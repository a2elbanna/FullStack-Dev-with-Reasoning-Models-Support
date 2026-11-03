"""OpenAI transport shared by the developer and browser agents.

The agent-facing contract remains a Chat-style assistant dict. `_response_output`
keeps the complete Responses output for lossless replay (including encrypted
reasoning, function call IDs and assistant phase) through logs and compression.
"""
from __future__ import annotations

import copy
import os
import re
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, APIStatusError
from anthropic import Anthropic

load_dotenv(Path(__file__).resolve().parents[1] / '.env')


class ModelResponseError(RuntimeError):
    """A response cannot safely be consumed or executed by the agent."""


class ModelOutputLimitError(ModelResponseError):
    """An incomplete response that a caller may retry with a larger budget."""

    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__(
            'Responses output limit reached: '
            f"budget={diagnostics['max_output_tokens']}, "
            f"output_tokens={diagnostics.get('output_tokens')}, "
            f"reasoning_tokens={diagnostics.get('reasoning_tokens')}, "
            f"visible_output_characters={diagnostics.get('visible_output_characters')}. "
            'No partial output was accepted. Configure a larger stage-specific output budget if needed.'
        )


def uses_responses_api(model, mode=None, vision=False):
    mode = mode or os.getenv('VLM_API_MODE' if vision else 'LLM_API_MODE', 'auto')
    if mode not in ('auto', 'responses', 'chat_completions'):
        raise ValueError('API mode must be auto, responses, or chat_completions.')
    return mode == 'responses' or (mode == 'auto' and is_reasoning_model(model))


def is_context_error(error):
    text = str(error).lower()
    return any(term in text for term in (
        'context_length_exceeded', 'maximum context length',
        'please reduce the length of the messages or completion',
        "'max_tokens' or 'max_completion_tokens' is too large"))


def is_fatal_model_error(error):
    if is_context_error(error):
        return False
    return (isinstance(error, ModelResponseError) or
            isinstance(error, APIStatusError) and error.status_code in (400, 401, 403, 404, 422))


def is_reasoning_model(model: str) -> bool:
    return bool(re.match(r'^(gpt-[56](?:[.-]|$)|o[134](?:-|$))', model.lower()))


def _credentials(provider: str, vision: bool, index: int | None):
    suffix = '' if index is None else str(index)
    if provider == 'anthropic':
        prefixes = ['ANTHROPIC_VLM', 'ANTHROPIC'] if vision else ['ANTHROPIC']
    else:
        prefixes = (['OPENAI_VLM', 'OPENAILIKE_VLM', 'OPENAI', 'OPENAILIKE']
                    if vision else ['OPENAI', 'OPENAILIKE'])
    for prefix in prefixes:
        key = os.getenv(f'{prefix}_API_KEY{suffix}')
        if key:
            # Keep key and endpoint paired: never send a native OpenAI key to
            # a legacy/self-hosted URL just because both are configured.
            url = os.getenv(f'{prefix}_BASE_URL{suffix}')
            if prefix.startswith('OPENAILIKE') and not url:
                raise ValueError(f'Set {prefix}_BASE_URL{suffix} with {prefix}_API_KEY{suffix}.')
            return key, url
    raise ValueError(f'Missing API key: configure {prefixes[0]}_API_KEY{suffix}.')


@lru_cache(maxsize=32)
def _client(provider, key, url):
    cls = Anthropic if provider == 'anthropic' else OpenAI
    options = {'api_key': key, 'timeout': 600.0, 'max_retries': 2}
    if url:
        options['base_url'] = url
    return cls(**options)


def get_anthropic_client(index=None, vision=False):
    return _client('anthropic', *_credentials('anthropic', vision, index))


def history_for_summary(messages):
    """Exclude replay metadata from text sent to a summarizer or chat endpoint."""
    allowed = {'role', 'content', 'tool_calls', 'tool_call_id', 'name'}
    return [{k: copy.deepcopy(v) for k, v in msg.items() if k in allowed}
            for msg in messages]


def _response_input(messages):
    items = []
    for msg in messages:
        role = msg['role']
        if role == 'assistant' and '_response_output' in msg:
            items.extend(copy.deepcopy(msg['_response_output']))
            continue
        if role == 'tool':
            items.append({'type': 'function_call_output',
                          'call_id': msg['tool_call_id'], 'output': msg.get('content') or ''})
            continue
        content = msg.get('content')
        if isinstance(content, list):
            parts = []
            for part in content:
                if part['type'] == 'text':
                    parts.append({'type': 'input_text', 'text': part['text']})
                elif part['type'] == 'image_url':
                    image = part['image_url']
                    parts.append({'type': 'input_image', 'image_url': image['url'],
                                  'detail': image.get('detail', 'auto')})
                else:
                    raise ValueError(f"Unsupported content part: {part['type']}")
            content = parts
        if content:
            items.append({'role': role, 'content': content})
        for call in msg.get('tool_calls', []):
            items.append({'type': 'function_call', 'call_id': call['id'],
                          'name': call['function']['name'],
                          'arguments': call['function']['arguments']})
    return items


