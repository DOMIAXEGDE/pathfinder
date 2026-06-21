"""
Install the Pathfinder text editor session behavior.

Run from the repository or installed Pathfinder app:

  pathfinder script --manifest pathfinder.manifest.json --session pathfinder.session.json --file text-session-instruct.py --autosave

This instruction script installs singular CRUD, batch CRUD, configuration,
styling, persistence, and .py plugin hooks into the Pathfinder manifest.
"""

from __future__ import annotations

from pathlib import Path
import json


if "api" not in globals():
    raise SystemExit("This file is a Pathfinder instruction script. Run it through: pathfinder script --file text-session-instruct.py")


PROJECT_DIR = Path(manifest.get("output_directory", manifest_path.parent)).resolve()
STORE_PATH = PROJECT_DIR / "text-session-store.json"
CONFIG_PATH = PROJECT_DIR / "text-session-config.json"
PLUGINS_DIR = PROJECT_DIR / "plugins"
EXPORTS_DIR = PROJECT_DIR / "exports"
SCRIPTS_DIR = PROJECT_DIR / "scripts"


STATE_BY_OPERATION = {
    state.get("editor_operation"): state["id"]
    for state in manifest.get("image_states", [])
    if state.get("editor_operation")
}


SCRIPT_HOOKS = {
    "crud.create": ("input", "text-session:singular-create", SCRIPTS_DIR / "input" / "singular_create.py"),
    "crud.read": ("output", "text-session:singular-read", SCRIPTS_DIR / "output" / "singular_read.py"),
    "crud.update": ("process", "text-session:singular-update", SCRIPTS_DIR / "process" / "singular_update.py"),
    "crud.delete": ("process", "text-session:singular-delete", SCRIPTS_DIR / "process" / "singular_delete.py"),
    "batch.create": ("input", "text-session:batch-create", SCRIPTS_DIR / "input" / "batch_create.py"),
    "batch.read": ("output", "text-session:batch-read-export", SCRIPTS_DIR / "output" / "batch_read.py"),
    "batch.update": ("process", "text-session:batch-update", SCRIPTS_DIR / "process" / "batch_update.py"),
    "batch.delete": ("process", "text-session:batch-delete", SCRIPTS_DIR / "process" / "batch_delete.py"),
    "python.plugins": ("process", "text-session:python-plugin-dispatch", SCRIPTS_DIR / "process" / "python_plugins.py"),
    "config.style": ("process", "text-session:configuration-style", SCRIPTS_DIR / "process" / "config_style.py"),
    "session.persistence": ("output", "text-session:persistence-summary", SCRIPTS_DIR / "output" / "session_persistence.py"),
}


DEFAULT_STORE = {
    "type": "pathfinder-text-session-store-v1",
    "documents": {},
    "history": [],
}


DEFAULT_CONFIG = {
    "type": "pathfinder-text-session-config-v1",
    "style": {
        "font_family": "Consolas",
        "font_size": 13,
        "foreground": "#101828",
        "background": "#FFFFFF",
        "accent": "#35B7A6",
        "line_numbers": True,
        "wrap": "word",
    },
    "behaviors": {
        "autosave": True,
        "archive_on_delete": True,
        "plugin_autoload": True,
        "default_extension": ".txt",
        "batch_export_format": "json",
    },
    "plugins": {
        "directory": str(PLUGINS_DIR),
        "enabled": True,
    },
}


