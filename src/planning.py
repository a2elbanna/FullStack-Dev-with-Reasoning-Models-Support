"""Compact architecture planning with bounded recovery from output limits."""
from __future__ import annotations

import os
from model_api import ModelOutputLimitError, is_fatal_model_error, uses_responses_api


def compact_planning_prompt(instruction: str, is_pure_frontend: bool) -> str:
    backend = '' if is_pure_frontend else '''
backendPlan:
  sharedTypes: object mapping reusable type names to typed field definitions
  entities: array of {name, briefDescription, mainFields: [{name, type}]}
  apiEndpoints: array of {name, method, path, description,
    requestSchema: [{name, type}], responseSchema: [{name, type}], statusCodes: [number]}
  businessRules: array of concise rules, including authorization, money invariants,
    state transitions, atomicity/idempotency and explicit demo/live boundaries when required
  nonFunctional: array of security, test, deployment and operational requirements
Use primitive types and references to sharedTypes (for example array<Voucher>).
Define each shared type once; do not repeatedly expand nested objects inline.
List static endpoints before parameterized endpoints. Frontend data-flow paths
must match the backend endpoint paths.
'''
    keys = 'frontendPlan' if is_pure_frontend else 'backendPlan and frontendPlan'
    return f'''Create a concise implementation architecture for the following requirements.
Return only one valid JSON object with top-level keys {keys}, with camelCase keys.
No prose, code fences, implementation code, worked examples or repeated requirements.
Target at most 6,000 visible output tokens. Use short descriptions and shared
contracts; do not reproduce the acceptance cases or enumerate every test step.
Reference their IDs where useful. Cover all requested capabilities, grouping related
operations into modules without omitting required business rules. The coding agents
will also receive the complete original requirements, so this plan is an architecture
and contract map, not a replacement for those requirements. Do not add unrequested
features or override requested frameworks, colors, roles or policy defaults.
{backend}
frontendPlan:
  pages: array of {{name, route, description,
    layout: {{header: boolean, footer: boolean,
      sections: [{{name, components: [string]}}]}},
    dataFlows: [{{endpointPath, action, optimisticUI: boolean, loadingStates, errorHandling}}],
    navigationLinks: [{{label, targetRoute, when}}]}}
  sharedComponents: array of {{name, purpose}}
  stateManagement: short description
  accessibilityAndUX: array of requirements from the product specification

Full product requirements (remain authoritative during implementation):
{instruction}'''


def _budgets(model, legacy_max_tokens):
    if any(tag in model.lower() for tag in ("anthropic", "claude")) or not uses_responses_api(model):
        return None, None
    # Only Astra's verified model limit is used as an automatic retry ceiling.
    # Other model families/custom aliases retain their existing limit unless a
    # planning-specific budget and retry ceiling are explicitly configured.
    astra = model == 'gpt-6-astra'
    default_initial = 65536 if astra else int(os.getenv('OPENAI_MAX_OUTPUT_TOKENS') or legacy_max_tokens)
    initial = int(os.getenv('OPENAI_PLANNING_MAX_OUTPUT_TOKENS') or default_initial)
    default_ceiling = 128000 if astra else initial
    ceiling = int(os.getenv('OPENAI_PLANNING_RETRY_MAX_OUTPUT_TOKENS') or default_ceiling)
    if initial <= 0 or ceiling < initial or (astra and ceiling > 128000):
        raise ValueError('Invalid planning budgets: require 0 < initial <= retry ceiling, '
                         'and an Astra ceiling no higher than 128000.')
    return initial, ceiling


def _validate_plan(plan, pure_frontend):
    if not isinstance(plan, dict):
        raise ValueError('Plan must be a JSON object.')
    expected = {'frontendPlan'} if pure_frontend else {'backendPlan', 'frontendPlan'}
    if set(plan) != expected:
        raise ValueError(f'Plan must contain exactly {sorted(expected)}.')
    for key in expected:
        if not isinstance(plan[key], dict):
            raise ValueError(f'{key} must be an object.')
    if not isinstance(plan['frontendPlan'].get('pages'), list) or not plan['frontendPlan']['pages']:
        raise ValueError('frontendPlan.pages must be a non-empty list.')
    if not pure_frontend:
        for field in ('entities', 'apiEndpoints', 'businessRules', 'nonFunctional'):
            if not isinstance(plan['backendPlan'].get(field), list):
                raise ValueError(f'backendPlan.{field} must be a list.')
    return plan


def generate_plans(*, instruction, model, is_pure_frontend, llm_generation,
                   parse_json, logger, legacy_max_tokens):
    budget, ceiling = _budgets(model, legacy_max_tokens)
    messages = [
        {'role': 'system', 'content': 'You are a senior full-stack software architect. Return concise JSON only.'},
        {'role': 'user', 'content': compact_planning_prompt(instruction, is_pure_frontend)},
    ]
    last_error = None
    # At most two model requests. No incomplete result is accepted or fed to a
    # coding agent, and no hidden reasoning is printed or reconstructed.
    for attempt in range(2):
        options = {'max_tokens': legacy_max_tokens}
        if budget is not None:
            options = {'max_output_tokens': budget, 'response_format': {'type': 'json_object'}}
        request = {'model': model, 'messages': messages.copy(), 'is_pure_frontend': is_pure_frontend,
                   'generation_options': options.copy(),
                   'reasoning_effort': os.getenv('OPENAI_REASONING_EFFORT', 'medium')}
        logger.log_message(f'Planning attempt {attempt + 1}/2; output budget={budget or legacy_max_tokens}; '
                           f'reasoning effort={request["reasoning_effort"]}')
        try:
            response = llm_generation(messages, model=model, **options)
            logger.log_llm_request_response(attempt, 'get_plans', request, response)
            return _validate_plan(parse_json(response.get('content') or ''), is_pure_frontend)
        except ModelOutputLimitError as error:
            last_error = error
            logger.log_llm_request_response(attempt, 'get_plans_error', request,
                                           response={'diagnostics': error.diagnostics}, error=str(error))
            if attempt or budget is None or budget >= ceiling:
                raise
            budget = min(budget * 2, ceiling)
            logger.log_message(f'Planning output limit reached; retrying once with budget={budget}. '
                               'Reasoning effort is unchanged.')
            messages = messages[:2] + [{'role': 'user', 'content':
                'The previous request exhausted its output budget. Start a fresh concise JSON plan. '
                'Keep the visible plan under 4,000 tokens by reusing shared types and short descriptions. '
                'Retain every required capability and invariant; do not repeat test cases or write implementation code.'}]
        except Exception as error:
            last_error = error
            logger.log_llm_request_response(attempt, 'get_plans_error', request, error=str(error))
            if is_fatal_model_error(error):
                raise
            messages = messages[:2] + [{'role': 'user', 'content':
                'Return a complete valid JSON object matching the requested plan shape, '
                'with a non-empty frontendPlan.pages list. Keep descriptions concise.'}]
    raise RuntimeError(f'Failed to obtain a valid plan after two attempts: {last_error}') from last_error
