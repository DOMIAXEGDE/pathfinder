# Pathfinder Developer Manual

Verified against the working text-editor-session in `D:\execute\omicron\pathfinder_text_editor_session` on 2026-06-21.

## 1. What Pathfinder Is

Pathfinder is a portable graphical runtime whose application state is described by:

- Square state images, such as the 700 by 700 PNG files in `pathfinder_text_editor_session\states`.
- A manifest, `pathfinder.manifest.json`, that indexes images, bootstrap order, basis metadata, workspace paths, and programmable state hooks.
- A session file, `pathfinder.session.json`, that persists the developer's active project, cursor, recent scripts, and runtime continuity.
- Python hook scripts that attach input events, processing logic, and output events to specific states.
- A Tensor workspace file, `pathfinder.workspace.json`, generated from the manifest for runtime/state inspection.

The important mental model is simple: a Pathfinder application is a graph of image-indexed states, and each state may run Python before, during, or after interaction.

## 2. Core Files

For the text-editor-session, the current working file-set is:

```text
D:\execute\omicron\pathfinder_text_editor_session
  pathfinder.manifest.json
  pathfinder.session.json
  pathfinder.workspace.json
  state-gen.py
  text-session-instruct.py
  wire-text-session-scripts.py
  text-session-store.json
  text-session-config.json
  states\
  scripts\
  plugins\
  exports\
```

The required generated state images are in:

```text
D:\execute\omicron\pathfinder_text_editor_session\states
```

Each state image is 700 by 700 pixels. The manifest boot sequence is:

```text
I0 -> I1 -> I2 -> I3 -> I4 -> I5 -> I6 -> I7 -> I8 -> I9 -> I10 -> I11
```

## 3. Runtime Concepts

### Manifest

`pathfinder.manifest.json` is the application definition. It stores:

- `image_states`: the state records, including `id`, image path, index, and `editor_operation`.
- `bootstrap_sequence`: the runtime order.
- `state_programming`: input/process/output hooks per state.
- `text_editor_session`: paths for the text editor store, config, plugins, exports, and scripts.
- `workspace_path`: the generated Tensor workspace JSON.

The text editor uses `editor_operation` values to avoid brittle positional wiring:

```text
crud.create
crud.read
crud.update
crud.delete
batch.create
batch.read
batch.update
batch.delete
python.plugins
config.style
session.persistence
```

### Session

`pathfinder.session.json` is the developer continuity file. It stores:

- active manifest path
- known projects
- state cursor
- recent instruction scripts

The `state_cursor` is the runtime's current pointer into a manifest state. Hook scripts can read it through the `cursor` variable.

### Hooks

Each state may have three hook collections:

```text
input_events
processors
output_events
```

Pathfinder names them as:

```text
input
process
output
```

Each hook can embed code directly, but the recommended pattern is to use `source_path` so the hook runs an editable `.py` file.

## 4. Text Editor State Map

The working text editor session wires these scripts:

| State | Operation | Hook Kind | Script |
|---|---|---|---|
| `I1` | `crud.create` | `input` | `scripts\input\singular_create.py` |
| `I2` | `crud.read` | `output` | `scripts\output\singular_read.py` |
| `I3` | `crud.update` | `process` | `scripts\process\singular_update.py` |
| `I4` | `crud.delete` | `process` | `scripts\process\singular_delete.py` |
| `I5` | `batch.create` | `input` | `scripts\input\batch_create.py` |
| `I6` | `batch.read` | `output` | `scripts\output\batch_read.py` |
| `I7` | `batch.update` | `process` | `scripts\process\batch_update.py` |
| `I8` | `batch.delete` | `process` | `scripts\process\batch_delete.py` |
| `I9` | `python.plugins` | `process` | `scripts\process\python_plugins.py` |
| `I10` | `config.style` | `process` | `scripts\process\config_style.py` |
| `I11` | `session.persistence` | `output` | `scripts\output\session_persistence.py` |

The shared implementation is:

```text
scripts\text_session_runtime.py
```

That module owns JSON persistence, interactive prompts, CRUD logic, batch logic, plugin dispatch, Python transform execution, and persistence summaries.

## 5. Automatic Wiring

Use the dedicated wiring script:

```text
D:\execute\omicron\pathfinder_text_editor_session\wire-text-session-scripts.py
```

Recommended Pathfinder mode:

```powershell
cd D:\execute\omicron
python .\pathfinder.py script `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session .\pathfinder_text_editor_session\pathfinder.session.json `
  --file .\pathfinder_text_editor_session\wire-text-session-scripts.py `
  --autosave
