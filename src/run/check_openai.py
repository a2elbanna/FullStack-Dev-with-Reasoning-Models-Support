#!/usr/bin/env python3
"""A small opt-in live check of Responses tool calling and reasoning replay."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_api import call_openai


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='gpt-6-astra')
    parser.add_argument('--live', action='store_true', help='Send two billable API requests')
    args = parser.parse_args()
    if not args.live:
        parser.error('Use --live to send the two small API requests.')
    history = [{'role': 'user', 'content': 'Call integration_probe once. After its result, reply with that result only.'}]
    tools = [{'type': 'function', 'function': {'name': 'integration_probe',
              'description': 'Return a fixed connectivity test result.',
              'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}}]
    first = call_openai(history, args.model, api_mode='responses', tools=tools,
                        tool_choice={'type': 'function', 'function': {'name': 'integration_probe'}},
                        reasoning_effort='low', max_output_tokens=4096)
    calls = first.get('tool_calls', [])
    if not calls or any(c['function']['name'] != 'integration_probe' for c in calls):
        raise RuntimeError('Expected integration_probe function call.')
    history.append(first)
    for call in calls:
        history.append({'role': 'tool', 'tool_call_id': call['id'], 'content': 'PROBE_OK'})
    second = call_openai(history, args.model, api_mode='responses', tools=tools,
                         tool_choice='none', reasoning_effort='low', max_output_tokens=4096)
    if 'PROBE_OK' not in second['content']:
        raise RuntimeError('The follow-up did not acknowledge the function output.')
    print(f'{args.model}: Responses function call and reasoning replay passed.')


if __name__ == '__main__':
    main()
