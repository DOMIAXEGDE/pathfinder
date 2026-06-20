#!/usr/bin/env python3
"""
Generate the Pathfinder text editor session file-set.

Outputs:
  states/*.png
  pathfinder.manifest.json
  pathfinder.session.json
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
STATES_DIR = ROOT / "states"
SIDE = 700
MANIFEST_TYPE = "pathfinder-manifest-v1"
SESSION_TYPE = "pathfinder-session-v1"
PROGRAMMING_TYPE = "pathfinder-state-programming-v1"


STATES: List[Dict[str, Any]] = [
    {
        "title": "Text Session",
        "subtitle": "single document and batch document workspace",
        "operation": "home",
        "bullets": ["state cursor", "session persistence", "Python instruction scripts", "plugin extensibility"],
        "accent": "#35B7A6",
    },
    {
        "title": "Create",
        "subtitle": "singular document creation",
        "operation": "crud.create",
        "bullets": ["new document id", "title and body", "metadata", "created timestamp"],
        "accent": "#3A86FF",
    },
    {
        "title": "Read",
        "subtitle": "singular document lookup",
        "operation": "crud.read",
        "bullets": ["open by id", "inspect metadata", "emit content", "export view"],
        "accent": "#7B61FF",
    },
    {
        "title": "Update",
        "subtitle": "singular document editing",
        "operation": "crud.update",
        "bullets": ["replace text", "append/prepend", "find and replace", "revision history"],
        "accent": "#FFB000",
    },
    {
        "title": "Delete",
        "subtitle": "singular document deletion",
        "operation": "crud.delete",
        "bullets": ["delete by id", "archive option", "history event", "safe confirmation payload"],
        "accent": "#F45B69",
    },
    {
        "title": "Batch Create",
        "subtitle": "multi-document creation/import",
        "operation": "batch.create",
        "bullets": ["document list", "folder import", "id policy", "bulk metadata"],
        "accent": "#00A676",
    },
    {
        "title": "Batch Read",
        "subtitle": "search, filter, and export",
        "operation": "batch.read",
        "bullets": ["query documents", "filter ids", "export json/txt", "batch preview"],
        "accent": "#118AB2",
    },
    {
        "title": "Batch Update",
        "subtitle": "transform many documents",
        "operation": "batch.update",
        "bullets": ["prefix/suffix", "find and replace", "case transforms", "plugin transforms"],
        "accent": "#FB8500",
    },
    {
        "title": "Batch Delete",
        "subtitle": "remove or archive many documents",
        "operation": "batch.delete",
        "bullets": ["delete ids", "delete by query", "archive batch", "undo material"],
        "accent": "#D62828",
    },
    {
        "title": "Python Scripts",
        "subtitle": "instruction scripts and plugins",
        "operation": "python.plugins",
        "bullets": [".py instruction scripts", ".py plugin folder", "alter config/style", "alter behavior"],
        "accent": "#9B5DE5",
    },
    {
        "title": "Configuration",
        "subtitle": "style and behavior profile",
        "operation": "config.style",
        "bullets": ["theme tokens", "key behavior flags", "storage paths", "render preferences"],
        "accent": "#2EC4B6",
    },
    {
        "title": "Persistence",
        "subtitle": "continue one or many projects",
        "operation": "session.persistence",
        "bullets": ["pathfinder.session.json", "project registry", "state cursor", "recent scripts"],
        "accent": "#4D908E",
    },
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for item in candidates:
        path = Path(item)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def draw_wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font_obj: ImageFont.ImageFont, fill: str, width: int, line_gap: int = 8) -> int:
    x, y = xy
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if draw.textlength(candidate, font=font_obj) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    for line in lines:
        draw.text((x, y), line, font=font_obj, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font_obj)
        y += (bbox[3] - bbox[1]) + line_gap
    return y


def create_state_image(index: int, state: Dict[str, Any], output_path: Path) -> Image.Image:
    accent = state["accent"]
    image = Image.new("RGB", (SIDE, SIDE), "#F6F7F9")
    draw = ImageDraw.Draw(image)
    title_font = font(54, bold=True)
    subtitle_font = font(24)
    small_font = font(18)
    bullet_font = font(26)
    mono_font = font(22, bold=True)

    # Deterministic editor-grid background.
    for y in range(0, SIDE, 28):
        shade = 232 if (y // 28) % 2 == 0 else 238
        draw.line((0, y, SIDE, y), fill=(shade, shade, shade), width=1)
    for x in range(0, SIDE, 28):
        draw.line((x, 0, x, SIDE), fill="#E2E7EC", width=1)

    draw.rounded_rectangle((32, 32, 668, 668), radius=18, fill="#FFFFFF", outline="#CBD5DF", width=2)
    draw.rectangle((32, 32, 668, 118), fill="#172033")
    draw.rectangle((32, 114, 668, 122), fill=accent)
    draw.text((56, 54), f"I{index}", font=mono_font, fill=accent)
    draw.text((128, 48), state["title"], font=title_font, fill="#FFFFFF")
    draw.text((56, 138), state["subtitle"], font=subtitle_font, fill="#344054")

    draw.rounded_rectangle((56, 196, 644, 322), radius=12, fill="#F2F6FA", outline="#D8E0E8", width=1)
    draw.text((80, 220), "operation", font=small_font, fill="#667085")
    draw.text((80, 252), state["operation"], font=font(34, bold=True), fill="#101828")

    y = 366
    for bullet in state["bullets"]:
        draw.ellipse((62, y + 8, 78, y + 24), fill=accent)
        y = draw_wrapped(draw, (96, y), bullet, bullet_font, "#101828", 500, line_gap=6) + 18

    draw.rounded_rectangle((56, 594, 644, 638), radius=8, fill="#101828")
    draw.text((78, 604), "Pathfinder text editor session state image | 700 x 700", font=small_font, fill="#FFFFFF")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return image


def state_programming(state_ids: Iterable[str]) -> Dict[str, Any]:
    return {
        "type": "pathfinder-state-programming-v1",
        "version": 1,
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "states": {state_id: {"input_events": [], "processors": [], "output_events": []} for state_id in state_ids},
    }


def main() -> int:
    state_records = []
    state_ids = []
    STATES_DIR.mkdir(parents=True, exist_ok=True)

    for index, state in enumerate(STATES):
        state_id = f"I{index}"
        state_ids.append(state_id)
        image_path = STATES_DIR / f"I{index:04d}.png"
        image = create_state_image(index, state, image_path)
        state_records.append(
            {
                "id": state_id,
                "index": index,
                "label": state["title"],
                "editor_operation": state["operation"],
                "image_path": str(image_path.resolve()),
                "rgb_path": "",
                "hex_path": "",
                "side_length": SIDE,
                "pixel_count": SIDE * SIDE,
                "pixel_sha256": sha256_bytes(image.tobytes()),
                "image_file_sha256": sha256_file(image_path),
                "source_state": None if index == 0 else f"I{index - 1}",
                "transform_index": None if index == 0 else index,
            }
        )

    manifest_path = ROOT / "pathfinder.manifest.json"
    session_path = ROOT / "pathfinder.session.json"
    workspace_path = ROOT / "pathfinder.workspace.json"
    now = now_utc()
    manifest = {
        "type": MANIFEST_TYPE,
        "name": "Pathfinder Text Editor Session",
        "created_at": now,
        "architecture": "Pathfinder text editor session: singular CRUD, batch CRUD, Python instruction scripts, and Python plugin extensibility.",
        "seed_image": str((STATES_DIR / "I0000.png").resolve()),
        "output_directory": str(ROOT.resolve()),
        "image_side_length": SIDE,
        "grid_pattern_signature": {
            "source": "state-gen.py",
            "side_length": SIDE,
            "state_count": len(STATES),
            "state_titles": [state["title"] for state in STATES],
            "signature_sha256": sha256_bytes("|".join(state["operation"] for state in STATES).encode("utf-8")),
        },
        "image_states": state_records,
        "tensor_states": [{"state_id": rec["id"], "workspace_bank": "2", "workspace_register": str(rec["index"])} for rec in state_records],
        "transforms": [
            {
                "index": index,
                "from": f"I{index - 1}",
                "to": f"I{index}",
                "parameters": {"kind": "text-editor-session-transition", "operation": STATES[index]["operation"]},
            }
            for index in range(1, len(STATES))
        ],
        "basis": {
            "engine_path": "",
            "config_path": "",
            "json_path": "",
            "seed_file": "",
            "seed_build_path": "",
            "metadata": {"program": "state-gen.py text editor session generator"},
            "seed_metadata": {"basis_row_count": str(len(STATES)), "basis_address": "text-editor-session"},
            "B_raw": [],
            "B_residue": [],
            "B_raw_sha256": "",
            "B_residue_sha256": "",
        },
        "basis_addresses": ["text-editor-session"],
        "bootstrap_sequence": state_ids,
        "command_bindings": {
            "boot": "I0",
            "create": "I1",
            "read": "I2",
            "update": "I3",
            "delete": "I4",
            "batch-create": "I5",
            "batch-read": "I6",
            "batch-update": "I7",
            "batch-delete": "I8",
            "plugins": "I9",
            "config": "I10",
            "persist": "I11",
        },
        "runtime_surfaces": [{"id": "text-editor-runtime", "renderer": "tkinter-canvas", "state_source": "bootstrap_sequence"}],
        "quadtree_cells": [{"state_id": state_id, "cell_path": str(index)} for index, state_id in enumerate(state_ids)],
        "state_programming": state_programming(state_ids),
        "text_editor_session": {
            "store_path": str((ROOT / "text-session-store.json").resolve()),
            "config_path": str((ROOT / "text-session-config.json").resolve()),
            "plugins_dir": str((ROOT / "plugins").resolve()),
            "instruction_script": str((ROOT / "text-session-instruct.py").resolve()),
        },
        "validation_reports": [
            {"check": "state_image_size", "status": "ok", "side_length": SIDE},
            {"check": "text_editor_state_count", "status": "ok", "count": len(STATES)},
        ],
        "rollback_points": [{"sequence_index": index, "state_id": state_id} for index, state_id in enumerate(state_ids)],
        "workspace_path": str(workspace_path.resolve()),
        "workspace_pixel_mode": "paths",
    }
    session = {
        "type": SESSION_TYPE,
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "active_manifest_path": str(manifest_path.resolve()),
        "projects": [
            {
                "manifest_path": str(manifest_path.resolve()),
                "label": "pathfinder_text_editor_session",
                "added_at": now,
            }
        ],
        "state_cursor": {
            "manifest_path": str(manifest_path.resolve()),
            "state_id": "I0",
            "sequence_index": 0,
            "image_x": None,
            "image_y": None,
            "screen_x": None,
            "screen_y": None,
            "source": "state-gen.py",
            "payload": {},
            "updated_at": now,
        },
        "recent_instruction_scripts": [str((ROOT / "text-session-instruct.py").resolve())],
    }
    write_json(manifest_path, manifest)
    write_json(session_path, session)
    print(f"generated {manifest_path}")
    print(f"generated {session_path}")
    print(f"generated {len(STATES)} state images in {STATES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
