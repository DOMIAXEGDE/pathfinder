"""
Wire the Pathfinder text editor session hook scripts to their states.

Preferred use from the repository or installed Pathfinder app:

  pathfinder script --manifest pathfinder.manifest.json --session pathfinder.session.json --file wire-text-session-scripts.py --autosave

Direct maintenance use:

  python wire-text-session-scripts.py --manifest pathfinder.manifest.json --session pathfinder.session.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import py_compile
import uuid
from hashlib import sha256
from pathlib import Path
from typing import Any


HOOK_PREFIX = "text-session:"
SESSION_TYPE = "pathfinder-session-v1"
STATE_PROGRAMMING_TYPE = "pathfinder-state-programming-v1"

HOOK_COLLECTIONS = {
    "input": "input_events",
    "process": "processors",
    "output": "output_events",
}

SCRIPT_HOOKS = {
    "crud.create": ("input", "text-session:singular-create", "scripts/input/singular_create.py"),
    "crud.read": ("output", "text-session:singular-read", "scripts/output/singular_read.py"),
    "crud.update": ("process", "text-session:singular-update", "scripts/process/singular_update.py"),
    "crud.delete": ("process", "text-session:singular-delete", "scripts/process/singular_delete.py"),
    "batch.create": ("input", "text-session:batch-create", "scripts/input/batch_create.py"),
    "batch.read": ("output", "text-session:batch-read-export", "scripts/output/batch_read.py"),
    "batch.update": ("process", "text-session:batch-update", "scripts/process/batch_update.py"),
    "batch.delete": ("process", "text-session:batch-delete", "scripts/process/batch_delete.py"),
    "python.plugins": ("process", "text-session:python-plugin-dispatch", "scripts/process/python_plugins.py"),
    "config.style": ("process", "text-session:configuration-style", "scripts/process/config_style.py"),
    "session.persistence": ("output", "text-session:persistence-summary", "scripts/output/session_persistence.py"),
}

FALLBACK_STATE_IDS = {
    "crud.create": "I1",
    "crud.read": "I2",
    "crud.update": "I3",
    "crud.delete": "I4",
    "batch.create": "I5",
    "batch.read": "I6",
    "batch.update": "I7",
    "batch.delete": "I8",
    "python.plugins": "I9",
    "config.style": "I10",
    "session.persistence": "I11",
}


def now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()


def hook_id(kind: str, name: str) -> str:
    digest = sha256(f"{kind}:{name}:{now_utc()}:{uuid.uuid4().hex}".encode("utf-8")).hexdigest()[:10]
    return f"{kind}-{digest}"


def project_dir_for(manifest: dict[str, Any], manifest_path: Path) -> Path:
    return Path(manifest.get("output_directory") or manifest_path.parent).resolve()


def sort_state_key(state: dict[str, Any]) -> int:
    state_id = str(state.get("id", ""))
    if state_id.startswith("I") and state_id[1:].isdigit():
        return int(state_id[1:])
    try:
        return int(state.get("index", 0))
    except (TypeError, ValueError):
        return 0


def state_by_operation(manifest: dict[str, Any]) -> dict[str, str]:
    states = {str(state.get("id")) for state in manifest.get("image_states", [])}
    mapping = {
        state.get("editor_operation"): state["id"]
        for state in manifest.get("image_states", [])
        if state.get("editor_operation") and state.get("id")
    }
    for operation, fallback_id in FALLBACK_STATE_IDS.items():
        if operation not in mapping and fallback_id in states:
            mapping[operation] = fallback_id
    return mapping


def ensure_state_programming(manifest: dict[str, Any]) -> dict[str, Any]:
    programming = manifest.setdefault(
        "state_programming",
        {
            "type": STATE_PROGRAMMING_TYPE,
            "version": 1,
            "created_at": now_utc(),
            "updated_at": now_utc(),
            "states": {},
        },
    )
    programming.setdefault("type", STATE_PROGRAMMING_TYPE)
    programming.setdefault("version", 1)
    programming.setdefault("created_at", now_utc())
    programming.setdefault("states", {})
    programming["updated_at"] = now_utc()
    for state in manifest.get("image_states", []):
        record = programming["states"].setdefault(str(state["id"]), {})
        record.setdefault("input_events", [])
        record.setdefault("processors", [])
        record.setdefault("output_events", [])
    return programming


def remove_existing_text_session_hooks(manifest: dict[str, Any]) -> int:
    removed = 0
    programming = ensure_state_programming(manifest)
    for record in programming.get("states", {}).values():
        for collection in HOOK_COLLECTIONS.values():
            hooks = list(record.get(collection, []))
            kept = [hook for hook in hooks if not str(hook.get("name", "")).startswith(HOOK_PREFIX)]
            removed += len(hooks) - len(kept)
            record[collection] = kept
    if removed:
        programming["updated_at"] = now_utc()
    return removed


def make_hook(kind: str, name: str, script_path: Path) -> dict[str, Any]:
    code = script_path.read_text(encoding="utf-8")
    created_at = now_utc()
    return {
        "id": hook_id(kind, name),
        "kind": kind,
        "name": name,
        "event_type": "python",
        "language": "python",
        "enabled": True,
        "source_path": str(script_path),
        "code": code,
        "created_at": created_at,
        "updated_at": created_at,
        "last_run_at": None,
        "last_status": "never-run",
        "last_error": None,
    }


def validate_scripts(project_dir: Path) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for operation, (_kind, _name, rel_path) in SCRIPT_HOOKS.items():
        path = (project_dir / rel_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Missing hook script for {operation}: {path}")
        py_compile.compile(str(path), doraise=True)
        resolved[operation] = path
    py_compile.compile(str(project_dir / "scripts" / "text_session_runtime.py"), doraise=True)
    return resolved


def restore_default_sequence(manifest: dict[str, Any]) -> list[str]:
    sequence = [
        str(state["id"])
        for state in sorted(manifest.get("image_states", []), key=sort_state_key)
        if state.get("id")
    ]
    manifest["bootstrap_sequence"] = sequence
    return sequence


def update_manifest_paths(manifest: dict[str, Any], manifest_path: Path) -> dict[str, str]:
    project_dir = project_dir_for(manifest, manifest_path)
    paths = {
        "store_path": str((project_dir / "text-session-store.json").resolve()),
        "config_path": str((project_dir / "text-session-config.json").resolve()),
        "plugins_dir": str((project_dir / "plugins").resolve()),
        "exports_dir": str((project_dir / "exports").resolve()),
        "scripts_dir": str((project_dir / "scripts").resolve()),
        "wiring_script": str(Path(__file__).resolve()),
    }
    for key in ("plugins_dir", "exports_dir", "scripts_dir"):
        Path(paths[key]).mkdir(parents=True, exist_ok=True)
    manifest.setdefault("text_editor_session", {}).update(paths)
    return paths


def wire_manifest_direct(manifest_path: Path, session_path: Path | None = None) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = read_json(manifest_path)
    project_dir = project_dir_for(manifest, manifest_path)
    script_paths = validate_scripts(project_dir)
    paths = update_manifest_paths(manifest, manifest_path)
    removed = remove_existing_text_session_hooks(manifest)
    mapping = state_by_operation(manifest)
    programming = ensure_state_programming(manifest)

    installed = []
    for operation, (kind, name, _rel_path) in SCRIPT_HOOKS.items():
        state_id = mapping.get(operation)
        if not state_id:
            raise KeyError(f"No state found for editor operation {operation}")
        record = programming["states"][state_id]
        hook = make_hook(kind, name, script_paths[operation])
        record[HOOK_COLLECTIONS[kind]].append(hook)
        installed.append(
            {
                "operation": operation,
                "state_id": state_id,
                "kind": kind,
                "name": name,
                "source_path": str(script_paths[operation]),
            }
        )

    sequence = restore_default_sequence(manifest)
    write_json(manifest_path, manifest)

    if session_path:
        update_session_file(session_path.resolve(), manifest_path, sequence)

    return {
        "wired": len(installed),
        "removed": removed,
        "manifest": str(manifest_path),
        "session": str(session_path.resolve()) if session_path else None,
        "scripts": paths["scripts_dir"],
        "sequence": sequence,
        "hooks": installed,
    }


def update_session_file(session_path: Path, manifest_path: Path, sequence: list[str]) -> None:
    if session_path.exists():
        session = read_json(session_path)
    else:
        session = {
            "type": SESSION_TYPE,
            "version": 1,
            "created_at": now_utc(),
            "projects": [],
            "recent_instruction_scripts": [],
        }
    session.setdefault("type", SESSION_TYPE)
    session.setdefault("version", 1)
    session.setdefault("created_at", now_utc())
    session["updated_at"] = now_utc()
    session["active_manifest_path"] = str(manifest_path)
    projects = session.setdefault("projects", [])
    manifest_text = str(manifest_path)
    for project in projects:
        if project.get("manifest_path") == manifest_text:
            project["last_seen_at"] = now_utc()
            break
    else:
        projects.append(
            {
                "manifest_path": manifest_text,
                "label": manifest_path.parent.name or manifest_path.stem,
                "added_at": now_utc(),
                "last_seen_at": now_utc(),
            }
        )
    session["state_cursor"] = {
        "manifest_path": manifest_text,
        "state_id": sequence[0] if sequence else "",
        "sequence_index": 0,
        "image_x": None,
        "image_y": None,
        "screen_x": None,
        "screen_y": None,
        "source": "wire-text-session-scripts",
        "payload": {},
        "updated_at": now_utc(),
    }
    recent = session.setdefault("recent_instruction_scripts", [])
    script_text = str(Path(__file__).resolve())
    if script_text in recent:
        recent.remove(script_text)
    recent.insert(0, script_text)
    del recent[16:]
    write_json(session_path, session)


def wire_via_pathfinder_instruction() -> dict[str, Any]:
    manifest_path_value = Path(globals()["manifest_path"]).resolve()
    manifest_value = globals()["manifest"]
    project_dir = project_dir_for(manifest_value, manifest_path_value)
    script_paths = validate_scripts(project_dir)
    paths = update_manifest_paths(manifest_value, manifest_path_value)
    restore_default_sequence(manifest_value)

    mapping = state_by_operation(manifest_value)
    removed = 0
    for state in manifest_value.get("image_states", []):
        state_id = state["id"]
        for hook in list(api.list_hooks(state_id)):  # type: ignore[name-defined]
            if str(hook.get("name", "")).startswith(HOOK_PREFIX):
                if api.delete_hook(state_id, hook["id"]):  # type: ignore[name-defined]
                    removed += 1

    installed = []
    for operation, (kind, name, _rel_path) in SCRIPT_HOOKS.items():
        state_id = mapping.get(operation)
        if not state_id:
            raise KeyError(f"No state found for editor operation {operation}")
        script_path = script_paths[operation]
        hook = api.add_hook(  # type: ignore[name-defined]
            kind,
            state_id,
            name,
            script_path.read_text(encoding="utf-8"),
            event_type="python",
            source_path=str(script_path),
        )
        installed.append(
            {
                "operation": operation,
                "state_id": state_id,
                "kind": kind,
                "hook_id": hook["id"],
                "source_path": str(script_path),
            }
        )

    api.set_cursor("I0")  # type: ignore[name-defined]
    if globals().get("session_path"):
        api.save_session(globals()["session_path"])  # type: ignore[name-defined]
    api.save()  # type: ignore[name-defined]

    return {
        "wired": len(installed),
        "removed": removed,
        "manifest": str(manifest_path_value),
        "session": str(globals().get("session_path")) if globals().get("session_path") else None,
        "scripts": paths["scripts_dir"],
        "sequence": manifest_value.get("bootstrap_sequence", []),
        "hooks": installed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Wire text-editor-session Python hooks to Pathfinder states.")
    parser.add_argument("--manifest", default="pathfinder.manifest.json", help="Pathfinder manifest JSON")
    parser.add_argument("--session", help="Optional Pathfinder session JSON to update or create")
    args = parser.parse_args()
    result = wire_manifest_direct(Path(args.manifest), Path(args.session) if args.session else None)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if "api" in globals() and "manifest" in globals() and "manifest_path" in globals():
    result = wire_via_pathfinder_instruction()
elif __name__ == "__main__":
    raise SystemExit(main())