```

Installed app equivalent:

```powershell
Pathfinder.exe script `
  --manifest D:\execute\omicron\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session D:\execute\omicron\pathfinder_text_editor_session\pathfinder.session.json `
  --file D:\execute\omicron\pathfinder_text_editor_session\wire-text-session-scripts.py `
  --autosave
```

Direct maintenance mode:

```powershell
python .\pathfinder_text_editor_session\wire-text-session-scripts.py `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session .\pathfinder_text_editor_session\pathfinder.session.json
```

When run directly, rebuild the workspace afterward:

```powershell
python .\pathfinder.py workspace `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --format summary `
  --rebuild
```

The wiring script:

- validates every target script exists
- compiles every target script with `py_compile`
- removes existing hooks whose names begin with `text-session:`
- installs the 11 known hooks with `source_path`
- restores the default `I0 -> I11` sequence
- updates `text_editor_session` paths
- resets the state cursor to `I0`

## 6. Running the Session

Graphical runtime:

```powershell
python .\pathfinder.py gui `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session .\pathfinder_text_editor_session\pathfinder.session.json `
  --autosave
```

Installed app:

```powershell
Pathfinder.exe gui `
  --manifest D:\execute\omicron\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session D:\execute\omicron\pathfinder_text_editor_session\pathfinder.session.json `
  --autosave
```

In the GUI, right-click a state and run input, processing, output, or all state behavior. When the text editor hook needs values and no useful payload is available, it prompts interactively.

CLI shell:

```powershell
python .\pathfinder.py shell `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session .\pathfinder_text_editor_session\pathfinder.session.json `
  --autosave
```

CLI hook listing:

```powershell
python .\pathfinder.py program `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session .\pathfinder_text_editor_session\pathfinder.session.json `
  list --state I1
```

Note: the current `program run` CLI sends a simple payload such as `{"source": "cli"}`. For full custom payloads, use an instruction script or `RuntimeController` from Python.

## 7. Hook Execution Context

Pathfinder provides each hook script these variables:

| Variable | Meaning |
|---|---|
| `controller` / `runtime` | The `RuntimeController` instance |
| `manifest` | Loaded manifest dictionary |
| `manifest_path` | Path to the manifest |
| `state` | Current state record |
| `state_id` | Current state id |
| `cursor` | Current state cursor |
| `session` | Loaded session dictionary, if any |
| `session_path` | Path to the session file, if any |
| `event` | Hook event, including payload |
| `hook` | Hook record |
| `outputs` | Output accumulator list |
| `emit(value)` | Append a value to outputs |
| `goto(state)` | Move runtime cursor to a state |
| `Path`, `json`, `math`, `os`, `re`, `shlex`, `subprocess`, `sys` | Utility modules |
| `now_utc()` | UTC timestamp helper |

A minimal custom output hook looks like:

```python
payload = event.get("payload", {})
emit({
    "state": state_id,
    "cursor": cursor,
    "payload": payload,
})
```

## 8. Text Editor Payload Contract

All text editor hooks accept a Python dictionary payload through `event["payload"]`.

### Singular Create, `I1`

```python
api.run("input", "I1", {
    "id": "note-1",
    "title": "Note 1",
    "content": "Hello",
    "replace": True,
})
```

Supported fields:

```text
id, name, title, content, value, path, file, metadata, replace, interactive
```

### Singular Read, `I2`

```python
api.run("output", "I2", {"id": "note-1"})
api.run("output", "I2", {"all": True})
api.run("output", "I2", {"query": "hello"})
```

Supported fields:

```text
id, ids, query, all, interactive
```

### Singular Update, `I3`

```python
api.run("process", "I3", {
    "id": "note-1",
    "append": " world",
})
```

Supported fields:

```text
id, content, value, path, file, append, prepend, suffix, prefix,
find, replace, transform, transform_code, title, metadata, interactive
```

Supported built-in transforms:

```text
upper, lower, title, strip
```

Python transform example:

```python
api.run("process", "I3", {
    "id": "note-1",
    "transform_code": "result = content.replace('world', 'Pathfinder')",
})
```

Or:

```python
api.run("process", "I3", {
    "id": "note-1",
    "transform_code": "def transform(content, document, payload):\n    return content.upper()",
})
```

The transform namespace receives:

```text
content, document, payload, config, store, result
```

### Singular Delete, `I4`

```python
api.run("process", "I4", {
    "id": "note-1",
    "archive": True,
})
```

Supported fields:

```text
id, archive, interactive
```

Deleted documents are archived when `archive_on_delete` is enabled in config or when `archive` is true.

### Batch Create, `I5`

```python
api.run("input", "I5", {
    "documents": [
        {"id": "batch-1", "title": "Batch 1", "content": "one"},
        {"id": "batch-2", "title": "Batch 2", "content": "two"},
    ]
})
```

Supported fields:

```text
documents, path, file, paths, files, directory, glob, id_prefix, encoding, interactive
```

### Batch Read, `I6`

```python
api.run("output", "I6", {
    "ids": ["batch-1", "batch-2"],
    "export": True,
    "export_name": "batch-read.json",
})
```

Supported fields:

```text
ids, query, all, export, export_name, interactive
```

Exports are written to:

```text
pathfinder_text_editor_session\exports
```

### Batch Update, `I7`

```python
api.run("process", "I7", {
    "ids": ["batch-1", "batch-2"],
    "suffix": "!",
})
```

Supported fields:

```text
ids, query, all, content, value, path, file, append, prepend,
suffix, prefix, find, replace, transform, transform_code, interactive
```

### Batch Delete, `I8`

```python
api.run("process", "I8", {
    "ids": ["batch-1", "batch-2"],
    "archive": True,
})
```

Supported fields:

```text
ids, query, all, archive, interactive
```

### Python Plugins, `I9`

```python
api.run("process", "I9", {
    "plugins": ["example_text_plugin.py"],
})
```

Drop plugin files into:

```text
pathfinder_text_editor_session\plugins
```

A plugin may define any of:

```python
def configure(config):
    config.setdefault("behaviors", {})["custom"] = True
    return {"configured": True}

