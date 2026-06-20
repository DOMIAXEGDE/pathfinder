#!/usr/bin/env python3
"""
Pathfinder
----------

Portable CLI-commanded, Python-authorable graphical runtime orchestrator.

Pathfinder joins the existing square-image analyzers, the 16.cpp basis tensor
engine, and the 25.py Tensor workspace model into one command surface.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


APP_NAME = "Pathfinder"
MANIFEST_TYPE = "pathfinder-manifest-v1"
SESSION_TYPE = "pathfinder-session-v1"
STATE_PROGRAMMING_TYPE = "pathfinder-state-programming-v1"
WORKSPACE_TYPE = "tensor-workspace-v1"
COMPONENT_ORDER = ["p", "q", "m", "g", "alpha", "beta"]
HEX_ALPHABET = "0123456789abcdef"
HOOK_COLLECTIONS = {
    "input": "input_events",
    "process": "processors",
    "processing": "processors",
    "output": "output_events",
}

RGB_PATTERN = re.compile(
    r"^\s*(\d+)\s*:\s*rgb\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)\s*$",
    re.IGNORECASE,
)
HEX_PATTERN = re.compile(r"^\s*(\d+)\s*:\s*#?([0-9a-fA-F]{6})\s*$")


def repo_root() -> Path:
    if getattr(sys, "frozen", False):
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            return Path(bundle_dir).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def require_pillow():
    try:
        from PIL import Image, ImageDraw, ImageTk  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local install
        raise RuntimeError(
            "Pathfinder image commands require Pillow. Install Pillow or use a Python runtime "
            "that already provides PIL."
        ) from exc
    return Image, ImageDraw, ImageTk


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_json(data: Any) -> str:
    return sha256_text(json.dumps(data, sort_keys=True, separators=(",", ":")))


def as_abs(path: Path | str) -> str:
    return str(Path(path).resolve())


def shorten(value: str, length: int = 18) -> str:
    text = str(value)
    if len(text) <= length:
        return text
    keep = max(6, length - 3)
    return text[:keep] + "..."


def load_square_rgb(path: Path):
    Image, _, _ = require_pillow()
    image = Image.open(path).convert("RGB")
    width, height = image.size
    if width != height:
        raise ValueError(f"Seed image must be square; got {width} x {height}: {path}")
    return image


def create_demo_seed(path: Path, size: int = 32) -> Path:
    Image, ImageDraw, _ = require_pillow()
    size = max(4, int(size))
    image = Image.new("RGB", (size, size), "#101820")
    draw = ImageDraw.Draw(image)
    grid = max(2, size // 8)
    for y in range(size):
        for x in range(size):
            r = (x * 11 + y * 5 + (x ^ y) * 3) % 256
            g = (x * 7 + y * 13 + (x * y) % 97) % 256
            b = (x * 17 + y * 3 + ((x + y) * 9)) % 256
            if x % grid == 0 or y % grid == 0:
                r, g, b = 240 - (x * 3 % 90), 245 - (y * 2 % 100), 255
            if x == y or x + y == size - 1:
                r, g, b = 255, 220, 80
            image.putpixel((x, y), (r, g, b))
    draw.rectangle((0, 0, size - 1, size - 1), outline="#ffffff")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def pixel_hex_list(image) -> List[str]:
    return [f"#{r:02X}{g:02X}{b:02X}" for r, g, b in image_pixels(image)]


def image_pixels(image) -> List[Tuple[int, int, int]]:
    if hasattr(image, "get_flattened_data"):
        return list(image.get_flattened_data())
    return list(image.getdata())


def write_pixel_sequences(image, stem: str, out_dir: Path) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rgb_path = out_dir / f"{stem}.rgb.txt"
    hex_path = out_dir / f"{stem}.hex.txt"
    with rgb_path.open("w", encoding="utf-8") as rgb_file, hex_path.open("w", encoding="utf-8") as hex_file:
        for index, (r, g, b) in enumerate(image_pixels(image)):
            rgb_file.write(f"{index}: rgb({r}, {g}, {b})\n")
            hex_file.write(f"{index}: #{r:02X}{g:02X}{b:02X}\n")
    return rgb_path, hex_path


def parse_pixel_sequence(path: Path) -> List[Tuple[int, int, int]]:
    indexed: List[Tuple[int, Tuple[int, int, int]]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            rgb_match = RGB_PATTERN.match(stripped)
            hex_match = HEX_PATTERN.match(stripped)
            if rgb_match:
                index = int(rgb_match.group(1))
                rgb = tuple(int(rgb_match.group(i)) for i in range(2, 5))
                if any(v < 0 or v > 255 for v in rgb):
                    raise ValueError(f"RGB value outside 0..255 on line {line_no}: {stripped}")
                indexed.append((index, rgb))  # type: ignore[arg-type]
            elif hex_match:
                index = int(hex_match.group(1))
                raw = hex_match.group(2)
                indexed.append((index, (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))))
            else:
                raise ValueError(f"Invalid pixel record on line {line_no}: {stripped}")
    indexed.sort(key=lambda item: item[0])
    for expected, (actual, _) in enumerate(indexed):
        if actual != expected:
            raise ValueError(f"Invalid pixel index sequence: expected {expected}, found {actual}")
    return [rgb for _, rgb in indexed]


def reconstruct_image(sequence_path: Path, output_path: Path) -> Path:
    Image, _, _ = require_pillow()
    pixels = parse_pixel_sequence(sequence_path)
    side = math.isqrt(len(pixels))
    if side * side != len(pixels):
        raise ValueError(f"Pixel record count is not a square: {len(pixels)}")
    image = Image.new("RGB", (side, side))
    image.putdata(pixels)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


def channel_mean(values: Iterable[Tuple[int, int, int]]) -> Tuple[int, int, int]:
    data = list(values)
    if not data:
        return (0, 0, 0)
    return tuple(int(sum(pixel[i] for pixel in data) / len(data)) for i in range(3))  # type: ignore[return-value]


def grid_pattern_signature(image, source_path: Path) -> Dict[str, Any]:
    side = image.width
    pixels = image_pixels(image)
    row_hashes = []
    col_hashes = []
    row_brightness = []
    col_brightness = []
    for y in range(side):
        row = [image.getpixel((x, y)) for x in range(side)]
        row_hashes.append(sha256_bytes(bytes(v for rgb in row for v in rgb)))
        row_brightness.append(sum(sum(rgb) for rgb in row) / (side * 3))
    for x in range(side):
        col = [image.getpixel((x, y)) for y in range(side)]
        col_hashes.append(sha256_bytes(bytes(v for rgb in col for v in rgb)))
        col_brightness.append(sum(sum(rgb) for rgb in col) / (side * 3))

    def high_contrast_lines(values: List[float]) -> List[int]:
        if len(values) < 3:
            return []
        deltas = [abs(values[i] - values[i - 1]) for i in range(1, len(values))]
        threshold = (sum(deltas) / max(1, len(deltas))) * 1.8
        lines = [i for i, delta in enumerate(deltas, start=1) if delta >= threshold and delta > 12]
        return lines[:64]

    diagonal = [image.getpixel((i, i)) for i in range(side)]
    anti = [image.getpixel((i, side - 1 - i)) for i in range(side)]
    edge = (
        [image.getpixel((x, 0)) for x in range(side)]
        + [image.getpixel((x, side - 1)) for x in range(side)]
        + [image.getpixel((0, y)) for y in range(side)]
        + [image.getpixel((side - 1, y)) for y in range(side)]
    )
    corners = [
        image.getpixel((0, 0)),
        image.getpixel((side - 1, 0)),
        image.getpixel((0, side - 1)),
        image.getpixel((side - 1, side - 1)),
    ]
    return {
        "source_path": as_abs(source_path),
        "side_length": side,
        "pixel_count": side * side,
        "image_sha256": sha256_bytes(image.tobytes()),
        "row_hash_sha256": sha256_text("|".join(row_hashes)),
        "column_hash_sha256": sha256_text("|".join(col_hashes)),
        "diagonal_sha256": sha256_bytes(bytes(v for rgb in diagonal + anti for v in rgb)),
        "edge_sha256": sha256_bytes(bytes(v for rgb in edge for v in rgb)),
        "mean_rgb": list(channel_mean(pixels)),
        "corner_rgb": [list(pixel) for pixel in corners],
        "candidate_grid_rows": high_contrast_lines(row_brightness),
        "candidate_grid_columns": high_contrast_lines(col_brightness),
    }


def basis_chunks_from_signature(signature: Dict[str, Any], basis_rows: int) -> List[Dict[str, str]]:
    base = sha256_json(signature)
    rows = []
    for row_index in range(max(1, basis_rows)):
        row: Dict[str, str] = {}
        for component in COMPONENT_ORDER:
            digest = hashlib.sha256(f"{base}:{row_index}:{component}".encode("utf-8")).hexdigest()
            row[component] = digest
        rows.append(row)
    return rows


def make_image_basis_config(
    signature: Dict[str, Any],
    *,
    basis_rows: int,
    seed_length: int,
    seed_mode: str,
    seed_file: Path,
    basis_output_path: Path,
    normal_output_path: Path,
) -> Dict[str, Any]:
    components = {}
    for name in COMPONENT_ORDER:
        spec: Dict[str, Any] = {
            "alphabet": HEX_ALPHABET,
            "length": {"mode": "variable", "min": 1, "max": 64},
        }
        if name in {"p", "m", "alpha"}:
            spec["signed_mapping"] = "zigzag"
        else:
            spec["positive_mapping"] = "id_plus_one"
        components[name] = spec
    return {
        "version": 1,
        "instance_count": max(1, basis_rows),
        "components": components,
        "instances": basis_chunks_from_signature(signature, basis_rows),
        "seed": {
            "output_length": int(seed_length),
            "seed_file": as_abs(seed_file),
            "basis_output_path": as_abs(basis_output_path),
            "mode": seed_mode,
            "basis_policy": "ordered_with_repetition",
            "emit_generated_seed": True,
        },
        "output": {"format": "json", "path": as_abs(normal_output_path)},
    }


def normalized_basis_config(
    source_config: Optional[Path],
    signature: Dict[str, Any],
    *,
    basis_rows: int,
    seed_length: int,
    seed_mode: str,
    seed_file: Path,
    basis_output_path: Path,
    normal_output_path: Path,
) -> Dict[str, Any]:
    if source_config:
        config = read_json(source_config)
    else:
        config = make_image_basis_config(
            signature,
            basis_rows=basis_rows,
            seed_length=seed_length,
            seed_mode=seed_mode,
            seed_file=seed_file,
            basis_output_path=basis_output_path,
            normal_output_path=normal_output_path,
        )
    config.setdefault("seed", {})
    config["seed"]["output_length"] = int(seed_length)
    config["seed"]["seed_file"] = as_abs(seed_file)
    config["seed"]["basis_output_path"] = as_abs(basis_output_path)
    config["seed"]["mode"] = seed_mode
    config["seed"].setdefault("basis_policy", "ordered_with_repetition")
    config["seed"].setdefault("emit_generated_seed", True)
    config.setdefault("output", {})
    config["output"]["format"] = "json"
    config["output"]["path"] = as_abs(normal_output_path)
    if "instance_count" not in config and "instances" in config:
        config["instance_count"] = len(config["instances"])
    return config


def find_basis_engine(requested: Optional[str], build_dir: Path) -> Optional[Path]:
    candidates = []
    if requested:
        candidates.append(Path(requested))
    candidates.extend([repo_root() / "basis_tensor.exe", build_dir / "basis_tensor.exe"])
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    cpp = repo_root() / "16.cpp"
    gpp = shutil.which("g++")
    if cpp.exists() and gpp:
        out = build_dir / "basis_tensor.exe"
        cmd = [gpp, "-std=c++17", "-O2", "-static", "-s", str(cpp), "-o", str(out)]
        subprocess.run(cmd, check=True, cwd=str(repo_root()))
        if out.exists():
            return out.resolve()
    return None


@dataclass
class BasisRun:
    basis_exe: Path
    config_path: Path
    json_path: Path
    seed_file: Path
    seed_build_path: Path
    stdout: str
    seed_stdout: str


def run_basis_engine(
    basis_exe: Path,
    config_path: Path,
    json_path: Path,
    seed_file: Path,
    seed_build_path: Path,
    *,
    seed_length: int,
    seed_mode: str,
) -> BasisRun:
    normal_cmd = [
        str(basis_exe),
        "--config",
        str(config_path),
        "--out",
        str(json_path),
        "--json",
        "--write-seed-file",
        str(seed_file),
        "--seed-length",
        str(seed_length),
        "--seed-mode",
        seed_mode,
    ]
    normal = subprocess.run(normal_cmd, cwd=str(repo_root()), text=True, capture_output=True)
    if normal.returncode != 0:
        raise RuntimeError(
            "Basis tensor normal generation failed.\n"
            + normal.stdout
            + normal.stderr
            + "\nCommand: "
            + " ".join(shlex.quote(part) for part in normal_cmd)
        )

    seed_cmd = [
        str(basis_exe),
        "--config",
        str(config_path),
        "--from-seeds",
        "--seed-file",
        str(seed_file),
        "--basis-out",
        str(seed_build_path),
        "--seed-mode",
        seed_mode,
    ]
    seed = subprocess.run(seed_cmd, cwd=str(repo_root()), text=True, capture_output=True)
    if seed.returncode != 0:
        raise RuntimeError(
            "Basis tensor seed reconstruction failed.\n"
            + seed.stdout
            + seed.stderr
            + "\nCommand: "
            + " ".join(shlex.quote(part) for part in seed_cmd)
        )
    return BasisRun(basis_exe, config_path, json_path, seed_file, seed_build_path, normal.stdout, seed.stdout)


def basis_rows_as_ints(basis: Dict[str, Any]) -> List[List[int]]:
    rows = basis.get("B_raw") or basis.get("raw_basis_tensor_dataset") or []
    parsed: List[List[int]] = []
    for row in rows:
        if isinstance(row, list):
            nums = []
            for value in row:
                try:
                    nums.append(int(str(value)))
                except ValueError:
                    nums.append(int(sha256_text(str(value)), 16))
            if nums:
                parsed.append(nums)
    if parsed:
        return parsed
    fallback = int(sha256_json(basis), 16)
    return [[fallback, fallback >> 7, fallback >> 13, fallback >> 19, fallback >> 29, fallback >> 37]]


def coprime_stride(seed: int, count: int) -> int:
    if count <= 1:
        return 1
    stride = seed % count
    if stride == 0:
        stride = 1
    while math.gcd(stride, count) != 1:
        stride = (stride + 1) % count
        if stride == 0:
            stride = 1
    return stride


def basis_transform_image(image, basis: Dict[str, Any], iteration: int):
    Image, _, _ = require_pillow()
    rows = basis_rows_as_ints(basis)
    row_index = (iteration - 1) % len(rows)
    row = rows[row_index]
    seed_meta = basis.get("seed_metadata", {})
    entropy_material = {
        "iteration": iteration,
        "row_index": row_index,
        "row": [str(v) for v in row],
        "canonical_seed_sequence": seed_meta.get("canonical_seed_sequence", []),
    }
    entropy = int(sha256_json(entropy_material), 16)
    pixels = image_pixels(image)
    count = len(pixels)
    if count == 0:
        return image.copy(), {"row_index": row_index, "offset": 0, "stride": 1}
    offset = (row[0] + entropy) % count
    stride = coprime_stride(row[1 % len(row)] + (entropy >> 11), count)
    red_shift = (row[2 % len(row)] + (entropy >> 17)) & 255
    green_shift = (row[3 % len(row)] + (entropy >> 23)) & 255
    blue_shift = (row[4 % len(row)] + (entropy >> 31)) & 255
    mix = (row[5 % len(row)] + iteration + (entropy >> 41)) & 255
    mode = entropy % 4
    output = []
    for i in range(count):
        src = (offset + i * stride) % count
        r, g, b = pixels[src]
        coord = (i + 1) * (iteration + 3)
        if mode == 1:
            r, g, b = g, b, r
        elif mode == 2:
            r, g, b = b, r, g
        elif mode == 3:
            r, g, b = 255 - r, 255 - g, 255 - b
        output.append(
            (
                (r + red_shift + ((coord * (mix | 1)) & 255)) & 255,
                (g + green_shift + ((coord * 3 + mix) & 255)) & 255,
                (b + blue_shift + ((coord * 5 + (mix << 1)) & 255)) & 255,
            )
        )
    next_image = Image.new("RGB", image.size)
    next_image.putdata(output)
    return next_image, {
        "kind": "basis_tensor_pixel_permutation",
        "iteration": iteration,
        "basis_row_index": row_index,
        "offset": str(offset),
        "stride": str(stride),
        "channel_shift_rgb": [red_shift, green_shift, blue_shift],
        "mix": mix,
        "mode": int(mode),
        "row_sha256": sha256_text("|".join(str(v) for v in row)),
    }


def load_tensor_module():
    path = repo_root() / "25.py"
    if not path.exists():
        raise FileNotFoundError("25.py Tensor workspace module is missing")
    spec = importlib.util.spec_from_file_location("pathfinder_tensor25", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Tensor workspace module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def workspace_set(ws: Any, bank: str, register: str, address: str, value: Any, title: str = "") -> None:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    ws.set_value(str(bank), str(register), str(address), value, title=title)


def build_workspace_from_manifest(manifest: Dict[str, Any], pixel_mode: str = "compact") -> Any:
    tensor = load_tensor_module()
    ws = tensor.Workspace()
    workspace_set(ws, "1", "1", "type", manifest.get("type"), "pathfinder.manifest")
    workspace_set(ws, "1", "1", "created_at", manifest.get("created_at"), "pathfinder.manifest")
    workspace_set(ws, "1", "1", "seed_image", manifest.get("seed_image"), "pathfinder.manifest")
    workspace_set(ws, "1", "1", "side_length", manifest.get("image_side_length"), "pathfinder.manifest")
    workspace_set(ws, "1", "1", "grid_pattern_signature", manifest.get("grid_pattern_signature"), "pathfinder.manifest")

    for state in manifest.get("image_states", []):
        reg = str(state.get("index", "0"))
        for key in [
            "id",
            "image_path",
            "rgb_path",
            "hex_path",
            "side_length",
            "pixel_sha256",
            "source_state",
            "transform_index",
        ]:
            workspace_set(ws, "2", reg, key, state.get(key, ""), "image.states")
        if pixel_mode == "compact":
            hex_path = Path(state.get("hex_path", ""))
            if hex_path.exists():
                values = [line.split(":", 1)[1].strip() for line in hex_path.read_text(encoding="utf-8").splitlines() if ":" in line]
                workspace_set(ws, "2", reg, "pixels_hex_json", values, "image.states")

    basis = manifest.get("basis", {})
    workspace_set(ws, "3", "1", "engine", basis.get("engine_path", ""), "basis.tensor")
    workspace_set(ws, "3", "1", "config_path", basis.get("config_path", ""), "basis.tensor")
    workspace_set(ws, "3", "1", "json_path", basis.get("json_path", ""), "basis.tensor")
    workspace_set(ws, "3", "1", "seed_file", basis.get("seed_file", ""), "basis.tensor")
    workspace_set(ws, "3", "1", "seed_build_path", basis.get("seed_build_path", ""), "basis.tensor")
    workspace_set(ws, "3", "1", "seed_metadata", basis.get("seed_metadata", {}), "basis.tensor")
    workspace_set(ws, "3", "1", "B_raw_sha256", basis.get("B_raw_sha256", ""), "basis.tensor")
    for i, row in enumerate(basis.get("B_raw", [])):
        workspace_set(ws, "3", str(i), "B_raw", row, "basis.tensor")
    for i, row in enumerate(basis.get("B_residue", [])):
        workspace_set(ws, "3", str(i), "B_residue", row, "basis.tensor")

    for transform in manifest.get("transforms", []):
        reg = str(transform.get("index", "0"))
        workspace_set(ws, "4", reg, "from", transform.get("from"), "transforms")
        workspace_set(ws, "4", reg, "to", transform.get("to"), "transforms")
        workspace_set(ws, "4", reg, "parameters", transform.get("parameters"), "transforms")

    for i, state_id in enumerate(manifest.get("bootstrap_sequence", [])):
        workspace_set(ws, "5", "1", str(i), state_id, "bootstrap.sequence")
    for name, state_id in manifest.get("command_bindings", {}).items():
        workspace_set(ws, "5", "2", name, state_id, "bootstrap.sequence")

    for i, cell in enumerate(manifest.get("quadtree_cells", [])):
        workspace_set(ws, "6", str(i), "cell", cell, "runtime.surface")
    for i, report in enumerate(manifest.get("validation_reports", [])):
        workspace_set(ws, "7", str(i), "report", report, "validation.reports")

    programming = manifest.get("state_programming", {})
    for state_id, record in programming.get("states", {}).items():
        reg = str(state_id).lstrip("I") or str(state_id)
        workspace_set(ws, "8", reg, "state_id", state_id, "state.programming")
        workspace_set(ws, "8", reg, "input_events", record.get("input_events", []), "state.programming")
        workspace_set(ws, "8", reg, "processors", record.get("processors", []), "state.programming")
        workspace_set(ws, "8", reg, "output_events", record.get("output_events", []), "state.programming")
    ws.dirty = False
    return ws


def save_workspace(manifest: Dict[str, Any], workspace_path: Path, pixel_mode: str) -> Path:
    tensor = load_tensor_module()
    ensure_state_programming(manifest)
    ws = build_workspace_from_manifest(manifest, pixel_mode=pixel_mode)
    write_json(workspace_path, ws.to_dict(include_meta=True))
    renderer = tensor.TensorRenderer(tensor.load_config(None))
    summary = renderer.render(ws, "summary")
    workspace_path.with_suffix(".summary.txt").write_text(summary, encoding="utf-8")
    return workspace_path


def state_record(index: int, image_path: Path, rgb_path: Path, hex_path: Path, image, **extra: Any) -> Dict[str, Any]:
    record = {
        "id": f"I{index}",
        "index": index,
        "image_path": as_abs(image_path),
        "rgb_path": as_abs(rgb_path),
        "hex_path": as_abs(hex_path),
        "side_length": image.width,
        "pixel_count": image.width * image.height,
        "pixel_sha256": sha256_bytes(image.tobytes()),
        "image_file_sha256": sha256_file(image_path),
        "rgb_file_sha256": sha256_file(rgb_path),
        "hex_file_sha256": sha256_file(hex_path),
    }
    record.update(extra)
    return record


def quadtree_cells_for_states(states: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cells = []
    for state in states:
        index = int(state["index"])
        path_bits = []
        n = index
        if n == 0:
            path_bits.append(0)
        while n:
            path_bits.append(n % 4)
            n //= 4
        cells.append({"state_id": state["id"], "cell_path": ".".join(str(v) for v in reversed(path_bits))})
    return cells


def build_pathfinder(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).resolve()
    states_dir = out_dir / "states"
    basis_dir = out_dir / "basis"
    manifest_path = out_dir / "pathfinder.manifest.json"
    if manifest_path.exists() and not args.force:
        raise FileExistsError(f"{manifest_path} already exists. Use --force to overwrite Pathfinder outputs.")
    states_dir.mkdir(parents=True, exist_ok=True)
    basis_dir.mkdir(parents=True, exist_ok=True)

    if args.seed:
        seed_path = Path(args.seed).resolve()
    else:
        seed_path = create_demo_seed(out_dir / "seed.demo.png", size=args.demo_size).resolve()

    seed_image = load_square_rgb(seed_path)
    signature = grid_pattern_signature(seed_image, seed_path)

    basis_json_path = basis_dir / "basis_tensors.json"
    seed_file = basis_dir / "19.pathfinder-seed.txt"
    seed_build_path = basis_dir / "20.pathfinder-seed-build.txt"
    config_path = basis_dir / "pathfinder_basis_config.json"
    basis_config = normalized_basis_config(
        Path(args.basis_config).resolve() if args.basis_config else None,
        signature,
        basis_rows=args.basis_rows,
        seed_length=args.seed_length,
        seed_mode=args.seed_mode,
        seed_file=seed_file,
        basis_output_path=seed_build_path,
        normal_output_path=basis_json_path,
    )
    write_json(config_path, basis_config)

    basis_exe = find_basis_engine(args.basis_exe, basis_dir)
    if basis_exe is None:
        raise FileNotFoundError("Could not find or build basis_tensor.exe from 16.cpp")
    basis_run = run_basis_engine(
        basis_exe,
        config_path,
        basis_json_path,
        seed_file,
        seed_build_path,
        seed_length=args.seed_length,
        seed_mode=args.seed_mode,
    )
    basis = read_json(basis_json_path)

    states: List[Dict[str, Any]] = []
    transforms: List[Dict[str, Any]] = []
    current = seed_image.copy()
    for index in range(args.iterations + 1):
        stem = f"I{index:04d}"
        image_path = states_dir / f"{stem}.png"
        current.save(image_path)
        rgb_path, hex_path = write_pixel_sequences(current, stem, states_dir)
        extra: Dict[str, Any] = {}
        if index == 0:
            extra.update({"source_state": None, "transform_index": None})
        else:
            extra.update({"source_state": f"I{index - 1}", "transform_index": index})
        states.append(state_record(index, image_path, rgb_path, hex_path, current, **extra))
        if index < args.iterations:
            next_image, params = basis_transform_image(current, basis, index + 1)
            transforms.append(
                {
                    "index": index + 1,
                    "from": f"I{index}",
                    "to": f"I{index + 1}",
                    "parameters": params,
                }
            )
            current = next_image

    workspace_path = out_dir / "pathfinder.workspace.json"
    manifest: Dict[str, Any] = {
        "type": MANIFEST_TYPE,
        "name": APP_NAME,
        "created_at": now_utc(),
        "architecture": (
            "Portable CLI-commanded, Python-authorable graphical OS runtime derived from a "
            "square seed image, basis-tensor transformations, indexed image states, and an "
            "editable bootstrap sequence."
        ),
        "seed_image": as_abs(seed_path),
        "output_directory": as_abs(out_dir),
        "image_side_length": seed_image.width,
        "grid_pattern_signature": signature,
        "image_states": states,
        "tensor_states": [{"state_id": state["id"], "workspace_bank": "2", "workspace_register": str(state["index"])} for state in states],
        "transforms": transforms,
        "basis": {
            "engine_path": as_abs(basis_run.basis_exe),
            "config_path": as_abs(basis_run.config_path),
            "json_path": as_abs(basis_run.json_path),
            "seed_file": as_abs(basis_run.seed_file),
            "seed_build_path": as_abs(basis_run.seed_build_path),
            "metadata": basis.get("metadata", {}),
            "seed_metadata": basis.get("seed_metadata", {}),
            "B_raw": basis.get("B_raw", []),
            "B_residue": basis.get("B_residue", []),
            "B_raw_sha256": sha256_json(basis.get("B_raw", [])),
            "B_residue_sha256": sha256_json(basis.get("B_residue", [])),
        },
        "basis_addresses": basis.get("seed_metadata", {}).get("canonical_seed_sequence", []),
        "bootstrap_sequence": [state["id"] for state in states],
        "command_bindings": {"boot": states[0]["id"], "latest": states[-1]["id"]},
        "runtime_surfaces": [{"id": "tk-runtime", "renderer": "tkinter-canvas", "state_source": "bootstrap_sequence"}],
        "quadtree_cells": quadtree_cells_for_states(states),
        "state_programming": default_state_programming(state["id"] for state in states),
        "validation_reports": [
            {"check": "square_seed", "status": "ok", "side_length": seed_image.width},
            {"check": "basis_tensor_json", "status": "ok", "path": as_abs(basis_json_path)},
            {"check": "state_count", "status": "ok", "count": len(states)},
        ],
        "rollback_points": [{"sequence_index": i, "state_id": state["id"]} for i, state in enumerate(states)],
        "workspace_path": as_abs(workspace_path),
        "workspace_pixel_mode": args.workspace_pixel_mode,
    }
    write_json(manifest_path, manifest)
    save_workspace(manifest, workspace_path, args.workspace_pixel_mode)
    print(f"Pathfinder build complete: {manifest_path}")
    print(f"States: {len(states)} | side: {seed_image.width} | workspace: {workspace_path}")
    return 0


def load_manifest(path: Path) -> Dict[str, Any]:
    manifest = read_json(path)
    if manifest.get("type") != MANIFEST_TYPE:
        raise ValueError(f"Not a Pathfinder manifest: {path}")
    ensure_state_programming(manifest)
    return manifest


def manifest_state_map(manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(state["id"]): state for state in manifest.get("image_states", [])}


def print_status(manifest: Dict[str, Any]) -> None:
    basis = manifest.get("basis", {})
    seed_meta = basis.get("seed_metadata", {})
    programming = manifest.get("state_programming", {})
    print(f"{manifest.get('name', APP_NAME)} manifest: {manifest.get('type')}")
    print(f"Seed: {manifest.get('seed_image')}")
    print(f"Output: {manifest.get('output_directory')}")
    print(f"Image side: {manifest.get('image_side_length')} | states: {len(manifest.get('image_states', []))}")
    print(f"Bootstrap sequence: {' -> '.join(manifest.get('bootstrap_sequence', []))}")
    print(f"Basis rows: {seed_meta.get('basis_row_count', len(basis.get('B_raw', [])))}")
    print(f"Basis address: {shorten(str(seed_meta.get('basis_address', '')), 36)}")
    print(f"Workspace: {manifest.get('workspace_path')}")
    print(f"Programmable states: {len(programming.get('states', {}))}")


def normalize_hook_kind(kind: str) -> str:
    raw = str(kind).strip().lower()
    if raw not in HOOK_COLLECTIONS:
        raise ValueError(f"Unknown programming hook kind: {kind}. Use input, process, or output.")
    if raw == "processing":
        return "process"
    return raw


def default_state_programming(state_ids: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    programming = {
        "type": STATE_PROGRAMMING_TYPE,
        "version": 1,
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "states": {},
    }
    for state_id in state_ids or []:
        programming["states"][str(state_id)] = {
            "input_events": [],
            "processors": [],
            "output_events": [],
        }
    return programming


def ensure_state_programming(manifest: Dict[str, Any]) -> Dict[str, Any]:
    state_ids = [str(state["id"]) for state in manifest.get("image_states", [])]
    programming = manifest.get("state_programming")
    if not isinstance(programming, dict):
        programming = default_state_programming(state_ids)
        manifest["state_programming"] = programming
    programming.setdefault("type", STATE_PROGRAMMING_TYPE)
    programming.setdefault("version", 1)
    programming.setdefault("created_at", now_utc())
    programming.setdefault("states", {})
    programming["updated_at"] = now_utc()
    for state_id in state_ids:
        ensure_state_programming_record(manifest, state_id)
    return programming


def ensure_state_programming_record(manifest: Dict[str, Any], state_id: str) -> Dict[str, Any]:
    programming = manifest.setdefault("state_programming", default_state_programming())
    states = programming.setdefault("states", {})
    record = states.setdefault(
        str(state_id),
        {"input_events": [], "processors": [], "output_events": []},
    )
    record.setdefault("input_events", [])
    record.setdefault("processors", [])
    record.setdefault("output_events", [])
    return record


def new_hook_id(kind: str, name: str) -> str:
    digest = sha256_text(f"{kind}:{name}:{now_utc()}:{uuid.uuid4().hex}")[:10]
    return f"{kind}-{digest}"


def make_programming_hook(
    kind: str,
    name: str,
    code: str,
    *,
    event_type: str = "python",
    enabled: bool = True,
    source_path: Optional[str] = None,
) -> Dict[str, Any]:
    normalized = normalize_hook_kind(kind)
    return {
        "id": new_hook_id(normalized, name),
        "kind": normalized,
        "name": name or f"{normalized} hook",
        "event_type": event_type or "python",
        "language": "python",
        "enabled": bool(enabled),
        "source_path": source_path,
        "code": code or "",
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "last_run_at": None,
        "last_status": "never-run",
        "last_error": None,
    }


def default_session_path_for_manifest(manifest_path: Path) -> Path:
    return manifest_path.resolve().parent / "pathfinder.session.json"


def create_session_data(manifest_path: Optional[Path] = None) -> Dict[str, Any]:
    now = now_utc()
    session = {
        "type": SESSION_TYPE,
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "active_manifest_path": as_abs(manifest_path) if manifest_path else None,
        "projects": [],
        "state_cursor": None,
        "recent_instruction_scripts": [],
    }
    if manifest_path:
        session["projects"].append(
            {
                "manifest_path": as_abs(manifest_path),
                "label": manifest_path.resolve().parent.name or manifest_path.stem,
                "added_at": now,
            }
        )
    return session


def load_session_file(path: Path) -> Dict[str, Any]:
    data = read_json(path)
    if data.get("type") != SESSION_TYPE:
        raise ValueError(f"Not a Pathfinder session file: {path}")
    data.setdefault("projects", [])
    data.setdefault("recent_instruction_scripts", [])
    return data


def save_session_file(path: Path, session: Dict[str, Any]) -> None:
    session["updated_at"] = now_utc()
    write_json(path, session)


def add_manifest_to_session(session: Dict[str, Any], manifest_path: Path, label: Optional[str] = None) -> None:
    resolved = as_abs(manifest_path)
    projects = session.setdefault("projects", [])
    for project in projects:
        if project.get("manifest_path") == resolved:
            project["label"] = label or project.get("label") or manifest_path.resolve().parent.name
            project["last_seen_at"] = now_utc()
            session["active_manifest_path"] = resolved
            return
    projects.append(
        {
            "manifest_path": resolved,
            "label": label or manifest_path.resolve().parent.name or manifest_path.stem,
            "added_at": now_utc(),
        }
    )
    session["active_manifest_path"] = resolved


def resolve_state_token(controller: "RuntimeController", token: Optional[str]) -> str:
    if token is None or token.lower() in {"current", "."}:
        state_id = controller.current_state_id()
        if state_id is None:
            raise ValueError("No current state is available.")
        return state_id
    state_map = manifest_state_map(controller.manifest)
    if token.isdigit():
        seq = controller.sequence
        index = int(token)
        if index < 0 or index >= len(seq):
            raise ValueError(f"Sequence index outside range: {index}")
        return seq[index]
    if token not in state_map:
        raise ValueError(f"Unknown state: {token}")
    return token


class RuntimeController:
    def __init__(self, manifest_path: Path, session_path: Optional[Path] = None, create_session: bool = False):
        self.manifest_path = manifest_path.resolve()
        self.manifest = load_manifest(self.manifest_path)
        ensure_state_programming(self.manifest)
        self.current_position = 0
        if create_session and session_path is None:
            session_path = default_session_path_for_manifest(self.manifest_path)
        self.session_path: Optional[Path] = session_path.resolve() if session_path else None
        self.session: Optional[Dict[str, Any]] = None
        self.state_cursor: Dict[str, Any] = {}
        if self.session_path:
            self.open_session(self.session_path, create=create_session)
        else:
            self.set_cursor(source="runtime-start")

    @property
    def sequence(self) -> List[str]:
        return list(self.manifest.get("bootstrap_sequence", []))

    def current_state_id(self) -> Optional[str]:
        seq = self.sequence
        if not seq:
            return None
        self.current_position %= len(seq)
        return seq[self.current_position]

    def current_state(self) -> Optional[Dict[str, Any]]:
        state_id = self.current_state_id()
        if state_id is None:
            return None
        return manifest_state_map(self.manifest).get(state_id)

    def save(self) -> None:
        ensure_state_programming(self.manifest)
        write_json(self.manifest_path, self.manifest)
        workspace_path = Path(self.manifest.get("workspace_path", self.manifest_path.with_suffix(".workspace.json")))
        save_workspace(self.manifest, workspace_path, self.manifest.get("workspace_pixel_mode", "compact"))
        if self.session_path and self.session:
            self.sync_session()
            save_session_file(self.session_path, self.session)

    def open_session(self, path: Path, create: bool = False) -> str:
        self.session_path = path.resolve()
        if self.session_path.exists():
            self.session = load_session_file(self.session_path)
        elif create:
            self.session = create_session_data(self.manifest_path)
            save_session_file(self.session_path, self.session)
        else:
            raise FileNotFoundError(f"Session file does not exist: {self.session_path}")
        add_manifest_to_session(self.session, self.manifest_path)
        cursor = self.session.get("state_cursor")
        if isinstance(cursor, dict) and cursor.get("manifest_path") == as_abs(self.manifest_path):
            state_id = cursor.get("state_id")
            if state_id in manifest_state_map(self.manifest):
                if state_id in self.sequence:
                    self.current_position = self.sequence.index(state_id)
                self.state_cursor = dict(cursor)
            else:
                self.set_cursor(source="session-open")
        else:
            self.set_cursor(source="session-open")
        self.sync_session()
        return f"session {self.session_path}"

    def sync_session(self) -> None:
        if not self.session:
            return
        add_manifest_to_session(self.session, self.manifest_path)
        self.session["state_cursor"] = dict(self.state_cursor)
        self.session["active_manifest_path"] = as_abs(self.manifest_path)
        self.session["updated_at"] = now_utc()

    def save_session(self, path: Optional[Path] = None) -> str:
        if path is not None:
            self.session_path = path.resolve()
        if self.session is None:
            self.session = create_session_data(self.manifest_path)
        if self.session_path is None:
            self.session_path = default_session_path_for_manifest(self.manifest_path)
        self.sync_session()
        save_session_file(self.session_path, self.session)
        return f"saved session {self.session_path}"

    def set_cursor(
        self,
        state_id: Optional[str] = None,
        *,
        image_x: Optional[int] = None,
        image_y: Optional[int] = None,
        screen_x: Optional[int] = None,
        screen_y: Optional[int] = None,
        source: str = "runtime",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        selected_state = state_id or self.current_state_id()
        if selected_state is None:
            selected_state = ""
        if selected_state and selected_state not in manifest_state_map(self.manifest):
            raise ValueError(f"Unknown state for cursor: {selected_state}")
        if selected_state in self.sequence:
            self.current_position = self.sequence.index(selected_state)
        self.state_cursor = {
            "manifest_path": as_abs(self.manifest_path),
            "state_id": selected_state,
            "sequence_index": self.current_position,
            "image_x": image_x,
            "image_y": image_y,
            "screen_x": screen_x,
            "screen_y": screen_y,
            "source": source,
            "payload": payload or {},
            "updated_at": now_utc(),
        }
        self.sync_session()
        return self.state_cursor

    def hook_collection(self, kind: str) -> str:
        return HOOK_COLLECTIONS[normalize_hook_kind(kind)]

    def add_hook(
        self,
        kind: str,
        state_id: str,
        name: str,
        code: str,
        *,
        event_type: str = "python",
        enabled: bool = True,
        source_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_state = resolve_state_token(self, state_id)
        record = ensure_state_programming_record(self.manifest, resolved_state)
        hook = make_programming_hook(kind, name, code, event_type=event_type, enabled=enabled, source_path=source_path)
        record[self.hook_collection(kind)].append(hook)
        self.manifest["state_programming"]["updated_at"] = now_utc()
        return hook

    def list_hooks(self, state_id: Optional[str] = None) -> List[Dict[str, Any]]:
        resolved_state = resolve_state_token(self, state_id)
        record = ensure_state_programming_record(self.manifest, resolved_state)
        hooks = []
        for collection in ("input_events", "processors", "output_events"):
            for hook in record.get(collection, []):
                item = dict(hook)
                item["state_id"] = resolved_state
                item["collection"] = collection
                hooks.append(item)
        return hooks

    def delete_hook(self, state_id: str, hook_id: str) -> bool:
        resolved_state = resolve_state_token(self, state_id)
        record = ensure_state_programming_record(self.manifest, resolved_state)
        for collection in ("input_events", "processors", "output_events"):
            original = list(record.get(collection, []))
            record[collection] = [hook for hook in original if hook.get("id") != hook_id]
            if len(record[collection]) != len(original):
                self.manifest["state_programming"]["updated_at"] = now_utc()
                return True
        return False

    def set_hook_enabled(self, state_id: str, hook_id: str, enabled: bool) -> bool:
        resolved_state = resolve_state_token(self, state_id)
        record = ensure_state_programming_record(self.manifest, resolved_state)
        for collection in ("input_events", "processors", "output_events"):
            for hook in record.get(collection, []):
                if hook.get("id") == hook_id:
                    hook["enabled"] = bool(enabled)
                    hook["updated_at"] = now_utc()
                    self.manifest["state_programming"]["updated_at"] = now_utc()
                    return True
        return False

    def programming_context(self, state_id: str, hook: Dict[str, Any], event: Dict[str, Any], outputs: List[Any]) -> Dict[str, Any]:
        state = manifest_state_map(self.manifest).get(state_id, {})

        def emit(value: Any = None) -> Any:
            outputs.append(value)
            return value

        def goto(token: str) -> str:
            return self.goto_state(token)

        context: Dict[str, Any] = {
            "__name__": "__pathfinder_state_program__",
            "controller": self,
            "runtime": self,
            "manifest": self.manifest,
            "manifest_path": self.manifest_path,
            "state": state,
            "state_id": state_id,
            "cursor": self.state_cursor,
            "session": self.session,
            "session_path": self.session_path,
            "event": event,
            "hook": hook,
            "outputs": outputs,
            "emit": emit,
            "goto": goto,
            "Path": Path,
            "json": json,
            "math": math,
            "os": os,
            "re": re,
            "shlex": shlex,
            "subprocess": subprocess,
            "sys": sys,
            "now_utc": now_utc,
        }
        return context

    def run_hook(self, state_id: str, hook: Dict[str, Any], payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not hook.get("enabled", True):
            return {"hook_id": hook.get("id"), "status": "skipped", "outputs": []}
        outputs: List[Any] = []
        event = {
            "kind": hook.get("kind"),
            "event_type": hook.get("event_type", "python"),
            "payload": payload or {},
            "state_cursor": dict(self.state_cursor),
            "timestamp": now_utc(),
        }
        code = str(hook.get("code") or "")
        source_path = hook.get("source_path")
        if source_path and Path(source_path).exists():
            code = Path(source_path).read_text(encoding="utf-8")
        context = self.programming_context(state_id, hook, event, outputs)
        try:
            exec(compile(code, str(source_path or f"<pathfinder:{state_id}:{hook.get('id')}>"), "exec"), context, context)
            handler = context.get("handle")
            if callable(handler):
                result = handler(context)
                if result is not None:
                    outputs.append(result)
            elif "result" in context:
                outputs.append(context["result"])
            hook["last_run_at"] = now_utc()
            hook["last_status"] = "ok"
            hook["last_error"] = None
            return {"hook_id": hook.get("id"), "status": "ok", "outputs": outputs}
        except Exception as exc:
            hook["last_run_at"] = now_utc()
            hook["last_status"] = "error"
            hook["last_error"] = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            raise

    def run_hooks(self, kind: str, state_id: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        resolved_state = resolve_state_token(self, state_id)
        self.set_cursor(resolved_state, source=f"run-{normalize_hook_kind(kind)}", payload=payload)
        record = ensure_state_programming_record(self.manifest, resolved_state)
        results = []
        for hook in record.get(self.hook_collection(kind), []):
            results.append(self.run_hook(resolved_state, hook, payload=payload))
        self.manifest["state_programming"]["updated_at"] = now_utc()
        return results

    def run_all_state_behaviour(self, state_id: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for kind in ("input", "process", "output"):
            results.extend(self.run_hooks(kind, state_id=state_id, payload=payload))
        return results

    def instruction_api(self) -> "PathfinderInstructionAPI":
        return PathfinderInstructionAPI(self)

    def run_instruction_script(self, path: Path) -> Any:
        script_path = path.resolve()
        code = script_path.read_text(encoding="utf-8")
        api = self.instruction_api()
        context = {
            "__name__": "__pathfinder_instruction__",
            "__file__": str(script_path),
            "api": api,
            "controller": self,
            "runtime": self,
            "manifest": self.manifest,
            "manifest_path": self.manifest_path,
            "session": self.session,
            "session_path": self.session_path,
            "Path": Path,
            "json": json,
            "os": os,
            "sys": sys,
            "subprocess": subprocess,
        }
        exec(compile(code, str(script_path), "exec"), context, context)
        if self.session is not None:
            recent = self.session.setdefault("recent_instruction_scripts", [])
            script_text = as_abs(script_path)
            if script_text in recent:
                recent.remove(script_text)
            recent.insert(0, script_text)
            del recent[16:]
        return context.get("result")

    def goto_state(self, token: str) -> str:
        seq = self.sequence
        state_map = manifest_state_map(self.manifest)
        if token.isdigit():
            index = int(token)
            if index < 0 or index >= len(seq):
                raise ValueError(f"Sequence index outside range: {index}")
            self.current_position = index
            self.set_cursor(seq[self.current_position], source="goto")
            return f"current {seq[self.current_position]}"
        if token in seq:
            self.current_position = seq.index(token)
            self.set_cursor(token, source="goto")
            return f"current {token}"
        if token in state_map:
            self.manifest.setdefault("bootstrap_sequence", []).append(token)
            self.current_position = len(self.manifest["bootstrap_sequence"]) - 1
            self.set_cursor(token, source="goto")
            return f"added {token} to sequence"
        raise ValueError(f"Unknown state: {token}")

    def run(self, line: str) -> Tuple[str, bool]:
        parts = shlex.split(line)
        if not parts:
            return "", False
        cmd = parts[0].lower()
        args = parts[1:]
        if cmd in {"help", "?"}:
            return (
                "commands: status, boot, next, prev, goto <index|state>, sequence, "
                "promote <state>, bind <name> <state>, cursor, session, program, script, save, export <path>, quit",
                False,
            )
        if cmd == "status":
            state = self.current_state_id() or "none"
            return f"current={state} states={len(self.manifest.get('image_states', []))} sequence={len(self.sequence)}", False
        if cmd == "boot":
            self.current_position = 0
            self.set_cursor(source="boot")
            return f"current {self.current_state_id()}", False
        if cmd == "next":
            if self.sequence:
                self.current_position = (self.current_position + 1) % len(self.sequence)
                self.set_cursor(source="next")
            return f"current {self.current_state_id()}", False
        if cmd == "prev":
            if self.sequence:
                self.current_position = (self.current_position - 1) % len(self.sequence)
                self.set_cursor(source="prev")
            return f"current {self.current_state_id()}", False
        if cmd == "goto":
            if not args:
                raise ValueError("Usage: goto <index|state>")
            return self.goto_state(args[0]), False
        if cmd == "sequence":
            if args and args[0] == "set":
                new_seq = []
                for item in " ".join(args[1:]).replace(",", " ").split():
                    if item not in manifest_state_map(self.manifest):
                        raise ValueError(f"Unknown state in sequence: {item}")
                    new_seq.append(item)
                if not new_seq:
                    raise ValueError("sequence set requires at least one state")
                self.manifest["bootstrap_sequence"] = new_seq
                self.current_position = 0
                return "sequence updated", True
            return " -> ".join(self.sequence), False
        if cmd == "promote":
            if not args:
                raise ValueError("Usage: promote <state>")
            state_id = args[0]
            if state_id not in manifest_state_map(self.manifest):
                raise ValueError(f"Unknown state: {state_id}")
            seq = [s for s in self.sequence if s != state_id]
            self.manifest["bootstrap_sequence"] = [state_id] + seq
            self.current_position = 0
            return f"promoted {state_id}", True
        if cmd == "bind":
            if len(args) != 2:
                raise ValueError("Usage: bind <name> <state>")
            name, state_id = args
            if state_id not in manifest_state_map(self.manifest):
                raise ValueError(f"Unknown state: {state_id}")
            self.manifest.setdefault("command_bindings", {})[name] = state_id
            return f"bound {name} -> {state_id}", True
        if cmd == "cursor":
            if args and args[0] == "set":
                state_id = resolve_state_token(self, args[1] if len(args) > 1 else None)
                image_x = int(args[2]) if len(args) > 2 and args[2] != "-" else None
                image_y = int(args[3]) if len(args) > 3 and args[3] != "-" else None
                self.set_cursor(state_id, image_x=image_x, image_y=image_y, source="shell")
                return json.dumps(self.state_cursor, indent=2), True
            return json.dumps(self.state_cursor, indent=2), False
        if cmd == "session":
            if not args or args[0] == "status":
                return json.dumps(self.session or {"session_path": None}, indent=2), False
            if args[0] == "create":
                path = Path(args[1]).resolve() if len(args) > 1 else default_session_path_for_manifest(self.manifest_path)
                self.session = create_session_data(self.manifest_path)
                self.session_path = path
                self.save_session(path)
                return f"created session {path}", True
            if args[0] == "open":
                if len(args) < 2:
                    raise ValueError("Usage: session open <path>")
                return self.open_session(Path(args[1]), create=False), False
            if args[0] == "save":
                path = Path(args[1]).resolve() if len(args) > 1 else None
                return self.save_session(path), False
            if args[0] == "projects":
                return json.dumps((self.session or {}).get("projects", []), indent=2), False
            raise ValueError("Usage: session status|create [path]|open <path>|save [path]|projects")
        if cmd == "program":
            return self._cmd_program(args)
        if cmd == "script":
            if not args:
                raise ValueError("Usage: script <instruction.py>")
            result = self.run_instruction_script(Path(args[0]))
            return f"ran script {Path(args[0]).resolve()}" + (f" -> {result}" if result is not None else ""), True
        if cmd == "save":
            self.save()
            return f"saved {self.manifest_path}", False
        if cmd == "export":
            if not args:
                raise ValueError("Usage: export <path>")
            export_path = Path(args[0]).resolve()
            write_json(export_path, self.manifest)
            return f"exported {export_path}", False
        if cmd in {"quit", "exit"}:
            return "quit", False
        raise ValueError(f"Unknown runtime command: {cmd}")

    def _cmd_program(self, args: List[str]) -> Tuple[str, bool]:
        if not args:
            return "Usage: program list [state]|add <input|process|output> <state|current> <name> <file|code>|run <kind|all> [state]|del <state> <hook_id>|enable <state> <hook_id>|disable <state> <hook_id>", False
        action = args[0]
        if action == "list":
            state_id = resolve_state_token(self, args[1] if len(args) > 1 else None)
            hooks = self.list_hooks(state_id)
            if not hooks:
                return f"no programs for {state_id}", False
            lines = []
            for hook in hooks:
                lines.append(
                    f"{hook['state_id']} {hook.get('kind')} {hook.get('id')} "
                    f"{'on' if hook.get('enabled', True) else 'off'} {hook.get('name')}"
                )
            return "\n".join(lines), False
        if action == "add":
            if len(args) < 5:
                raise ValueError("Usage: program add <input|process|output> <state|current> <name> <file|code>")
            kind, state_token, name = args[1], args[2], args[3]
            source = " ".join(args[4:])
            source_path: Optional[str] = None
            possible_path = Path(source)
            if possible_path.exists():
                code = possible_path.read_text(encoding="utf-8")
                source_path = as_abs(possible_path)
            else:
                code = source
            hook = self.add_hook(kind, state_token, name, code, source_path=source_path)
            return f"added {hook['kind']} program {hook['id']} to {resolve_state_token(self, state_token)}", True
        if action == "run":
            if len(args) < 2:
                raise ValueError("Usage: program run <input|process|output|all> [state]")
            kind = args[1]
            state_id = args[2] if len(args) > 2 else None
            if kind == "all":
                results = self.run_all_state_behaviour(state_id, payload={"source": "shell"})
            else:
                results = self.run_hooks(kind, state_id=state_id, payload={"source": "shell"})
            return json.dumps(results, indent=2, ensure_ascii=False), True
        if action == "del":
            if len(args) != 3:
                raise ValueError("Usage: program del <state|current> <hook_id>")
            deleted = self.delete_hook(args[1], args[2])
            return "deleted" if deleted else "not found", deleted
        if action in {"enable", "disable"}:
            if len(args) != 3:
                raise ValueError(f"Usage: program {action} <state|current> <hook_id>")
            changed = self.set_hook_enabled(args[1], args[2], enabled=(action == "enable"))
            return action if changed else "not found", changed
        raise ValueError("Unknown program action. Use list, add, run, del, enable, or disable.")


class PathfinderInstructionAPI:
    """Small stable API exposed to user-authored Pathfinder instruction scripts."""

    def __init__(self, controller: RuntimeController):
        self.controller = controller

    @property
    def manifest(self) -> Dict[str, Any]:
        return self.controller.manifest

    @property
    def session(self) -> Optional[Dict[str, Any]]:
        return self.controller.session

    def current_state_id(self) -> Optional[str]:
        return self.controller.current_state_id()

    def current_state(self) -> Optional[Dict[str, Any]]:
        return self.controller.current_state()

    def goto(self, state: str) -> str:
        return self.controller.goto_state(state)

    def set_cursor(self, state: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        state_id = resolve_state_token(self.controller, state)
        return self.controller.set_cursor(state_id, source="instruction-script", **kwargs)

    def create_session(self, path: str | Path) -> str:
        self.controller.session = create_session_data(self.controller.manifest_path)
        self.controller.session_path = Path(path).resolve()
        return self.controller.save_session(self.controller.session_path)

    def open_session(self, path: str | Path) -> str:
        return self.controller.open_session(Path(path), create=False)

    def save(self) -> None:
        self.controller.save()

    def save_session(self, path: Optional[str | Path] = None) -> str:
        return self.controller.save_session(Path(path) if path else None)

    def add_input(self, state: str, name: str, code: str, event_type: str = "python") -> Dict[str, Any]:
        return self.controller.add_hook("input", state, name, code, event_type=event_type)

    def add_processor(self, state: str, name: str, code: str, event_type: str = "python") -> Dict[str, Any]:
        return self.controller.add_hook("process", state, name, code, event_type=event_type)

    def add_output(self, state: str, name: str, code: str, event_type: str = "python") -> Dict[str, Any]:
        return self.controller.add_hook("output", state, name, code, event_type=event_type)

    def add_hook(
        self,
        kind: str,
        state: str,
        name: str,
        code: str,
        event_type: str = "python",
        source_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.controller.add_hook(kind, state, name, code, event_type=event_type, source_path=source_path)

    def run(self, kind: str = "all", state: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if kind == "all":
            return self.controller.run_all_state_behaviour(state, payload=payload)
        return self.controller.run_hooks(kind, state_id=state, payload=payload)

    def list_hooks(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.controller.list_hooks(state)

    def delete_hook(self, state: str, hook_id: str) -> bool:
        return self.controller.delete_hook(state, hook_id)


def run_shell(args: argparse.Namespace) -> int:
    controller = RuntimeController(
        Path(args.manifest),
        session_path=Path(args.session) if args.session else None,
        create_session=args.create_session,
    )
    print("Pathfinder runtime shell. Type help for commands, quit to exit.")
    while True:
        try:
            line = input("pathfinder> ")
        except EOFError:
            print()
            return 0
        try:
            output, changed = controller.run(line)
            if output:
                print(output)
            if changed and args.autosave:
                controller.save()
            if output == "quit":
                return 0
        except Exception as exc:
            print(f"error: {exc}")


def run_gui(args: argparse.Namespace) -> int:
    Image, _, ImageTk = require_pillow()
    import tkinter as tk
    from tkinter import filedialog, messagebox

    controller = RuntimeController(
        Path(args.manifest),
        session_path=Path(args.session) if args.session else None,
        create_session=args.create_session,
    )

    root = tk.Tk()
    root.title("Pathfinder Runtime")
    root.geometry("1040x720")
    root.minsize(720, 480)

    top = tk.Frame(root)
    top.pack(fill=tk.X, padx=10, pady=(10, 4))
    title = tk.Label(top, text="Pathfinder", font=("Segoe UI", 18, "bold"))
    title.pack(side=tk.LEFT)
    status = tk.Label(top, text="", anchor="e")
    status.pack(side=tk.RIGHT, fill=tk.X, expand=True)

    body = tk.Frame(root)
    body.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
    canvas = tk.Canvas(body, bg="#101820", highlightthickness=0)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    side = tk.Text(body, width=38, height=12, wrap=tk.WORD)
    side.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))

    bottom = tk.Frame(root)
    bottom.pack(fill=tk.X, padx=10, pady=(4, 10))
    entry = tk.Entry(bottom)
    entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    button = tk.Button(bottom, text="Run")
    button.pack(side=tk.RIGHT, padx=(8, 0))

    tk_image_holder: Dict[str, Any] = {"image": None}
    display_info: Dict[str, Any] = {}

    def log(text: str) -> None:
        side.insert(tk.END, text.rstrip() + "\n")
        side.see(tk.END)

    def render() -> None:
        state = controller.current_state()
        canvas.delete("all")
        if not state:
            status.config(text="No state")
            tk_image_holder["image"] = None
            display_info.clear()
            return

        path = Path(state["image_path"])
        if not path.exists():
            status.config(text=f"Missing image for {state['id']}: {path}")
            tk_image_holder["image"] = None
            display_info.clear()
            return

        image = Image.open(path).convert("RGB")
        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw <= 20 or ch <= 20:
            status.config(text=f"{state['id']} | waiting for canvas layout")
            tk_image_holder["image"] = None
            display_info.clear()
            return

        max_w = max(1, cw - 20)
        max_h = max(1, ch - 20)
        display = image.copy()
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
        display.thumbnail((max_w, max_h), resampling)
        if display.width <= 0 or display.height <= 0:
            status.config(text=f"{state['id']} | image has no drawable size")
            tk_image_holder["image"] = None
            display_info.clear()
            return

        tk_image = ImageTk.PhotoImage(display, master=root)
        tk_image_holder["image"] = tk_image
        x0 = (cw - display.width) // 2
        y0 = (ch - display.height) // 2
        canvas.create_image(cw // 2, ch // 2, image=tk_image, anchor=tk.CENTER)
        display_info.clear()
        display_info.update(
            {
                "state_id": state["id"],
                "image_width": image.width,
                "image_height": image.height,
                "display_width": display.width,
                "display_height": display.height,
                "x0": x0,
                "y0": y0,
                "scale_x": image.width / display.width,
                "scale_y": image.height / display.height,
            }
        )
        status.config(text=f"{state['id']} | {image.width}x{image.height} | {shorten(state['pixel_sha256'], 22)}")

    def image_coords_from_event(event: Any) -> Tuple[Optional[int], Optional[int]]:
        if not display_info:
            return None, None
        x0 = int(display_info["x0"])
        y0 = int(display_info["y0"])
        dw = int(display_info["display_width"])
        dh = int(display_info["display_height"])
        if event.x < x0 or event.x >= x0 + dw or event.y < y0 or event.y >= y0 + dh:
            return None, None
        image_x = int((event.x - x0) * float(display_info["scale_x"]))
        image_y = int((event.y - y0) * float(display_info["scale_y"]))
        image_x = max(0, min(int(display_info["image_width"]) - 1, image_x))
        image_y = max(0, min(int(display_info["image_height"]) - 1, image_y))
        return image_x, image_y

    def program_template(kind: str, state_id: str) -> str:
        if normalize_hook_kind(kind) == "input":
            return (
                "event_payload = event.get('payload', {})\n"
                "emit({'input': event_payload, 'cursor': cursor, 'state': state_id})\n"
            )
        if normalize_hook_kind(kind) == "process":
            return (
                "state.setdefault('program_data', {})['processed_at'] = now_utc()\n"
                "emit({'processed': state_id, 'cursor': cursor})\n"
            )
        return (
            "output_path = Path(manifest.get('output_directory', '.')) / f'{state_id}.program-output.json'\n"
            "output_path.write_text(json.dumps({'state': state_id, 'cursor': cursor}, indent=2), encoding='utf-8')\n"
            "emit({'wrote': str(output_path)})\n"
        )

    def open_program_editor(kind: str) -> None:
        state_id = controller.current_state_id()
        if not state_id:
            return
        editor = tk.Toplevel(root)
        editor.title(f"{APP_NAME} {normalize_hook_kind(kind)} program")
        editor.geometry("760x540")
        top_frame = tk.Frame(editor, padx=8, pady=8)
        top_frame.pack(fill=tk.X)
        tk.Label(top_frame, text="Name").pack(side=tk.LEFT)
        name_var = tk.StringVar(value=f"{normalize_hook_kind(kind)}-{state_id}")
        name_entry = tk.Entry(top_frame, textvariable=name_var)
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        tk.Label(top_frame, text="Type").pack(side=tk.LEFT)
        type_var = tk.StringVar(value="python")
        type_entry = tk.Entry(top_frame, textvariable=type_var, width=18)
        type_entry.pack(side=tk.LEFT, padx=(8, 0))
        text = tk.Text(editor, wrap=tk.NONE, undo=True)
        text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        text.insert("1.0", program_template(kind, state_id))
        bottom_frame = tk.Frame(editor, padx=8, pady=8)
        bottom_frame.pack(fill=tk.X)

        def save_program() -> None:
            code = text.get("1.0", tk.END).rstrip()
            hook = controller.add_hook(kind, state_id, name_var.get().strip(), code, event_type=type_var.get().strip())
            log(f"added {hook['kind']} program {hook['id']} to {state_id}")
            if args.autosave:
                controller.save()
            editor.destroy()

        def load_script() -> None:
            path = filedialog.askopenfilename(
                title="Open Python instruction or hook file",
                filetypes=[("Python files", "*.py"), ("All files", "*.*")],
            )
            if path:
                text.delete("1.0", tk.END)
                text.insert("1.0", Path(path).read_text(encoding="utf-8"))

        tk.Button(bottom_frame, text="Load .py", command=load_script).pack(side=tk.LEFT)
        tk.Button(bottom_frame, text="Save Program", command=save_program).pack(side=tk.RIGHT)
        tk.Button(bottom_frame, text="Cancel", command=editor.destroy).pack(side=tk.RIGHT, padx=(0, 8))
        name_entry.focus_set()

    def show_programs() -> None:
        state_id = controller.current_state_id()
        if not state_id:
            return
        win = tk.Toplevel(root)
        win.title(f"{APP_NAME} programs for {state_id}")
        win.geometry("760x360")
        listbox = tk.Listbox(win)
        listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        hooks = controller.list_hooks(state_id)

        def refresh() -> None:
            hooks[:] = controller.list_hooks(state_id)
            listbox.delete(0, tk.END)
            for hook in hooks:
                status_text = "on" if hook.get("enabled", True) else "off"
                listbox.insert(tk.END, f"{hook.get('kind')} {hook.get('id')} {status_text} {hook.get('name')}")

        def selected_hook() -> Optional[Dict[str, Any]]:
            selection = listbox.curselection()
            if not selection:
                return None
            return hooks[selection[0]]

        def toggle() -> None:
            hook = selected_hook()
            if not hook:
                return
            controller.set_hook_enabled(state_id, hook["id"], not hook.get("enabled", True))
            if args.autosave:
                controller.save()
            refresh()

        def delete() -> None:
            hook = selected_hook()
            if not hook:
                return
            if messagebox.askyesno("Pathfinder", f"Delete {hook.get('name')}?"):
                controller.delete_hook(state_id, hook["id"])
                if args.autosave:
                    controller.save()
                refresh()

        buttons = tk.Frame(win, padx=8, pady=8)
        buttons.pack(fill=tk.X)
        tk.Button(buttons, text="Enable/Disable", command=toggle).pack(side=tk.LEFT)
        tk.Button(buttons, text="Delete", command=delete).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(buttons, text="Close", command=win.destroy).pack(side=tk.RIGHT)
        refresh()

    def run_programs(kind: str) -> None:
        state_id = controller.current_state_id()
        if not state_id:
            return
        try:
            if kind == "all":
                results = controller.run_all_state_behaviour(state_id, payload={"source": "gui", "cursor": controller.state_cursor})
            else:
                results = controller.run_hooks(kind, state_id=state_id, payload={"source": "gui", "cursor": controller.state_cursor})
            log(json.dumps(results, indent=2, ensure_ascii=False))
            if args.autosave:
                controller.save()
            render()
        except Exception as exc:
            messagebox.showerror("Pathfinder program error", str(exc))

    def save_session_as() -> None:
        initial = controller.session_path or default_session_path_for_manifest(controller.manifest_path)
        path = filedialog.asksaveasfilename(
            title="Save Pathfinder session",
            initialdir=str(initial.parent),
            initialfile=initial.name,
            defaultextension=".json",
            filetypes=[("Pathfinder session", "*.json"), ("All files", "*.*")],
        )
        if path:
            log(controller.save_session(Path(path)))

    def show_context_menu(event: Any) -> None:
        state = controller.current_state()
        if not state:
            return
        image_x, image_y = image_coords_from_event(event)
        controller.set_cursor(
            state["id"],
            image_x=image_x,
            image_y=image_y,
            screen_x=event.x_root,
            screen_y=event.y_root,
            source="gui-context-menu",
        )
        menu = tk.Menu(root, tearoff=False)
        menu.add_command(label=f"Cursor: {state['id']} ({image_x}, {image_y})", state=tk.DISABLED)
        menu.add_separator()
        menu.add_command(label="Add Input Event...", command=lambda: open_program_editor("input"))
        menu.add_command(label="Add Processing Logic...", command=lambda: open_program_editor("process"))
        menu.add_command(label="Add Output Event...", command=lambda: open_program_editor("output"))
        menu.add_separator()
        menu.add_command(label="Run Input Events", command=lambda: run_programs("input"))
        menu.add_command(label="Run Processing Logic", command=lambda: run_programs("process"))
        menu.add_command(label="Run Output Events", command=lambda: run_programs("output"))
        menu.add_command(label="Run All State Behaviour", command=lambda: run_programs("all"))
        menu.add_separator()
        menu.add_command(label="Manage State Programs...", command=show_programs)
        menu.add_command(label="Save Session As...", command=save_session_as)
        menu.add_command(label="Save Manifest and Session", command=controller.save)
        menu.tk_popup(event.x_root, event.y_root)

    def run_command() -> None:
        line = entry.get().strip()
        entry.delete(0, tk.END)
        if not line:
            return
        try:
            output, changed = controller.run(line)
            log(f"> {line}")
            if output:
                log(output)
            if changed and args.autosave:
                controller.save()
            if output == "quit":
                root.destroy()
                return
            render()
        except Exception as exc:
            messagebox.showerror("Pathfinder command error", str(exc))

    button.config(command=run_command)
    entry.bind("<Return>", lambda _event: run_command())
    root.bind("<Left>", lambda _event: (controller.run("prev"), render()))
    root.bind("<Right>", lambda _event: (controller.run("next"), render()))
    canvas.bind("<Configure>", lambda _event: render())
    canvas.bind("<Button-3>", show_context_menu)
    canvas.bind("<Button-2>", show_context_menu)
    log("Pathfinder runtime ready. Type help for commands.")
    render()
    root.mainloop()
    return 0


def default_projects_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / "Pathfinder" / "projects"
    return Path.home() / "Pathfinder" / "projects"


def run_desktop(args: argparse.Namespace) -> int:
    require_pillow()
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.title("Pathfinder")
    root.geometry("760x480")
    root.minsize(640, 420)

    manifest_var = tk.StringVar(value="")
    session_var = tk.StringVar(value="")
    status_var = tk.StringVar(value="Ready")

    header = tk.Frame(root, padx=16, pady=14)
    header.pack(fill=tk.X)
    tk.Label(header, text="Pathfinder", font=("Segoe UI", 22, "bold")).pack(anchor="w")
    tk.Label(
        header,
        text="Image-indexed tensor runtime",
        font=("Segoe UI", 10),
        fg="#4a5568",
    ).pack(anchor="w")

    body = tk.Frame(root, padx=16, pady=8)
    body.pack(fill=tk.BOTH, expand=True)

    manifest_row = tk.Frame(body)
    manifest_row.pack(fill=tk.X, pady=(0, 10))
    manifest_entry = tk.Entry(manifest_row, textvariable=manifest_var)
    manifest_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def choose_manifest() -> None:
        path = filedialog.askopenfilename(
            title="Open Pathfinder manifest",
            filetypes=[("Pathfinder manifest", "pathfinder.manifest.json"), ("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            manifest_var.set(path)
            status_var.set(f"Selected {path}")

    tk.Button(manifest_row, text="Open", command=choose_manifest, width=10).pack(side=tk.RIGHT, padx=(8, 0))

    session_row = tk.Frame(body)
    session_row.pack(fill=tk.X, pady=(0, 10))
    session_entry = tk.Entry(session_row, textvariable=session_var)
    session_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def choose_session() -> None:
        path = filedialog.askopenfilename(
            title="Open Pathfinder session",
            filetypes=[("Pathfinder session", "*.json"), ("All files", "*.*")],
        )
        if path:
            session_var.set(path)
            status_var.set(f"Selected session {path}")

    def create_session() -> None:
        manifest_text = manifest_var.get().strip()
        initial_dir = Path(manifest_text).resolve().parent if manifest_text else default_projects_dir()
        path = filedialog.asksaveasfilename(
            title="Create Pathfinder session",
            initialdir=str(initial_dir),
            initialfile="pathfinder.session.json",
            defaultextension=".json",
            filetypes=[("Pathfinder session", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        manifest_path = Path(manifest_text).resolve() if manifest_text else None
        data = create_session_data(manifest_path)
        save_session_file(Path(path), data)
        session_var.set(path)
        log(f"Created session: {path}")

    tk.Button(session_row, text="Session", command=choose_session, width=10).pack(side=tk.RIGHT, padx=(8, 0))
    tk.Button(session_row, text="New", command=create_session, width=8).pack(side=tk.RIGHT, padx=(8, 0))

    output = tk.Text(body, height=10, wrap=tk.WORD)
    output.pack(fill=tk.BOTH, expand=True)

    def log(text: str) -> None:
        output.insert(tk.END, text.rstrip() + "\n")
        output.see(tk.END)
        status_var.set(text.strip())

    def build_demo() -> None:
        try:
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            out_dir = default_projects_dir() / f"demo-{stamp}"
            ns = argparse.Namespace(
                seed=None,
                out=str(out_dir),
                iterations=4,
                basis_config=None,
                basis_exe=None,
                basis_rows=6,
                seed_length=2,
                seed_mode="strict",
                workspace_pixel_mode="compact",
                demo_size=32,
                force=True,
            )
            build_pathfinder(ns)
            manifest = out_dir / "pathfinder.manifest.json"
            manifest_var.set(str(manifest))
            if not session_var.get().strip():
                session = out_dir / "pathfinder.session.json"
                save_session_file(session, create_session_data(manifest))
                session_var.set(str(session))
            log(f"Built demo runtime: {manifest}")
        except Exception as exc:
            messagebox.showerror("Pathfinder build failed", str(exc))

    def launch_runtime() -> None:
        path = manifest_var.get().strip()
        if not path:
            messagebox.showinfo("Pathfinder", "Open or build a manifest first.")
            return
        try:
            session_text = session_var.get().strip()
            ns = argparse.Namespace(
                manifest=path,
                autosave=True,
                session=session_text or None,
                create_session=bool(session_text),
            )
            root.withdraw()
            run_gui(ns)
            root.deiconify()
        except Exception as exc:
            root.deiconify()
            messagebox.showerror("Pathfinder runtime failed", str(exc))

    buttons = tk.Frame(body)
    buttons.pack(fill=tk.X, pady=(10, 0))
    tk.Button(buttons, text="Build Demo Runtime", command=build_demo).pack(side=tk.LEFT)
    tk.Button(buttons, text="Launch Runtime", command=launch_runtime).pack(side=tk.LEFT, padx=(8, 0))
    tk.Button(buttons, text="Quit", command=root.destroy).pack(side=tk.RIGHT)

    tk.Label(root, textvariable=status_var, anchor="w", padx=16, pady=8).pack(fill=tk.X)
    log(f"Projects folder: {default_projects_dir()}")
    root.mainloop()
    return 0


def command_status(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest))
    print_status(manifest)
    return 0


def command_workspace(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest))
    workspace_path = Path(manifest.get("workspace_path", Path(args.manifest).with_suffix(".workspace.json")))
    if args.rebuild or not workspace_path.exists():
        save_workspace(manifest, workspace_path, manifest.get("workspace_pixel_mode", "compact"))
    tensor = load_tensor_module()
    ws = tensor.Workspace.from_dict(read_json(workspace_path))
    renderer = tensor.TensorRenderer(tensor.load_config(None))
    data = renderer.render(ws, args.format)
    if args.output:
        Path(args.output).write_text(data, encoding="utf-8")
    else:
        print(data, end="" if data.endswith("\n") else "\n")
    return 0


def command_session(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve() if args.manifest else None
    session_path = Path(args.session).resolve() if args.session else (
        default_session_path_for_manifest(manifest_path) if manifest_path else Path("pathfinder.session.json").resolve()
    )
    if args.create:
        save_session_file(session_path, create_session_data(manifest_path))
        print(f"created session {session_path}")
        return 0
    if not session_path.exists():
        raise FileNotFoundError(f"Session file does not exist: {session_path}")
    session = load_session_file(session_path)
    if manifest_path:
        add_manifest_to_session(session, manifest_path)
        save_session_file(session_path, session)
    print(json.dumps(session, indent=2, ensure_ascii=False))
    return 0


def command_script(args: argparse.Namespace) -> int:
    controller = RuntimeController(
        Path(args.manifest),
        session_path=Path(args.session) if args.session else None,
        create_session=args.create_session,
    )
    result = controller.run_instruction_script(Path(args.file))
    if args.autosave:
        controller.save()
    elif args.save_session and controller.session_path:
        controller.save_session()
    if result is not None:
        print(json.dumps(result, indent=2, ensure_ascii=False) if not isinstance(result, str) else result)
    print(f"ran instruction script {Path(args.file).resolve()}")
    return 0


def command_program(args: argparse.Namespace) -> int:
    controller = RuntimeController(
        Path(args.manifest),
        session_path=Path(args.session) if args.session else None,
        create_session=args.create_session,
    )
    if args.action == "list":
        hooks = controller.list_hooks(args.state)
        print(json.dumps(hooks, indent=2, ensure_ascii=False))
        return 0
    if args.action == "run":
        if args.kind == "all":
            results = controller.run_all_state_behaviour(args.state, payload={"source": "cli"})
        else:
            results = controller.run_hooks(args.kind, state_id=args.state, payload={"source": "cli"})
        if args.autosave:
            controller.save()
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0
    if args.action == "add":
        code = Path(args.code_or_file).read_text(encoding="utf-8") if Path(args.code_or_file).exists() else args.code_or_file
        source_path = as_abs(Path(args.code_or_file)) if Path(args.code_or_file).exists() else None
        hook = controller.add_hook(args.kind, args.state, args.name, code, event_type=args.event_type, source_path=source_path)
        if args.autosave:
            controller.save()
        print(json.dumps(hook, indent=2, ensure_ascii=False))
        return 0
    raise ValueError(f"Unsupported program action: {args.action}")


def command_reconstruct(args: argparse.Namespace) -> int:
    out = reconstruct_image(Path(args.input), Path(args.output))
    print(f"reconstructed {out}")
    return 0


def command_demo_seed(args: argparse.Namespace) -> int:
    path = create_demo_seed(Path(args.output), size=args.size)
    print(f"wrote demo seed {path}")
    return 0


def command_basis(args: argparse.Namespace) -> int:
    basis_exe = find_basis_engine(args.basis_exe, Path(args.out).resolve().parent)
    if basis_exe is None:
        raise FileNotFoundError("Could not find or build basis_tensor.exe")
    out = Path(args.out).resolve()
    seed_file = Path(args.seed_file).resolve() if args.seed_file else out.with_suffix(".seed.txt")
    seed_build = Path(args.seed_build).resolve() if args.seed_build else out.with_suffix(".seed-build.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    seed_build.parent.mkdir(parents=True, exist_ok=True)
    run_basis_engine(
        basis_exe,
        Path(args.config).resolve(),
        out,
        seed_file,
        seed_build,
        seed_length=args.seed_length,
        seed_mode=args.seed_mode,
    )
    print(f"wrote {out}")
    print(f"wrote {seed_build}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pathfinder",
        description="Pathfinder image-indexed tensor runtime orchestrator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              pathfinder build --seed seed.png --iterations 8 --out build/pathfinder
              pathfinder build --iterations 4 --out build/demo
              pathfinder status --manifest build/demo/pathfinder.manifest.json
              pathfinder gui --manifest build/demo/pathfinder.manifest.json
              pathfinder workspace --manifest build/demo/pathfinder.manifest.json --format summary
            """
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="build a Pathfinder manifest, workspace, states, and basis outputs")
    p_build.add_argument("--seed", help="square seed image; omitted creates a deterministic demo seed")
    p_build.add_argument("--out", default="pathfinder_build", help="output directory")
    p_build.add_argument("--iterations", type=int, default=8, help="basis-transform iterations after I0")
    p_build.add_argument("--basis-config", help="existing 16.cpp JSON config; omitted creates an image-derived config")
    p_build.add_argument("--basis-exe", help="basis_tensor.exe path")
    p_build.add_argument("--basis-rows", type=int, default=6, help="basis rows for generated image-derived config")
    p_build.add_argument("--seed-length", type=int, choices=range(1, 7), default=2, help="generated canonical seed length")
    p_build.add_argument("--seed-mode", choices=["strict", "wrap"], default="strict")
    p_build.add_argument("--workspace-pixel-mode", choices=["compact", "paths"], default="compact")
    p_build.add_argument("--demo-size", type=int, default=32, help="demo seed side length when --seed is omitted")
    p_build.add_argument("--force", action="store_true", help="overwrite known Pathfinder output files")
    p_build.set_defaults(func=build_pathfinder)

    p_status = sub.add_parser("status", help="summarize a Pathfinder manifest")
    p_status.add_argument("--manifest", required=True)
    p_status.set_defaults(func=command_status)

    p_workspace = sub.add_parser("workspace", help="render or rebuild the Tensor workspace")
    p_workspace.add_argument("--manifest", required=True)
    p_workspace.add_argument("--format", default="summary", choices=["json", "jsonl", "csv", "markdown", "tensor_text", "databank_text", "summary", "dot"])
    p_workspace.add_argument("--output")
    p_workspace.add_argument("--rebuild", action="store_true")
    p_workspace.set_defaults(func=command_workspace)

    p_shell = sub.add_parser("shell", help="run the CLI-commanded runtime shell")
    p_shell.add_argument("--manifest", required=True)
    p_shell.add_argument("--session", help="Pathfinder session persistence JSON")
    p_shell.add_argument("--create-session", action="store_true", help="create --session when it does not exist")
    p_shell.add_argument("--autosave", action="store_true", help="save manifest/workspace after mutating commands")
    p_shell.set_defaults(func=run_shell)

    p_gui = sub.add_parser("gui", help="run the Tk graphical Pathfinder runtime")
    p_gui.add_argument("--manifest", required=True)
    p_gui.add_argument("--session", help="Pathfinder session persistence JSON")
    p_gui.add_argument("--create-session", action="store_true", help="create --session when it does not exist")
    p_gui.add_argument("--autosave", action="store_true", help="save manifest/workspace after mutating commands")
    p_gui.set_defaults(func=run_gui)

    p_desktop = sub.add_parser("desktop", help="open the Pathfinder desktop launcher")
    p_desktop.set_defaults(func=run_desktop)

    p_session = sub.add_parser("session", help="create or inspect a Pathfinder development session")
    p_session.add_argument("--manifest", help="project manifest to attach")
    p_session.add_argument("--session", help="session JSON path")
    p_session.add_argument("--create", action="store_true", help="create the session file")
    p_session.set_defaults(func=command_session)

    p_script = sub.add_parser("script", help="run a full-scope Python Pathfinder instruction script")
    p_script.add_argument("--manifest", required=True)
    p_script.add_argument("--file", required=True, help=".py instruction script")
    p_script.add_argument("--session", help="Pathfinder session persistence JSON")
    p_script.add_argument("--create-session", action="store_true", help="create --session when it does not exist")
    p_script.add_argument("--autosave", action="store_true", help="save manifest/workspace after running")
    p_script.add_argument("--save-session", action="store_true", help="save session even when --autosave is not used")
    p_script.set_defaults(func=command_script)

    p_program = sub.add_parser("program", help="list, add, or run per-state Python programs")
    p_program.add_argument("--manifest", required=True)
    p_program.add_argument("--session", help="Pathfinder session persistence JSON")
    p_program.add_argument("--create-session", action="store_true", help="create --session when it does not exist")
    p_program.add_argument("--autosave", action="store_true", help="save manifest/workspace after mutating commands")
    program_sub = p_program.add_subparsers(dest="action", required=True)
    p_program_list = program_sub.add_parser("list")
    p_program_list.add_argument("--state", default="current")
    p_program_run = program_sub.add_parser("run")
    p_program_run.add_argument("kind", choices=["input", "process", "output", "all"])
    p_program_run.add_argument("--state", default="current")
    p_program_add = program_sub.add_parser("add")
    p_program_add.add_argument("kind", choices=["input", "process", "output"])
    p_program_add.add_argument("state")
    p_program_add.add_argument("name")
    p_program_add.add_argument("code_or_file")
    p_program_add.add_argument("--event-type", default="python")
    p_program.set_defaults(func=command_program)

    p_recon = sub.add_parser("reconstruct", help="reconstruct a square image from rgb.txt or hex.txt")
    p_recon.add_argument("--input", required=True)
    p_recon.add_argument("--output", required=True)
    p_recon.set_defaults(func=command_reconstruct)

    p_seed = sub.add_parser("demo-seed", help="write a deterministic square grid-pattern seed image")
    p_seed.add_argument("--output", required=True)
    p_seed.add_argument("--size", type=int, default=32)
    p_seed.set_defaults(func=command_demo_seed)

    p_basis = sub.add_parser("basis", help="run the 16.cpp basis engine through Pathfinder")
    p_basis.add_argument("--config", required=True)
    p_basis.add_argument("--out", default="basis_tensors.json")
    p_basis.add_argument("--basis-exe")
    p_basis.add_argument("--seed-file")
    p_basis.add_argument("--seed-build")
    p_basis.add_argument("--seed-length", type=int, choices=range(1, 7), default=1)
    p_basis.add_argument("--seed-mode", choices=["strict", "wrap"], default="strict")
    p_basis.set_defaults(func=command_basis)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) == 0:
        argv = ["desktop"]
    args = parser.parse_args(argv)
    if getattr(args, "iterations", 0) < 0:
        parser.error("--iterations must be >= 0")
    if getattr(args, "basis_rows", 1) < 1:
        parser.error("--basis-rows must be >= 1")
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"pathfinder: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
