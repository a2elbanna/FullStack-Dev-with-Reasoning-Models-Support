"""Exercise both real agent loops with a mocked model and tool executor."""
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from model_api import ModelResponseError, _response_input


class AgentIntegrationTests(unittest.TestCase):
    def agents(self):
        for name in ('core.agent', 'core_decoupled.agent'):
            module = importlib.import_module(name)
            agent = module.WebGenAgent2V1.__new__(module.WebGenAgent2V1)
            agent.config = SimpleNamespace(model='gpt-6-astra', max_tokens=32768,
                                           compression_ratio=.5, max_iterations=3)
            agent.max_history_length = 100
            agent.history = [{'role': 'system', 'content': 'Code'},
                             {'role': 'assistant', 'content': 'Ready'},
                             {'role': 'user', 'content': 'Build'}]
            agent.registry = Mock()
            agent.registry.get_tool_schemas.return_value = []
            agent.registry.execute_tool.return_value = {'llmContent': 'ok', 'returnDisplay': 'ok'}
            agent.session_logger = Mock()
            agent.chosen_template = {'name': 'example'}
            agent.validation_num = 0
            agent.is_frontend = False
            agent.is_pure_frontend = False
            agent.tool_call_history = []
            yield module, agent

    def test_agent_executes_multiple_calls_then_replays_complete_reasoning(self):
        for module, agent in self.agents():
            with self.subTest(module=module.__name__):
                output = [{'type': 'reasoning', 'id': 'rs_1', 'summary': [], 'encrypted_content': 'opaque'}]
                calls = []
                for i in (1, 2):
                    calls.append({'id': f'call_{i}', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{}'}})
                    output.append({'type': 'function_call', 'call_id': f'call_{i}', 'id': f'fc_{i}', 'name': 'read_file', 'arguments': '{}'})
                agent.llm_generation = Mock(return_value={'role': 'assistant', 'content': '', 'tool_calls': calls, '_response_output': output})
                self.assertEqual(agent.step(0)['type'], 'success')
                self.assertEqual(agent.registry.execute_tool.call_count, 2)
                restored = json.loads(json.dumps(agent.history))
                self.assertEqual(_response_input(restored)[3:6], output)
                self.assertEqual([x['call_id'] for x in _response_input(restored)[-2:]], ['call_1', 'call_2'])

    def test_compression_removes_old_metadata_and_keeps_recent_pairs(self):
        for module, agent in self.agents():
            with self.subTest(module=module.__name__):
                for i in (1, 2):
                    agent.history += [{'role': 'assistant', 'content': '',
                        'tool_calls': [{'id': f'c{i}', 'function': {'name': 'read_file', 'arguments': '{}'}}],
                        '_response_output': [{'type': 'reasoning', 'encrypted_content': 'opaque'}]},
                        {'role': 'tool', 'tool_call_id': f'c{i}', 'content': 'ok'}]
                kept = agent.history[-2:]
                with patch.object(module, 'llm_generation', return_value={'content': 'Summary'}) as summarize:
                    agent._compress_history(force=True)
                self.assertNotIn('opaque', summarize.call_args.args[0][1]['content'])
                self.assertEqual(agent.history[-2:], kept)
                self.assertEqual(len(agent.history), 6)

    def test_incomplete_response_stops_before_any_tool_executes(self):
        for module, agent in self.agents():
            with self.subTest(module=module.__name__):
                agent.llm_generation = Mock(side_effect=ModelResponseError('incomplete'))
                self.assertEqual(agent.step(0)['type'], 'fatal_error')
                agent.registry.execute_tool.assert_not_called()
                self.assertEqual(len(agent.history), 3)
                agent.initialize_agent = Mock(return_value=0)
                agent.step = Mock(return_value={'type': 'fatal_error'})
                self.assertFalse(agent.run_agent())
                agent.step.assert_called_once()

    def test_run_returns_success_for_launcher(self):
        import tempfile
        for module, agent in self.agents():
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as folder:
                agent.config.log_dir = folder
                agent.initialize_template_and_plan = Mock()
                agent.run_agent = Mock(return_value=True)
                self.assertTrue(agent.run())
                self.assertTrue(json.loads((Path(folder) / 'finished.json').read_text())['is_finished'])


if __name__ == '__main__':
    unittest.main()