def _response_tools(tools):
    converted = []
    for tool in tools:
        if tool.get('type') != 'function' or 'function' not in tool:
            raise ValueError('The developer agent expects Chat-style function tools.')
        spec = copy.deepcopy(tool['function'])
        # Responses otherwise normalizes schemas to strict mode, making the
        # existing tools' optional parameters required.
        spec.setdefault('strict', False)
        converted.append({'type': 'function', **spec})
    return converted


def call_openai(messages, model, index=None, vision=False, **kwargs):
    responses = uses_responses_api(model, kwargs.pop('api_mode', None), vision)
    if kwargs.get('stream'):
        raise ValueError('This agent requires a completed, non-streaming response.')
    kwargs.pop('stream', None)
    client = _client('openai', *_credentials('openai', vision, index))
    if not responses:
        # Qwen/vLLM retains its original max_tokens and sampling parameters.
        response = client.chat.completions.create(
            model=model, messages=history_for_summary(messages), **kwargs)
        if response.choices[0].finish_reason in ('length', 'content_filter'):
            raise ModelResponseError(f'Chat response stopped: {response.choices[0].finish_reason}')
        return response.choices[0].message.model_dump(exclude_none=True)

    # Responses budgets include internal reasoning plus visible output.
    legacy_limit = kwargs.pop('max_tokens', None)
    completion_limit = kwargs.pop('max_completion_tokens', None)
    kwargs.setdefault('max_output_tokens', int(os.getenv('OPENAI_MAX_OUTPUT_TOKENS') or
                                              completion_limit or legacy_limit or 32768))
    effort = kwargs.pop('reasoning_effort', None)
    if is_reasoning_model(model):
        reasoning = dict(kwargs.pop('reasoning', {}) or {})
        reasoning.setdefault('effort', effort or os.getenv('OPENAI_REASONING_EFFORT', 'medium'))
        kwargs['reasoning'] = reasoning
        if reasoning['effort'] != 'none':
            for param in ('temperature', 'top_p', 'logprobs', 'top_logprobs'):
                kwargs.pop(param, None)
    elif effort:
        kwargs['reasoning'] = {'effort': effort}
    if 'tools' in kwargs:
        kwargs['tools'] = _response_tools(kwargs['tools'])
    choice = kwargs.get('tool_choice')
    if isinstance(choice, dict) and 'function' in choice:
        kwargs['tool_choice'] = {'type': 'function', 'name': choice['function']['name']}
    if 'response_format' in kwargs:
        fmt = kwargs.pop('response_format')
        if fmt['type'] == 'json_schema':
            fmt = {'type': 'json_schema', **fmt['json_schema']}
        kwargs.setdefault('text', {})['format'] = fmt
    # Stateless replay allows independent agents and existing history compression.
    kwargs['store'] = False
    include = list(kwargs.pop('include', []))
    include = [x for x in include if x != 'message.output_text.logprobs']
    if 'reasoning.encrypted_content' not in include:
        include.append('reasoning.encrypted_content')
    response = client.responses.create(
        model=model, input=_response_input(messages), include=include, **kwargs)
    if response.status != 'completed':
        detail = getattr(response, 'incomplete_details', None) or getattr(response, 'error', None)
        if response.status == 'incomplete' and getattr(detail, 'reason', None) == 'max_output_tokens':
            usage = getattr(response, 'usage', None)
            output_details = getattr(usage, 'output_tokens_details', None)
            raise ModelOutputLimitError({
                'response_id': response.id,
                'max_output_tokens': kwargs['max_output_tokens'],
                'output_tokens': getattr(usage, 'output_tokens', None),
                'reasoning_tokens': getattr(output_details, 'reasoning_tokens', None),
                'visible_output_characters': len(response.output_text or ''),
            })
        raise ModelResponseError(
            f'Responses request {response.status}: {detail}. '
            'If the output budget was exhausted, increase OPENAI_MAX_OUTPUT_TOKENS '
            'or lower OPENAI_REASONING_EFFORT.')
    output = [item.model_dump(exclude_none=True) for item in response.output]
    calls, text = [], []
    for item in output:
        if item['type'] == 'function_call':
            calls.append({'id': item['call_id'], 'type': 'function',
                          'function': {'name': item['name'], 'arguments': item['arguments']}})
        elif item['type'] == 'message':
            for part in item.get('content', []):
                if part['type'] == 'refusal':
                    raise ModelResponseError(f"Model refused the request: {part['refusal']}")
                if part['type'] == 'output_text':
                    text.append(part['text'])
    if not calls and not any(text):
        raise ModelResponseError('The model returned no usable text or function calls.')
    assistant = {'role': 'assistant', 'content': '\n'.join(text), '_response_output': output}
    if getattr(response, 'usage', None) is not None:
        assistant['_usage'] = response.usage.model_dump(exclude_none=True)
    if calls:
        assistant['tool_calls'] = calls
    return assistant
