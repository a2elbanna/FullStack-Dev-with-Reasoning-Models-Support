"""Checks of the generation input wiring, not of the generated website."""
import ast
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from generation_input import build_generation_instruction


class GenerationInputTests(unittest.TestCase):
    def test_instruction_only_preserves_existing_behavior(self):
        self.assertEqual(build_generation_instruction({'instruction': 'Build a site.'}), 'Build a site.')

    def test_all_requirement_fields_reach_agent_without_mutating_input(self):
        sample = {'instruction': 'Build.', 'policy_defaults': {'mode': 'DEMO'},
                  'data_structures': ['wallet'],
                  'ui_instruct': [{'id': 'UI01', 'task': 'العربية'}],
                  'backend_test_cases': [{'id': 'BE01', 'instruction': 'Concurrent redemption'}],
                  'private_metadata': 'do-not-forward'}
        original = copy.deepcopy(sample)
        result = build_generation_instruction(sample)
        for expected in ['Build.', 'DEMO', 'wallet', 'UI01', 'العربية', 'BE01', 'Concurrent redemption', 'NOT_RUN']:
            self.assertIn(expected, result)
        self.assertNotIn('do-not-forward', result)
        self.assertEqual(sample, original)

    def test_empty_optional_fields_do_not_add_noise(self):
        self.assertEqual(build_generation_instruction({'instruction': 'Build.', 'ui_instruct': [],
                                                       'policy_defaults': {}, 'backend_test_cases': None}), 'Build.')

    def test_malformed_requirements_fail_visibly(self):
        for sample in [{}, {'instruction': ''}, {'instruction': None},
                       {'instruction': 'Build', 'ui_instruct': 'not a list'},
                       {'instruction': 'Build', 'policy_defaults': []}]:
            with self.subTest(sample=sample), self.assertRaises(ValueError):
                build_generation_instruction(sample)

    def test_both_launchers_use_the_shared_composer(self):
        # Exercise process_sample with fakes so no containers or filesystem work run.
        from types import SimpleNamespace
        from unittest.mock import Mock
        for filename in ['run_batch.py', 'run_batch_decoupled.py']:
            tree = ast.parse((ROOT / 'src/run' / filename).read_text())
            fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'process_sample')
            captured = Mock(return_value=(True, 'sample', 'done'))
            namespace = {'build_generation_instruction': build_generation_instruction,
                         'os': __import__('os'), 'time': SimpleNamespace(sleep=lambda _: None),
                         'run_agent_in_container': captured}
            exec(compile(ast.Module(body=[fn], type_ignores=[]), filename, 'exec'), namespace)
            args = SimpleNamespace(model='gpt-6-astra', max_history_length=600, max_iterations=400,
                                   overwrite=False, compression_ratio=.5, max_validation_num=5,
                                   max_summary_retry=5, clear_backend=False, template_names=None)
            sample = {'id': 'sample', 'instruction': 'Build',
                      'backend_test_cases': [{'id': 'BE01', 'instruction': 'Verify ledger'}]}
            self.assertEqual(namespace['process_sample'](sample, args, '/unused/work', '/unused/log'),
                             (True, 'sample', 'done'))
            self.assertIn('Verify ledger', captured.call_args.kwargs['instruction'])
            self.assertIn('BE01', captured.call_args.kwargs['instruction'])

    def test_voucher_specification_has_consistent_ids_and_policies(self):
        lines = [line for line in (ROOT / 'data/new-site.jsonl').read_text().splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        sample = json.loads(lines[0])
        self.assertEqual(sample['id'], 'my001')
        self.assertEqual(sample['requirements_version'], 'voucher-v2')
        ui = sample['ui_instruct']; backend = sample['backend_test_cases']
        self.assertEqual(len(ui), 20)
        self.assertEqual(len(backend), 40)
        ids = [test['id'] for test in ui + backend]
        self.assertEqual(len(ids), len(set(ids)))
        for test in ui:
            self.assertTrue(test['task'] and test['expected_result'])
        for test in backend:
            self.assertTrue(test['instruction'] and test['expected_result'])
        policies = sample['policy_defaults']
        self.assertEqual(policies['mode'], 'DEMO')
        self.assertIsNone(policies['voucher_expiry_days'])
        self.assertEqual(policies['redemption_approval_expiry_seconds'], 120)
        self.assertEqual(policies['unused_voucher_refund_destination'], 'current_holder_wallet')
        rendered = build_generation_instruction(sample)
        for test_id in ids:
            self.assertIn(test_id, rendered)
        self.assertIn('Africa/Cairo', rendered)
        self.assertIn('simulated', rendered)
        self.assertIn('append-only', rendered)

    def test_launcher_uses_separate_output_tag(self):
        script = (ROOT / 'src/run/run_batch.sh').read_text()
        self.assertIn('TAG="${TAG:-voucher-v2-responses}"', script)
        self.assertIn('MODEL="${MODEL:-gpt-6-astra}"', script)


if __name__ == '__main__':
    unittest.main()
