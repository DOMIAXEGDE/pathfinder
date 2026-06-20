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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


APP_NAME = "Pathfinder"
MANIFEST_TYPE = "pathfinder-manifest-v1"
WORKSPACE_TYPE = "tensor-workspace-v1"
COMPONENT_ORDER = ["p", "q", "m", "g", "alpha", "beta"]
HEX_ALPHABET = "0123456789abcdef"

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
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
    ws.dirty = False
    return ws


def save_workspace(manifest: Dict[str, Any], workspace_path: Path, pixel_mode: str) -> Path:
    tensor = load_tensor_module()
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
    return manifest


def manifest_state_map(manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(state["id"]): state for state in manifest.get("image_states", [])}


def print_status(manifest: Dict[str, Any]) -> None:
    basis = manifest.get("basis", {})
    seed_meta = basis.get("seed_metadata", {})
    print(f"{manifest.get('name', APP_NAME)} manifest: {manifest.get('type')}")
    print(f"Seed: {manifest.get('seed_image')}")
    print(f"Output: {manifest.get('output_directory')}")
    print(f"Image side: {manifest.get('image_side_length')} | states: {len(manifest.get('image_states', []))}")
    print(f"Bootstrap sequence: {' -> '.join(manifest.get('bootstrap_sequence', []))}")
    print(f"Basis rows: {seed_meta.get('basis_row_count', len(basis.get('B_raw', [])))}")
    print(f"Basis address: {shorten(str(seed_meta.get('basis_address', '')), 36)}")
    print(f"Workspace: {manifest.get('workspace_path')}")


class RuntimeController:
    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path.resolve()
        self.manifest = load_manifest(self.manifest_path)
        self.current_position = 0

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
        write_json(self.manifest_path, self.manifest)
        workspace_path = Path(self.manifest.get("workspace_path", self.manifest_path.with_suffix(".workspace.json")))
        save_workspace(self.manifest, workspace_path, self.manifest.get("workspace_pixel_mode", "compact"))

    def goto_state(self, token: str) -> str:
        seq = self.sequence
        state_map = manifest_state_map(self.manifest)
        if token.isdigit():
            index = int(token)
            if index < 0 or index >= len(seq):
                raise ValueError(f"Sequence index outside range: {index}")
            self.current_position = index
            return f"current {seq[self.current_position]}"
        if token in seq:
            self.current_position = seq.index(token)
            return f"current {token}"
        if token in state_map:
            self.manifest.setdefault("bootstrap_sequence", []).append(token)
            self.current_position = len(self.manifest["bootstrap_sequence"]) - 1
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
                "promote <state>, bind <name> <state>, save, export <path>, quit",
                False,
            )
        if cmd == "status":
            state = self.current_state_id() or "none"
            return f"current={state} states={len(self.manifest.get('image_states', []))} sequence={len(self.sequence)}", False
        if cmd == "boot":
            self.current_position = 0
            return f"current {self.current_state_id()}", False
        if cmd == "next":
            if self.sequence:
                self.current_position = (self.current_position + 1) % len(self.sequence)
            return f"current {self.current_state_id()}", False
        if cmd == "prev":
            if self.sequence:
                self.current_position = (self.current_position - 1) % len(self.sequence)
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


def run_shell(args: argparse.Namespace) -> int:
    controller = RuntimeController(Path(args.manifest))
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
    from tkinter import messagebox

    controller = RuntimeController(Path(args.manifest))

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

    def log(text: str) -> None:
        side.insert(tk.END, text.rstrip() + "\n")
        side.see(tk.END)

    def render() -> None:
        state = controller.current_state()
        canvas.delete("all")
        if not state:
            status.config(text="No state")
            return
        path = Path(state["image_path"])
        image = Image.open(path).convert("RGB")
        cw = max(1, canvas.winfo_width() or 640)
        ch = max(1, canvas.winfo_height() or 480)
        display = image.copy()
        display.thumbnail((cw - 20, ch - 20))
        tk_image = ImageTk.PhotoImage(display)
        tk_image_holder["image"] = tk_image
        canvas.create_image(cw // 2, ch // 2, image=tk_image, anchor=tk.CENTER)
        status.config(text=f"{state['id']} | {image.width}x{image.height} | {shorten(state['pixel_sha256'], 22)}")

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
            log(f"Built demo runtime: {manifest}")
        except Exception as exc:
            messagebox.showerror("Pathfinder build failed", str(exc))

    def launch_runtime() -> None:
        path = manifest_var.get().strip()
        if not path:
            messagebox.showinfo("Pathfinder", "Open or build a manifest first.")
            return
        try:
            ns = argparse.Namespace(manifest=path, autosave=True)
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
    p_shell.add_argument("--autosave", action="store_true", help="save manifest/workspace after mutating commands")
    p_shell.set_defaults(func=run_shell)

    p_gui = sub.add_parser("gui", help="run the Tk graphical Pathfinder runtime")
    p_gui.add_argument("--manifest", required=True)
    p_gui.add_argument("--autosave", action="store_true", help="save manifest/workspace after mutating commands")
    p_gui.set_defaults(func=run_gui)

    p_desktop = sub.add_parser("desktop", help="open the Pathfinder desktop launcher")
    p_desktop.set_defaults(func=run_desktop)

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
