"""Regression tests for the reported max_output_tokens planning failure."""
import importlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import model_api
from planning import generate_plans, compact_planning_prompt, _budgets

PLAN = {'backendPlan': {'entities': [], 'apiEndpoints': [], 'businessRules': ['Atomic money updates'],
                        'nonFunctional': []},
        'frontendPlan': {'pages': [{'name': 'Home', 'route': '/'}]}}


def response(output, status='completed', **extra):
    return {'id': 'resp_test', 'object': 'response', 'created_at': 0, 'model': 'gpt-6-astra',
            'status': status, 'output': output, **extra}


def completed(plan=PLAN):
    return response([{'type': 'message', 'id': 'msg_test', 'role': 'assistant', 'status': 'completed',
                      'content': [{'type': 'output_text', 'text': json.dumps(plan), 'annotations': []}]}])


def incomplete(budget=65536):
    return response([], status='incomplete', incomplete_details={'reason': 'max_output_tokens'},
                    usage={'input_tokens': 100, 'output_tokens': budget, 'total_tokens': budget+100,
                           'input_tokens_details': {'cached_tokens': 0},
                           'output_tokens_details': {'reasoning_tokens': budget}})


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'OPENAI_API_KEY': 'test',
            'OPENAI_MAX_OUTPUT_TOKENS': '32768', 'OPENAI_REASONING_EFFORT': 'medium'}, clear=True)
        self.env.start()
        self.requests = []
        self.responses = []
        self.logger = Mock()
        self.client = OpenAI(api_key='test', max_retries=0,
                            http_client=httpx.Client(transport=httpx.MockTransport(self.handle)))
        self.client_patch = patch.object(model_api, '_client', return_value=self.client)
        self.client_patch.start()

    def tearDown(self):
        self.client_patch.stop()
        self.client.close()
        self.env.stop()

    def handle(self, request):
        self.requests.append(json.loads(request.content))
        return httpx.Response(200, json=self.responses.pop(0))

    def run_planner(self, **overrides):
        kwargs = dict(instruction='Build a voucher site with white background and teal components.',
                      model='gpt-6-astra', is_pure_frontend=False,
                      llm_generation=model_api.call_openai, parse_json=json.loads,
                      logger=self.logger, legacy_max_tokens=128000)
        kwargs.update(overrides)
        return generate_plans(**kwargs)

    def test_reported_failure_recovers_at_larger_budget_with_reasoning_enabled(self):
        self.responses = [incomplete(), completed()]
        self.assertEqual(self.run_planner(), PLAN)
        self.assertEqual([r['max_output_tokens'] for r in self.requests], [65536, 128000])
        for request in self.requests:
            self.assertEqual(request['reasoning']['effort'], 'medium')
            self.assertEqual(request['text']['format'], {'type': 'json_object'})
        error_log = next(c for c in self.logger.log_llm_request_response.call_args_list
                         if c.args[1] == 'get_plans_error')
        self.assertEqual(error_log.kwargs['response']['diagnostics']['reasoning_tokens'], 65536)
        self.assertNotIn('opaque', str(error_log))

    def test_repeated_exhaustion_stops_after_two_requests(self):
        self.responses = [incomplete(), incomplete(128000)]
        with self.assertRaises(model_api.ModelOutputLimitError):
            self.run_planner()
        self.assertEqual(len(self.requests), 2)

    def test_explicit_planning_cap_is_respected(self):
        with patch.dict(os.environ, {'OPENAI_PLANNING_MAX_OUTPUT_TOKENS': '32768',
                                     'OPENAI_PLANNING_RETRY_MAX_OUTPUT_TOKENS': '32768'}):
            self.responses = [incomplete(32768)]
            with self.assertRaises(model_api.ModelOutputLimitError):
                self.run_planner()
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]['max_output_tokens'], 32768)

    def test_incomplete_json_is_never_accepted_even_if_parseable(self):
        full = completed()
        full.update(status='incomplete', incomplete_details={'reason': 'max_output_tokens'})
        self.responses = [full, completed()]
        self.assertEqual(self.run_planner(), PLAN)
        self.assertEqual(len(self.requests), 2)

    def test_malformed_plan_shape_retries_then_validates(self):
        self.responses = [completed({'backendPlan': 'wrong', 'frontendPlan': {}}), completed()]
        self.assertEqual(self.run_planner(), PLAN)
        self.assertEqual([r['max_output_tokens'] for r in self.requests], [65536, 65536])

    def test_non_budget_failure_does_not_retry(self):
        self.responses = [response([], status='failed', error={'code': 'server_error', 'message': 'Failed'})]
        with self.assertRaises(model_api.ModelResponseError):
            self.run_planner()
        self.assertEqual(len(self.requests), 1)

    def test_pure_frontend_and_both_actual_agent_entrypoints(self):
        for name in ['core.agent', 'core_decoupled.agent']:
            module = importlib.import_module(name)
            agent = module.WebGenAgent2V1.__new__(module.WebGenAgent2V1)
            agent.config = SimpleNamespace(instruction='Build a site', model='gpt-6-astra', max_tokens=8192)
            agent.is_pure_frontend = True
            agent.llm_generation = model_api.call_openai
            agent.session_logger = self.logger
            plan = {'frontendPlan': PLAN['frontendPlan']}
            self.responses = [completed(plan)]
            self.assertEqual(agent.get_plans(), plan)
            self.assertEqual(self.requests[-1]['max_output_tokens'], 65536)

    def test_qwen_and_anthropic_keep_legacy_arguments(self):
        for model in ['Qwen3-Coder', 'claude-sonnet-test']:
            call = Mock(return_value={'content': json.dumps(PLAN)})
            self.assertEqual(self.run_planner(model=model, llm_generation=call, legacy_max_tokens=8192), PLAN)
            self.assertEqual(call.call_args.kwargs, {'model': model, 'max_tokens': 8192})

    def test_model_limit_validation_and_no_guessed_other_model_escalation(self):
        self.assertEqual(_budgets('gpt-5-mini', 8192), (32768, 32768))
        with patch.dict(os.environ, {'OPENAI_PLANNING_MAX_OUTPUT_TOKENS': '128001'}):
            with self.assertRaises(ValueError):
                _budgets('gpt-6-astra', 128000)
        with patch.dict(os.environ, {'LLM_API_MODE': 'responses'}):
            self.assertEqual(_budgets('claude-sonnet-test', 8192), (None, None))

    def test_compact_prompt_keeps_full_requirements_and_avoids_conflicting_style(self):
        instruction = 'white and teal; preserve every financial rule; BE01 and UI01'
        prompt = compact_planning_prompt(instruction, False)
        self.assertIn(instruction, prompt)
        self.assertIn('sharedTypes', prompt)
        self.assertNotIn('navy', prompt)
        self.assertNotIn('think step by step', prompt)
        self.assertLess(len(prompt) - len(instruction), 3500)


if __name__ == '__main__':
    unittest.main()
