"""Offline transport regressions; no credentials, Docker, or network needed."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI, BadRequestError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import model_api as api

TOOLS = [{'type': 'function', 'kind': 'read', 'function': {
    'name': 'read_file', 'description': 'Read a file', 'parameters': {
        'type': 'object', 'properties': {'path': {'type': 'string'}, 'limit': {'type': 'integer'}},
        'required': ['path']}}}]
REASONING = {'id': 'rs_1', 'type': 'reasoning', 'summary': [], 'encrypted_content': 'opaque'}
CALL = {'id': 'fc_1', 'type': 'function_call', 'call_id': 'call_1',
        'name': 'read_file', 'arguments': '{"path":"README.md"}', 'status': 'completed'}
TEXT = {'id': 'msg_1', 'type': 'message', 'role': 'assistant', 'status': 'completed',
        'phase': 'final_answer', 'content': [{'type': 'output_text', 'text': 'Done', 'annotations': []}]}


def wire_response(output, status='completed', **kwargs):
    return {'id': 'resp_1', 'object': 'response', 'created_at': 0, 'model': 'gpt-6-astra',
            'status': status, 'output': output, **kwargs}


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'OPENAI_API_KEY': 'test'}, clear=True)
        self.env.start()
        self.requests = []
        self.responses = []
        self.client = OpenAI(api_key='test', max_retries=0,
                             http_client=httpx.Client(transport=httpx.MockTransport(self.handle)))
        self.mock = patch.object(api, '_client', return_value=self.client)
        self.mock.start()

    def tearDown(self):
        self.mock.stop()
        self.client.close()
        self.env.stop()

    def handle(self, request):
        self.requests.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json=self.responses.pop(0))

    def call(self, messages=None, **kwargs):
        return api.call_openai(messages or [{'role': 'user', 'content': 'Inspect'}],
                               kwargs.pop('model', 'gpt-6-astra'), **kwargs)

    def test_tools_and_reasoning_survive_tool_result_and_disk_roundtrip(self):
        self.responses = [wire_response([REASONING, CALL]), wire_response([TEXT])]
        assistant = self.call(tools=TOOLS, max_tokens=8192, temperature=.7, top_p=.9)
        self.assertEqual(assistant['tool_calls'][0]['id'], 'call_1')
        history = json.loads(json.dumps([{'role': 'system', 'content': 'Code'}, assistant,
            {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'file data', 'new_db_entries': []}]))
        self.assertEqual(self.call(history, tools=TOOLS)['content'], 'Done')
        path, first = self.requests[0]
        self.assertEqual(path, '/v1/responses')
        self.assertEqual(first['max_output_tokens'], 8192)
        self.assertFalse(first['tools'][0]['strict'])
        self.assertEqual(first['tools'][0]['parameters']['required'], ['path'])
        self.assertNotIn('kind', first['tools'][0])
        self.assertNotIn('temperature', first)
        self.assertNotIn('top_p', first)
        self.assertFalse(first['store'])
        self.assertEqual(first['reasoning']['effort'], 'medium')
        self.assertEqual(self.requests[1][1]['input'][1:3], [REASONING, CALL])
        self.assertEqual(self.requests[1][1]['input'][-1], {
            'type': 'function_call_output', 'call_id': 'call_1', 'output': 'file data'})

    def test_phase_is_preserved_without_duplicating_text(self):
        self.responses = [wire_response([REASONING, TEXT]), wire_response([TEXT])]
        assistant = self.call()
        self.call([assistant, {'role': 'user', 'content': 'Continue'}])
        self.assertEqual(self.requests[-1][1]['input'][1], TEXT)
        self.assertEqual(len(self.requests[-1][1]['input']), 3)

    def test_images_and_legacy_history(self):
        self.responses = [wire_response([TEXT])]
        self.call([{'role': 'assistant', 'content': None, 'tool_calls': [{
            'id': 'old_call', 'function': {'name': 'read_file', 'arguments': '{}'}}]},
            {'role': 'tool', 'tool_call_id': 'old_call', 'content': 'ok'},
            {'role': 'user', 'content': [{'type': 'text', 'text': 'Look'},
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,abc', 'detail': 'low'}}]}])
        items = self.requests[0][1]['input']
        self.assertEqual(items[0]['call_id'], 'old_call')
        self.assertEqual(items[-1]['content'][1]['type'], 'input_image')
        self.assertEqual(items[-1]['content'][1]['detail'], 'low')

    def test_qwen_keeps_chat_api_and_original_sampling_parameters(self):
        self.responses = [{'id': 'chat_1', 'object': 'chat.completion', 'created': 0, 'model': 'Qwen',
                           'choices': [{'index': 0, 'finish_reason': 'stop',
                                        'message': {'role': 'assistant', 'content': 'ok'}}]}]
        self.call(model='Qwen3-Coder', max_tokens=4096, temperature=.7)
        path, body = self.requests[0]
        self.assertEqual(path, '/v1/chat/completions')
        self.assertEqual(body['max_tokens'], 4096)
        self.assertEqual(body['temperature'], .7)
        self.assertNotIn('max_completion_tokens', body)

    def test_provider_keys_and_numbered_vision_clients(self):
        with patch.dict(os.environ, {'OPENAILIKE_API_KEY': 'legacy', 'OPENAILIKE_BASE_URL': 'http://local/v1',
                                    'OPENAILIKE_VLM_API_KEY2': 'vision', 'OPENAILIKE_VLM_BASE_URL2': 'http://vision/v1'}):
            self.assertEqual(api._credentials('openai', False, None), ('test', None))
            self.assertEqual(api._credentials('openai', True, 2), ('vision', 'http://vision/v1'))
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'Missing API key'):
                api._credentials('openai', False, None)

    def test_env_budget_overrides_legacy_agent_limit(self):
        self.responses = [wire_response([TEXT])]
        with patch.dict(os.environ, {'OPENAI_MAX_OUTPUT_TOKENS': '32768', 'OPENAI_REASONING_EFFORT': 'high'}):
            self.call(max_tokens=8192)
        self.assertEqual(self.requests[0][1]['max_output_tokens'], 32768)
        self.assertEqual(self.requests[0][1]['reasoning']['effort'], 'high')

    def test_incomplete_or_refused_response_is_never_executed(self):
        for response in [wire_response([CALL], status='incomplete', incomplete_details={'reason': 'max_output_tokens'}),
                         wire_response([]), wire_response([{**TEXT, 'content': [{'type': 'refusal', 'refusal': 'No'}]}])]:
            with self.subTest(response=response):
                self.responses = [response]
                with self.assertRaises(api.ModelResponseError):
                    self.call(tools=TOOLS)

    def test_summary_strips_encrypted_data_without_mutating_history(self):
        history = [{'role': 'assistant', 'content': 'Ready', '_response_output': [REASONING], 'tool_calls': []}]
        saved = copy.deepcopy(history)
        clean = api.history_for_summary(history)
        self.assertNotIn('opaque', json.dumps(clean))
        self.assertEqual(history, saved)

    def test_explicit_responses_mode_and_json_format(self):
        self.responses = [wire_response([TEXT])]
        self.call(model='custom-alias', api_mode='responses', response_format={'type': 'json_object'},
                  tool_choice={'type': 'function', 'function': {'name': 'read_file'}}, tools=TOOLS)
        body = self.requests[0][1]
        self.assertEqual(body['text']['format'], {'type': 'json_object'})
        self.assertEqual(body['tool_choice'], {'type': 'function', 'name': 'read_file'})

    def test_auth_and_schema_errors_are_fatal_but_context_errors_can_compress(self):
        response = httpx.Response(400, request=httpx.Request('POST', 'https://api.openai.com/v1/responses'))
        self.assertTrue(api.is_fatal_model_error(BadRequestError('unsupported parameter', response=response, body=None)))
        self.assertFalse(api.is_fatal_model_error(BadRequestError('context_length_exceeded', response=response, body=None)))

    def test_wrappers_import_with_only_openai_credentials(self):
        for name, rel in [('text_wrapper', 'src/utils/llm_generation.py'), ('vision_wrapper', 'src/webtester/vlm_generation.py')]:
            spec = importlib.util.spec_from_file_location(name, ROOT / rel)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.responses = [wire_response([TEXT])]
            fn = getattr(module, 'llm_generation', None) or module.vlm_generation
            result = fn([{'role': 'user', 'content': 'Hello'}], 'gpt-6-astra')
            self.assertEqual(result if isinstance(result, str) else result['content'], 'Done')


if __name__ == '__main__':
    unittest.main()
