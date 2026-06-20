"""
Pathfinder instruction script template.

Run with:
  pathfinder script --manifest pathfinder.manifest.json --file pathfinder_instruction_template.py --autosave

Available objects:
  api, controller, runtime, manifest, manifest_path, session, session_path
"""

state_id = api.current_state_id() or "I0"

api.set_cursor(state_id)

api.add_input(
    state_id,
    "cursor-input",
    """
emit({
    'kind': 'input',
    'state': state_id,
    'cursor': cursor,
    'payload': event.get('payload', {})
})
""",
)

api.add_processor(
    state_id,
    "mark-processed",
    """
state.setdefault('program_data', {})['processed_at'] = now_utc()
emit({'kind': 'process', 'state': state_id, 'processed_at': state['program_data']['processed_at']})
""",
)

api.add_output(
    state_id,
    "write-json-output",
    """
output_path = Path(manifest.get('output_directory', '.')) / f'{state_id}.state-output.json'
output_path.write_text(json.dumps({'state': state_id, 'cursor': cursor}, indent=2), encoding='utf-8')
emit({'kind': 'output', 'wrote': str(output_path)})
""",
)

result = api.run("all", state_id, payload={"source": "instruction-template"})