COMMON = r'''
project_dir = Path(manifest.get("output_directory", manifest_path.parent if "manifest_path" in globals() else ".")).resolve()
store_path = Path(manifest.setdefault("text_editor_session", {}).get("store_path") or project_dir / "text-session-store.json")
config_path = Path(manifest.setdefault("text_editor_session", {}).get("config_path") or project_dir / "text-session-config.json")
plugins_dir = Path(manifest.setdefault("text_editor_session", {}).get("plugins_dir") or project_dir / "plugins")
exports_dir = project_dir / "exports"
plugins_dir.mkdir(parents=True, exist_ok=True)
exports_dir.mkdir(parents=True, exist_ok=True)

def _read_json(path, default):
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(json.dumps(default))

def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import os
    import uuid
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()

store = _read_json(store_path, {"type": "pathfinder-text-session-store-v1", "documents": {}, "history": []})
config = _read_json(config_path, {"type": "pathfinder-text-session-config-v1", "style": {}, "behaviors": {}, "plugins": {}})
payload = event.get("payload", {}) if isinstance(event, dict) else {}
if not isinstance(payload, dict):
    payload = {"value": payload}

def _record(action, detail):
    store.setdefault("history", []).append({
        "at": now_utc(),
        "state": state_id,
        "action": action,
        "detail": detail,
    })

def _documents():
    return store.setdefault("documents", {})

def _select_ids():
    docs = _documents()
    ids = payload.get("ids")
    if isinstance(ids, str):
        return [ids]
    if isinstance(ids, list):
        return [str(item) for item in ids if str(item) in docs]
    query = str(payload.get("query", "")).lower()
    if query:
        return [
            doc_id for doc_id, doc in docs.items()
            if query in doc_id.lower()
            or query in str(doc.get("title", "")).lower()
            or query in str(doc.get("content", "")).lower()
        ]
    if payload.get("all"):
        return list(docs.keys())
    doc_id = payload.get("id")
    return [str(doc_id)] if doc_id is not None else []

def _save():
    _write_json(store_path, store)
    _write_json(config_path, config)
    manifest.setdefault("text_editor_session", {})["store_path"] = str(store_path)
    manifest.setdefault("text_editor_session", {})["config_path"] = str(config_path)
    manifest.setdefault("text_editor_session", {})["plugins_dir"] = str(plugins_dir)
'''


