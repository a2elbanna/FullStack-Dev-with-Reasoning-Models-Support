"""Compose the developer agent's request from a complete dataset sample.

Passing acceptance criteria to an agent does not execute or verify those tests.
The generated application must provide executable checks and their evidence.
"""
from __future__ import annotations

import json
from typing import Any


def build_generation_instruction(sample: dict[str, Any]) -> str:
    """Preserve the instruction and include supplied policies and test criteria.

    Instruction-only datasets keep their existing behavior. Do not include the
    whole sample: categories and arbitrary metadata are not development tasks.
    """
    instruction = sample.get('instruction', '')
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError('Each sample must contain a non-empty instruction string.')
    sections = [instruction]
    for key, heading, expected_type in (
        ('policy_defaults', 'Explicit policy defaults', dict),
        ('data_structures', 'Required persisted data', list),
        ('ui_instruct', 'Browser acceptance criteria', list),
        ('backend_test_cases', 'Backend acceptance criteria', list),
    ):
        value = sample.get(key)
        if value is None:
            continue
        if not isinstance(value, expected_type):
            raise ValueError(f'{key} must be a {expected_type.__name__}.')
        if value:
            sections.append(f'--- {heading} ---\n' + json.dumps(value, ensure_ascii=False, indent=2))
    if sample.get('ui_instruct') or sample.get('backend_test_cases'):
        sections.append(
            '--- Verification contract ---\n'
            'These acceptance criteria describe required behavior; they are not executed tests or proof of success. '
            'Implement appropriate executable checks, run the checks available in the environment, and report '
            'PASS, FAIL, or NOT_RUN with command results and evidence for each supplied test ID. '
            'Record unavailable services and credentials as blockers. Do not claim a criterion passed merely '
            'because code for it was written. Preserve the supplied test IDs in acceptance-results.json.'
        )
    return '\n\n'.join(sections)