def style(style_config):
    return {"accent": "#7B61FF"}

def handle(editor):
    editor["documents"]["plugin-note"] = {
        "id": "plugin-note",
        "title": "Plugin Note",
        "content": "Created by plugin",
        "metadata": {},
        "created_at": editor["runtime"].now_utc(),
        "updated_at": editor["runtime"].now_utc(),
        "revisions": [],
    }
    return {"created": "plugin-note"}
```

The `editor` object includes:

```text
runtime, manifest, store, config, documents, payload, event, cursor,
project_dir, plugins_dir, exports_dir, create_document, read_document,
update_document, delete_document, emit
```

### Config and Style, `I10`

```python
api.run("process", "I10", {
    "style": {
        "font_size": 16,
        "accent": "#7B61FF"
    },
    "behaviors": {
        "autosave": True
    }
})
```

Supported fields:

```text
style, behaviors, plugins_config, reset, interactive
```

### Persistence Summary, `I11`

```python
api.run("output", "I11", {
    "summary_name": "text-session-summary.json",
})
```

Writes a summary JSON beside the manifest.

## 9. Programmatic Development

Create a Pathfinder instruction script when you need full payload control:

```python
from pathlib import Path

api.run("input", "I1", {
    "id": "dev-note",
    "title": "Developer Note",
    "content": "Created from an instruction script.",
    "replace": True,
})

api.run("process", "I3", {
    "id": "dev-note",
    "append": "\nEdited programmatically.",
})

result = api.run("output", "I2", {"id": "dev-note"})
api.save()
```

Run it:

```powershell
python .\pathfinder.py script `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session .\pathfinder_text_editor_session\pathfinder.session.json `
  --file .\my-instruction.py `
  --autosave
```

For Python automation outside the instruction-script sandbox:

```python
from pathlib import Path
from pathfinder import RuntimeController

root = Path("pathfinder_text_editor_session")
controller = RuntimeController(root / "pathfinder.manifest.json", root / "pathfinder.session.json")
controller.run_hooks("input", state_id="I1", payload={
    "id": "external-note",
    "content": "Created through RuntimeController.",
    "replace": True,
})
controller.save()
```

## 10. Creating A New Pathfinder Session

The recommended workflow is:

1. Generate or collect square state images.
2. Create `pathfinder.manifest.json` with `image_states`.
3. Add stable state ids and operation metadata.
4. Create `pathfinder.session.json`.
5. Create hook scripts under `scripts\input`, `scripts\process`, and `scripts\output`.
6. Wire hooks using a dedicated script similar to `wire-text-session-scripts.py`.
7. Rebuild the workspace.
8. Verify with CLI, GUI, and programmatic smoke tests.

For the text editor example, state images and initial JSON are generated by:

```powershell
python .\pathfinder_text_editor_session\state-gen.py
```

Then install defaults and hooks:

```powershell
python .\pathfinder.py script `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session .\pathfinder_text_editor_session\pathfinder.session.json `
  --file .\pathfinder_text_editor_session\text-session-instruct.py `
  --autosave