HOOKS = {
    "crud.create": (
        "input",
        "text-session:singular-create",
        COMMON
        + r'''
docs = _documents()
doc_id = str(payload.get("id") or payload.get("name") or f"doc-{len(docs) + 1:04d}")
if doc_id in docs and not payload.get("replace"):
    raise ValueError(f"document already exists: {doc_id}")
docs[doc_id] = {
    "id": doc_id,
    "title": payload.get("title", doc_id),
    "content": payload.get("content", ""),
    "metadata": payload.get("metadata", {}),
    "created_at": now_utc(),
    "updated_at": now_utc(),
    "revisions": [],
}
_record("create", {"id": doc_id})
_save()
emit({"created": doc_id, "count": len(docs)})
''',
    ),
    "crud.read": (
        "output",
        "text-session:singular-read",
        COMMON
        + r'''
docs = _documents()
doc_id = payload.get("id")
if doc_id is None:
    emit({"documents": list(docs.values()), "count": len(docs)})
else:
    doc_id = str(doc_id)
    if doc_id not in docs:
        raise KeyError(f"document not found: {doc_id}")
    _record("read", {"id": doc_id})
    _save()
    emit(docs[doc_id])
''',
    ),
    "crud.update": (
        "process",
        "text-session:singular-update",
        COMMON
        + r'''
docs = _documents()
doc_id = str(payload.get("id"))
if doc_id not in docs:
    raise KeyError(f"document not found: {doc_id}")
doc = docs[doc_id]
doc.setdefault("revisions", []).append({"at": now_utc(), "content": doc.get("content", "")})
content = str(doc.get("content", ""))
if "content" in payload:
    content = str(payload["content"])
if "append" in payload:
    content += str(payload["append"])
if "prepend" in payload:
    content = str(payload["prepend"]) + content
if "find" in payload:
    content = content.replace(str(payload.get("find", "")), str(payload.get("replace", "")))
doc["content"] = content
doc["title"] = payload.get("title", doc.get("title", doc_id))
doc["metadata"] = {**doc.get("metadata", {}), **payload.get("metadata", {})}
doc["updated_at"] = now_utc()
_record("update", {"id": doc_id})
_save()
emit({"updated": doc_id, "length": len(content)})
''',
    ),
    "crud.delete": (
        "process",
        "text-session:singular-delete",
        COMMON
        + r'''
docs = _documents()
doc_id = str(payload.get("id"))
if doc_id not in docs:
    raise KeyError(f"document not found: {doc_id}")
deleted = docs.pop(doc_id)
if config.get("behaviors", {}).get("archive_on_delete", True) or payload.get("archive"):
    archive = store.setdefault("deleted_archive", [])
    archive.append({"at": now_utc(), "document": deleted})
_record("delete", {"id": doc_id})
_save()
emit({"deleted": doc_id, "remaining": len(docs)})
''',
    ),
    "batch.create": (
        "input",
        "text-session:batch-create",
        COMMON
        + r'''
docs = _documents()
incoming = payload.get("documents") or []
if not incoming:
    incoming = [
        {"id": "batch-0001", "title": "Batch document 1", "content": "Generated by batch create."},
        {"id": "batch-0002", "title": "Batch document 2", "content": "Generated by batch create."},
    ]
created = []
for item in incoming:
    doc_id = str(item.get("id") or item.get("name") or f"doc-{len(docs) + 1:04d}")
    docs[doc_id] = {
        "id": doc_id,
        "title": item.get("title", doc_id),
        "content": item.get("content", ""),
        "metadata": item.get("metadata", {}),
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "revisions": [],
    }
    created.append(doc_id)
_record("batch-create", {"ids": created})
_save()
emit({"created": created, "count": len(created)})
''',
    ),
    "batch.read": (
        "output",
        "text-session:batch-read-export",
        COMMON
        + r'''
docs = _documents()
ids = _select_ids() or list(docs.keys())
selected = [docs[doc_id] for doc_id in ids if doc_id in docs]
export_path = None
if payload.get("export", True):
    export_path = exports_dir / str(payload.get("export_name", "batch-read.json"))
    export_path.write_text(json.dumps(selected, indent=2, ensure_ascii=False), encoding="utf-8")
_record("batch-read", {"ids": ids, "export_path": str(export_path) if export_path else None})
_save()
emit({"documents": selected, "count": len(selected), "export_path": str(export_path) if export_path else None})
''',
    ),
    "batch.update": (
        "process",
        "text-session:batch-update",
        COMMON
        + r'''
docs = _documents()
ids = _select_ids()
if not ids and payload.get("all", True):
    ids = list(docs.keys())
updated = []
for doc_id in ids:
    if doc_id not in docs:
        continue
    doc = docs[doc_id]
    doc.setdefault("revisions", []).append({"at": now_utc(), "content": doc.get("content", "")})
    content = str(doc.get("content", ""))
    if "find" in payload:
        content = content.replace(str(payload.get("find", "")), str(payload.get("replace", "")))
    if "prefix" in payload:
        content = str(payload["prefix"]) + content
    if "suffix" in payload:
        content = content + str(payload["suffix"])
    transform = payload.get("transform")
    if transform == "upper":
        content = content.upper()
    elif transform == "lower":
        content = content.lower()
    elif transform == "title":
        content = content.title()
    doc["content"] = content
    doc["updated_at"] = now_utc()
    updated.append(doc_id)
_record("batch-update", {"ids": updated})
_save()
emit({"updated": updated, "count": len(updated)})
''',
    ),
    "batch.delete": (
        "process",
        "text-session:batch-delete",
        COMMON
        + r'''
docs = _documents()
ids = _select_ids()
deleted = []
archive = store.setdefault("deleted_archive", [])
for doc_id in ids:
    if doc_id in docs:
        doc = docs.pop(doc_id)
        deleted.append(doc_id)
        if config.get("behaviors", {}).get("archive_on_delete", True) or payload.get("archive", True):
            archive.append({"at": now_utc(), "document": doc})
_record("batch-delete", {"ids": deleted})
_save()
emit({"deleted": deleted, "count": len(deleted), "remaining": len(docs)})
''',
    ),
    "python.plugins": (
        "process",
        "text-session:python-plugin-dispatch",
        COMMON
        + r'''
results = []
for plugin_path in sorted(plugins_dir.glob("*.py")):
    ns = {
        "manifest": manifest,
        "store": store,
        "config": config,
        "payload": payload,
        "event": event,
        "cursor": cursor,
        "project_dir": project_dir,
        "Path": Path,
        "json": json,
        "now_utc": now_utc,
        "emit": emit,
    }
    exec(compile(plugin_path.read_text(encoding="utf-8"), str(plugin_path), "exec"), ns, ns)
    result = None
    if callable(ns.get("configure")):
        result = ns["configure"](config)
    if callable(ns.get("style")):
        style_result = ns["style"](config.get("style", {}))
        if isinstance(style_result, dict):
            config.setdefault("style", {}).update(style_result)
            result = style_result
    if callable(ns.get("handle")):
        result = ns["handle"]({"store": store, "config": config, "payload": payload, "manifest": manifest})
    results.append({"plugin": plugin_path.name, "result": result})
_record("plugins", {"plugins": [item["plugin"] for item in results]})
_save()
emit({"plugins": results, "count": len(results)})
''',
    ),
    "config.style": (
        "process",
        "text-session:configuration-style",
        COMMON
        + r'''
config.setdefault("style", {}).update(payload.get("style", {}))
config.setdefault("behaviors", {}).update(payload.get("behaviors", {}))
if payload.get("reset"):
    config["style"] = {
        "font_family": "Consolas",
        "font_size": 13,
        "foreground": "#101828",
        "background": "#FFFFFF",
        "accent": "#35B7A6",
        "line_numbers": True,
        "wrap": "word",
    }
_record("configure", {"style": config.get("style", {}), "behaviors": config.get("behaviors", {})})
_save()
emit(config)
''',
    ),
    "session.persistence": (
        "output",
        "text-session:persistence-summary",
        COMMON
        + r'''
summary = {
    "manifest": str(manifest_path),
    "session": str(session_path) if session_path else None,
    "store": str(store_path),
    "config": str(config_path),
    "plugins": str(plugins_dir),
    "document_count": len(_documents()),
    "history_count": len(store.get("history", [])),
}
summary_path = project_dir / "text-session-summary.json"
summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
_record("persist", {"summary_path": str(summary_path)})
_save()
emit(summary)
''',
    ),
}


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import os
    import uuid
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()