```

Then rewire to the editable hook files:

```powershell
python .\pathfinder.py script `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session .\pathfinder_text_editor_session\pathfinder.session.json `
  --file .\pathfinder_text_editor_session\wire-text-session-scripts.py `
  --autosave
```

## 11. Creating Hook Scripts

A hook script can be tiny:

```python
payload = event.get("payload", {})
emit({"state": state_id, "received": payload})
```

For hooks that share local helper modules, use the `source_path` pattern:

```python
from pathlib import Path
import sys

_source = Path(hook.get("source_path") or ".").resolve()
_scripts_dir = _source.parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from text_session_runtime import TextSessionRuntime

runtime = TextSessionRuntime(globals())
emit(runtime.create_document())
```

When adding a new state:

1. Add the state record to `image_states`.
2. Give it a stable `id`.
3. Give it an operation label, such as `editor_operation`.
4. Create its `.py` hook script.
5. Add the operation to the wiring script.
6. Run the wiring script.
7. Run `pathfinder.py status` and `pathfinder.py workspace --rebuild`.

## 12. Verification

Compile all text-editor-session Python files:

```powershell
$files = @(
  '.\pathfinder_text_editor_session\text-session-instruct.py',
  '.\pathfinder_text_editor_session\wire-text-session-scripts.py'
) + (Get-ChildItem .\pathfinder_text_editor_session\scripts -Recurse -Filter *.py | ForEach-Object { $_.FullName })
python -m py_compile @files
```

Wire hooks:

```powershell
python .\pathfinder.py script `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session .\pathfinder_text_editor_session\pathfinder.session.json `
  --file .\pathfinder_text_editor_session\wire-text-session-scripts.py `
  --autosave
```

Check status:

```powershell
python .\pathfinder.py status `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json
```

Expected summary:

```text
Image side: 700 | states: 12
Bootstrap sequence: I0 -> I1 -> I2 -> I3 -> I4 -> I5 -> I6 -> I7 -> I8 -> I9 -> I10 -> I11
Programmable states: 12
```

Confirm all hooks are file-backed:

```powershell
python -c "import json; from pathlib import Path; m=json.loads(Path('pathfinder_text_editor_session/pathfinder.manifest.json').read_text()); hooks=[h for r in m['state_programming']['states'].values() for k in ('input_events','processors','output_events') for h in r.get(k,[])]; print(len(hooks), sum(1 for h in hooks if h.get('source_path')))"
```

Expected:

```text
11 11
```

Rebuild workspace:

```powershell
python .\pathfinder.py workspace `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --format summary `
  --rebuild
```

## 13. Troubleshooting

### Hook does not run

Check the hook is installed on the state:

```powershell
python .\pathfinder.py program `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session .\pathfinder_text_editor_session\pathfinder.session.json `
  list --state I3
```

Confirm `source_path` points to an existing `.py` file.

### Workspace is stale

Run:

```powershell
python .\pathfinder.py workspace `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --format summary `
  --rebuild
```

### CLI cannot pass a rich payload

Use a Pathfinder instruction script with `api.run(...)`, or call `RuntimeController.run_hooks(...)` from Python.

### Hook script imports fail

Use the `source_path` bootstrap pattern shown above. It adds the session `scripts` directory to `sys.path`.

### Store has test data

Reset the text editor store and reinstall defaults:

```powershell
Remove-Item .\pathfinder_text_editor_session\text-session-store.json -ErrorAction SilentlyContinue
Remove-Item .\pathfinder_text_editor_session\text-session-config.json -ErrorAction SilentlyContinue
python .\pathfinder.py script `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session .\pathfinder_text_editor_session\pathfinder.session.json `
  --file .\pathfinder_text_editor_session\text-session-instruct.py `
  --autosave
python .\pathfinder.py script `
  --manifest .\pathfinder_text_editor_session\pathfinder.manifest.json `
  --session .\pathfinder_text_editor_session\pathfinder.session.json `
  --file .\pathfinder_text_editor_session\wire-text-session-scripts.py `
  --autosave
```

## 14. Delivery Checklist

Before packaging or handing a session to another developer:

- All state images exist and have the expected dimensions.
- `pathfinder.manifest.json` has stable state ids.
- `bootstrap_sequence` starts at the intended boot state.
- Every required hook has `source_path`.
- Every hook file compiles.
- The workspace rebuild succeeds.
- The session store is either intentionally populated or reset clean.
- The GUI launches with the expected manifest and session.
- At least one programmatic smoke test has exercised create, read, update, delete, plugin dispatch, configuration, and persistence.

For the current text-editor-session, those checks have been performed and the delivered store is reset to a clean starter state.