def ensure_defaults() -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_PATH.exists():
        write_json(STORE_PATH, DEFAULT_STORE)
    if not CONFIG_PATH.exists():
        write_json(CONFIG_PATH, DEFAULT_CONFIG)
    sample_plugin = PLUGINS_DIR / "example_text_plugin.py"
    if not sample_plugin.exists():
        sample_plugin.write_text(
            '''"""Example Pathfinder text session plugin."""

def style(style_config):
    return {"accent": "#7B61FF"}

def handle(editor):
    editor["config"].setdefault("behaviors", {})["example_plugin_seen"] = True
    return {"example_plugin": "ok"}
''',
            encoding="utf-8",
        )
    manifest.setdefault("text_editor_session", {})
    manifest["text_editor_session"].update(
        {
            "store_path": str(STORE_PATH),
            "config_path": str(CONFIG_PATH),
            "plugins_dir": str(PLUGINS_DIR),
            "exports_dir": str(EXPORTS_DIR),
            "scripts_dir": str(SCRIPTS_DIR),
            "instruction_script": str(Path(__file__).resolve()),
        }
    )


def restore_default_sequence() -> None:
    def sort_key(state):
        text = str(state.get("id", ""))
        if text.startswith("I") and text[1:].isdigit():
            return int(text[1:])
        return int(state.get("index", 0))

    manifest["bootstrap_sequence"] = [
        state["id"]
        for state in sorted(manifest.get("image_states", []), key=sort_key)
        if state.get("id")
    ]


def install_hooks() -> None:
    for state in manifest.get("image_states", []):
        state_id = state["id"]
        for hook in list(api.list_hooks(state_id)):
            if str(hook.get("name", "")).startswith("text-session:"):
                api.delete_hook(state_id, hook["id"])

    for operation, (kind, name, script_path) in SCRIPT_HOOKS.items():
        state_id = STATE_BY_OPERATION.get(operation)
        if not state_id:
            continue
        script_path = script_path.resolve()
        if not script_path.exists():
            raise FileNotFoundError(f"Missing text session hook script: {script_path}")
        code = script_path.read_text(encoding="utf-8")
        api.add_hook(kind, state_id, name, code, event_type="python", source_path=str(script_path))


ensure_defaults()
restore_default_sequence()
install_hooks()
api.set_cursor("I0")
api.save_session(PROJECT_DIR / "pathfinder.session.json")
api.save()

result = {
    "installed": "pathfinder-text-editor-session",
    "manifest": str(manifest_path),
    "session": str(PROJECT_DIR / "pathfinder.session.json"),
    "store": str(STORE_PATH),
    "config": str(CONFIG_PATH),
    "plugins": str(PLUGINS_DIR),
    "scripts": str(SCRIPTS_DIR),
    "states": len(manifest.get("image_states", [])),
    "hooks": sum(len(api.list_hooks(state["id"])) for state in manifest.get("image_states", [])),
}
