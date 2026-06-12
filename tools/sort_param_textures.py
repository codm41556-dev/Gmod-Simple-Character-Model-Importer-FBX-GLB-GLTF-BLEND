#!/usr/bin/env python3
"""Step 12 texture and normal-map processing for MMD Character Importer."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

try:
    from PIL import Image, ImageOps
except Exception as exc:  # pragma: no cover - dependency guard
    raise SystemExit("Pillow is required for Step 12 texture processing. Install with: python -m pip install Pillow") from exc


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tif", ".tiff", ".dds"}
IMAGE_EXTENSION_PRIORITY = (".png", ".tga", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".dds")
NORMAL_HINTS = ("_n", "_hn", "_normal", "_norm", "_nrm", "_bump", "normal", "norm", "bump")
BASE_SUFFIXES = (
    "_d",
    "_diffuse",
    "_basecolor",
    "_base_color",
    "_albedo",
    "_color",
    "_col",
    "_tex",
)
NORMAL_SUFFIXES = ("_n", "_normal", "_norm", "_nrm", "_bump", "_hn", "normal", "norm", "nrm", "bump")
MAX_TEXTURE_EDGE = 4096
GENERATE_NORMAL_MIN_EDGE = 1024
SMARTNORMAL_BIAS = 85
NORMAL_REFERENCE_INTENSITY = 85.0
NORMAL_REFERENCE_STRENGTH = 3.0


@dataclass
class MaterialTexture:
    uid: str
    material_name: str
    output_name: str
    base_source_path: str
    base_color_file: str = ""
    vertex_count: int = 0
    face_count: int = 0
    warnings: list[str] = field(default_factory=list)


def emit(message: str) -> None:
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        sys.stdout.buffer.write((message + "\n").encode(encoding, errors="replace"))
        sys.stdout.flush()


def as_path(value: str | os.PathLike[str] | None) -> Path | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("//"):
        text = text[2:]
    return Path(text).expanduser()


def decode_literal_unicode_escapes(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        raw = match.group(1)
        try:
            return chr(int(raw, 16))
        except Exception:
            return match.group(0)

    return re.sub(r"\\u([0-9a-fA-F]{4})", repl, text)


def safe_basename(name: str, fallback: str, used: set[str]) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "", str(name or ""))
    if not cleaned or cleaned in used:
        cleaned = fallback
    base = cleaned
    suffix = 2
    while cleaned in used:
        cleaned = f"{base}_{suffix:02d}"
        suffix += 1
    used.add(cleaned)
    return cleaned


def resolve_material_mapping(input_path: Path) -> tuple[Path | None, Path | None, Path, Path]:
    """Return (materials_npy, materials_json, material_dir, workspace_root)."""
    path = input_path.resolve()
    candidates: list[Path] = []
    if path.is_file():
        if path.name.lower() == "materials.npy":
            candidates.append(path)
        elif path.name.lower() == "materials.json":
            sibling = path.with_name("materials.npy")
            if sibling.exists():
                candidates.append(sibling)
    elif path.is_dir():
        direct = path / "materials.npy"
        step_dir = path / "5_sort_materials" / "materials.npy"
        if direct.exists():
            candidates.append(direct)
        if step_dir.exists():
            candidates.append(step_dir)
        if not candidates:
            found = list(path.rglob("materials.npy"))
            found = [item for item in found if item.parent.name == "5_sort_materials"]
            candidates.extend(sorted(found, key=lambda item: item.stat().st_mtime, reverse=True))
    if not candidates:
        # Step 5's .npy write is best-effort, so accept a materials.json found at
        # the same locations when the sibling .npy is absent.
        json_candidates: list[Path] = []
        if path.is_file() and path.name.lower() == "materials.json":
            json_candidates.append(path)
        elif path.is_dir():
            direct_json = path / "materials.json"
            step_json = path / "5_sort_materials" / "materials.json"
            if direct_json.exists():
                json_candidates.append(direct_json)
            if step_json.exists():
                json_candidates.append(step_json)
            if not json_candidates:
                found_json = [item for item in path.rglob("materials.json") if item.parent.name == "5_sort_materials"]
                json_candidates.extend(sorted(found_json, key=lambda item: item.stat().st_mtime, reverse=True))
        if json_candidates:
            json_path = json_candidates[0].resolve()
            material_dir = json_path.parent
            workspace_root = material_dir.parent if material_dir.name == "5_sort_materials" else material_dir
            return None, json_path, material_dir, workspace_root
        raise FileNotFoundError(f"Could not locate Step 5 materials.npy or materials.json from {input_path}")
    npy_path = candidates[0].resolve()
    json_path = npy_path.with_name("materials.json")
    material_dir = npy_path.parent
    workspace_root = material_dir.parent if material_dir.name == "5_sort_materials" else material_dir
    return npy_path, (json_path if json_path.exists() else None), material_dir, workspace_root


def read_materials_json(json_path: Path, used_names: set[str]) -> list[MaterialTexture]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    rows = data.get("final_materials") or data.get("materials") or data.get("source_materials") or []
    materials: list[MaterialTexture] = []
    for index, entry in enumerate(rows, start=1):
        if not isinstance(entry, dict):
            continue
        if entry.get("keep") is False:
            continue
        base_path = str(entry.get("base_color_path") or "").strip()
        if not base_path:
            continue
        material_name = str(entry.get("proposed_name") or entry.get("material_name") or entry.get("final_name") or f"material_{index:03d}")
        output_name = safe_basename(material_name, f"mat_{index:03d}", used_names)
        warnings = [str(item) for item in entry.get("warnings", []) if item] if isinstance(entry.get("warnings"), list) else []
        materials.append(
            MaterialTexture(
                uid=str(entry.get("uid") or f"material_{index:03d}"),
                material_name=material_name,
                output_name=output_name,
                base_source_path=base_path,
                base_color_file=str(entry.get("base_color_file") or Path(base_path).name),
                vertex_count=int(entry.get("vertex_count", 0) or 0),
                face_count=int(entry.get("face_count", 0) or 0),
                warnings=warnings,
            )
        )
    return materials


def read_materials_npy(npy_path: Path, used_names: set[str]) -> list[MaterialTexture]:
    data = np.load(npy_path, allow_pickle=True)
    materials: list[MaterialTexture] = []
    for index, row in enumerate(data.tolist(), start=1):
        try:
            raw_name = str(row[0] or "").strip()
            raw_path = str(row[1] or "").strip()
        except Exception:
            continue
        if not raw_path:
            continue
        material_name = raw_name or Path(raw_path).stem
        material_name = re.sub(r"(_D|_Diffuse|_BaseColor)$", "", material_name, flags=re.IGNORECASE)
        output_name = safe_basename(material_name, f"mat_{index:03d}", used_names)
        materials.append(
            MaterialTexture(
                uid=f"material_{index:03d}",
                material_name=material_name,
                output_name=output_name,
                base_source_path=raw_path,
                base_color_file=Path(raw_path).name,
            )
        )
    return materials


def load_material_entries(input_path: Path) -> tuple[list[MaterialTexture], Path, Path, Path | None]:
    npy_path, json_path, material_dir, workspace_root = resolve_material_mapping(input_path)
    used_names: set[str] = set()
    materials = read_materials_json(json_path, used_names) if json_path else []
    if not materials and npy_path:
        materials = read_materials_npy(npy_path, used_names)
    return materials, workspace_root, material_dir, json_path


def open_image(path: Path) -> Image.Image:
    image = Image.open(path)
    image.load()
    return ImageOps.exif_transpose(image)


def image_size(path: Path) -> tuple[int, int]:
    with open_image(path) as image:
        return int(image.width), int(image.height)


def resize_to_limit(image: Image.Image, max_edge: int = MAX_TEXTURE_EDGE) -> tuple[Image.Image, bool]:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_edge:
        return image, False
    scale = max_edge / float(longest)
    size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return image.resize(size, Image.Resampling.LANCZOS), True


def normalized_stem(stem: str, suffixes: tuple[str, ...]) -> str:
    value = stem.lower()
    value = re.sub(r"[\s\-]+", "_", value)
    for suffix in suffixes:
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    return re.sub(r"[^a-z0-9]+", "", value)


def has_normal_hint(path: Path) -> bool:
    stem = f"_{path.stem.lower()}_"
    return any(hint in stem for hint in NORMAL_HINTS)


def normal_candidate_score(base_path: Path, candidate: Path) -> float:
    if candidate.resolve() == base_path.resolve():
        return -1.0
    if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
        return -1.0
    if not has_normal_hint(candidate):
        return -1.0
    base_root = normalized_stem(base_path.stem, BASE_SUFFIXES)
    cand_root = normalized_stem(candidate.stem, NORMAL_SUFFIXES)
    score = 0.0
    if base_root == cand_root:
        score += 100.0
    elif base_root and cand_root and (base_root in cand_root or cand_root in base_root):
        score += 55.0
    else:
        return -1.0
    lower = candidate.stem.lower()
    if lower.endswith("_n"):
        score += 20.0
    if lower.endswith("_normal") or lower.endswith("_norm"):
        score += 16.0
    if "_hn" in lower:
        score += 10.0
    distance = 0 if candidate.parent == base_path.parent else len(candidate.parts)
    score -= min(20.0, distance * 0.25)
    return score


def collect_search_dirs(base_path: Path, workspace_root: Path) -> list[Path]:
    dirs: list[Path] = []
    for item in (
        base_path.parent,
        base_path.parent / "textures",
        base_path.parent.parent / "textures" if base_path.parent.parent else None,
        workspace_root / "0_source_mmd_assets",
        workspace_root / "0_source_mmd_assets" / "textures",
        workspace_root / "0_source_mmd_assets" / "other tex",
    ):
        if item and item.exists() and item.is_dir() and item not in dirs:
            dirs.append(item)
    return dirs


# Per-run caches: the source asset tree can hold thousands of files and the
# material loops would otherwise re-walk it once per material.
_IMAGE_FILE_CACHE: dict[tuple[str, bool], list[Path]] = {}
_TEXTURE_FILE_KEY_CACHE: dict[str, set[str]] = {}


def iter_image_files(folder: Path, recursive: bool) -> list[Path]:
    cache_key = (str(folder.resolve()).lower(), recursive)
    cached = _IMAGE_FILE_CACHE.get(cache_key)
    if cached is None:
        iterator = folder.rglob("*") if recursive else folder.glob("*")
        cached = [
            path.resolve()
            for path in iterator
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
        _IMAGE_FILE_CACHE[cache_key] = cached
    return cached


def collect_image_files(search_dirs: list[Path]) -> list[Path]:
    seen: set[str] = set()
    files: list[Path] = []
    for folder in search_dirs:
        for path in iter_image_files(folder, recursive=folder.name == "0_source_mmd_assets"):
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            files.append(path)
    return files


def texture_name_keys(path_or_name: str | Path) -> set[str]:
    text = decode_literal_unicode_escapes(str(path_or_name or "")).strip()
    if not text:
        return set()
    name = Path(text).name
    stem = Path(name).stem
    values = {name, stem}
    if "\ufffd" in name:
        values.add(name.replace("\ufffd", ""))
        values.add(stem.replace("\ufffd", ""))
    keys: set[str] = set()
    for value in values:
        folded = value.casefold()
        keys.add(folded)
        keys.add(re.sub(r"\.[^.]+$", "", folded))
        keys.add(re.sub(r"[^a-z0-9\u0080-\uffff]+", "", folded))
    return {key for key in keys if key}


def texture_keys_for_file(path: Path) -> set[str]:
    cache_key = str(path)
    cached = _TEXTURE_FILE_KEY_CACHE.get(cache_key)
    if cached is None:
        cached = texture_name_keys(path.name)
        _TEXTURE_FILE_KEY_CACHE[cache_key] = cached
    return cached


def source_texture_search_dirs(base_path: Path | None, workspace_root: Path) -> list[Path]:
    dirs: list[Path] = []
    for item in (
        base_path.parent if base_path else None,
        workspace_root / "0_source_mmd_assets" / "tex",
        workspace_root / "0_source_mmd_assets" / "textures",
        workspace_root / "0_source_mmd_assets" / "other tex",
        workspace_root / "0_source_mmd_assets",
    ):
        if item and item.exists() and item.is_dir() and item not in dirs:
            dirs.append(item)
    return dirs


def resolve_base_texture_path(
    raw_path: str | Path | None,
    workspace_root: Path,
    base_color_file: str = "",
) -> tuple[Path | None, list[str]]:
    warnings: list[str] = []
    base_path = as_path(raw_path)
    if base_path and base_path.exists():
        return base_path.resolve(), warnings
    decoded_path = as_path(decode_literal_unicode_escapes(str(raw_path or "")))
    if decoded_path and decoded_path.exists():
        warnings.append(f"Resolved escaped texture path to {decoded_path.name}.")
        return decoded_path.resolve(), warnings

    lookup_keys = set()
    if base_path:
        lookup_keys.update(texture_name_keys(base_path.name))
    if base_color_file:
        lookup_keys.update(texture_name_keys(base_color_file))
    if decoded_path:
        lookup_keys.update(texture_name_keys(decoded_path.name))
    if not lookup_keys:
        return base_path, warnings

    candidates: list[Path] = []
    for folder in source_texture_search_dirs(base_path or decoded_path, workspace_root):
        for path in iter_image_files(folder, recursive=folder.name == "0_source_mmd_assets"):
            keys = texture_keys_for_file(path)
            if lookup_keys.intersection(keys):
                candidates.append(path)
    if not candidates:
        return base_path or decoded_path, warnings

    def score(candidate: Path) -> tuple[int, int, str]:
        suffix_rank = IMAGE_EXTENSION_PRIORITY.index(candidate.suffix.lower()) if candidate.suffix.lower() in IMAGE_EXTENSION_PRIORITY else 99
        same_parent = 0 if base_path and candidate.parent == base_path.parent else 1
        return same_parent, suffix_rank, str(candidate).casefold()

    chosen: Path | None = None
    for candidate in sorted(set(candidates), key=score):
        if candidate.suffix.lower() == ".dds":
            # Pillow handles common DXT1/3/5 DDS but not every exotic sub-format.
            try:
                with Image.open(candidate) as probe:
                    probe.load()
            except Exception:
                warnings.append(f"Skipped unreadable DDS candidate {candidate.name}.")
                continue
        chosen = candidate
        break
    if chosen is None:
        return base_path or decoded_path, warnings
    missing_name = Path(str(raw_path or "")).name
    warnings.append(f"Texture path {missing_name or raw_path} was missing; resolved to {chosen.name}.")
    return chosen, warnings


def find_normal_candidate(base_path: Path, workspace_root: Path) -> tuple[Path | None, float, list[str]]:
    warnings: list[str] = []
    files = collect_image_files(collect_search_dirs(base_path, workspace_root))
    scored = [(normal_candidate_score(base_path, candidate), candidate) for candidate in files]
    scored = [(score, candidate) for score, candidate in scored if score >= 20.0]
    scored.sort(key=lambda item: (-item[0], str(item[1]).lower()))
    if not scored:
        return None, 0.0, warnings
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 5.0:
        warnings.append(f"Ambiguous normal candidates; selected {scored[0][1].name}.")
    return scored[0][1], scored[0][0], warnings


def classify_normal_map(path: Path) -> tuple[str, dict[str, float], list[str]]:
    warnings: list[str] = []
    with open_image(path).convert("RGBA") as image:
        image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        arr = np.asarray(image).astype(np.float32) / 255.0
    rgb = arr[..., :3]
    means = rgb.reshape(-1, 3).mean(axis=0)
    stds = rgb.reshape(-1, 3).std(axis=0)
    r, g, b = [float(v) for v in means]
    sr, sg, sb = [float(v) for v in stds]
    stats = {
        "mean_r": r,
        "mean_g": g,
        "mean_b": b,
        "std_r": sr,
        "std_g": sg,
        "std_b": sb,
    }
    if b > 0.60 and b > r + 0.08 and b > g + 0.08:
        return "blue", stats, warnings
    if r > 0.42 and g > 0.42 and b < 0.62 and (sr > 0.025 or sg > 0.025):
        return "ue_rg", stats, warnings
    if b < 0.55 and r > b + 0.05 and g > b + 0.05:
        return "ue_rg", stats, warnings
    warnings.append("Normal color statistics were ambiguous.")
    return "ambiguous", stats, warnings


def normal_tone_report(path: Path) -> tuple[bool, dict[str, float], list[str]]:
    warnings: list[str] = []
    with open_image(path).convert("RGBA") as image:
        image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        arr = np.asarray(image).astype(np.float32) / 255.0
    rgb = arr[..., :3]
    means = rgb.reshape(-1, 3).mean(axis=0)
    stds = rgb.reshape(-1, 3).std(axis=0)
    r, g, b = [float(v) for v in means]
    sr, sg, sb = [float(v) for v in stds]
    luminance = float(rgb.mean())
    chroma_spread = max(r, g, b) - min(r, g, b)
    stats = {
        "mean_r": r,
        "mean_g": g,
        "mean_b": b,
        "std_r": sr,
        "std_g": sg,
        "std_b": sb,
        "mean_luminance": luminance,
        "chroma_spread": chroma_spread,
    }
    if b < 0.58:
        warnings.append("Normal preview is not blue/purple enough; blue channel is too low.")
    if b < max(r, g) + 0.045:
        warnings.append("Normal preview is not blue/purple enough; red/green dominate the blue channel.")
    if luminance < 0.28:
        warnings.append("Normal preview is too dark.")
    if r > 0.82 and g > 0.82 and b > 0.82 and max(sr, sg, sb) < 0.08:
        warnings.append("Normal preview is too white/flat.")
    if r > b + 0.04 and g > b - 0.02:
        warnings.append("Normal preview is brown/yellow rather than blue/purple.")
    return not warnings, stats, warnings


def validate_or_regenerate_normal(output_path: Path, base_source: Path, bias: int, row_report: dict[str, Any], context: str) -> None:
    ok, stats, tone_warnings = normal_tone_report(output_path)
    row_report["normal_tone_stats"] = stats
    row_report["normal_tone_ok"] = ok
    if ok:
        return
    row_report["warnings"].append(
        f"{context} normal did not pass blue/purple tone validation; regenerated from base texture."
    )
    row_report["warnings"].extend(tone_warnings)
    generate_normal_from_base(base_source, output_path, bias)
    ok_after, stats_after, warnings_after = normal_tone_report(output_path)
    row_report["normal_tone_stats"] = stats_after
    row_report["normal_tone_ok"] = ok_after
    row_report["normal_regenerated_for_tone"] = True
    row_report["generate_normal"] = True
    if not ok_after:
        row_report["warnings"].append("Generated normal still did not pass blue/purple tone validation.")
        row_report["warnings"].extend(warnings_after)
        raise RuntimeError("Generated normal failed blue/purple tone validation.")


def convert_ue_rg_normal_to_rgb(input_path: Path, output_path: Path) -> None:
    img = open_image(input_path).convert("RGBA")
    img, _ = resize_to_limit(img)
    arr = np.asarray(img).astype(np.float32) / 255.0
    r = arr[..., 0]
    g = arr[..., 1]
    a = arr[..., 3]
    nx = r * 2.0 - 1.0
    ny = g * 2.0 - 1.0
    nz_sq = np.clip(1.0 - nx * nx - ny * ny, 0.0, 1.0)
    nz = np.sqrt(nz_sq)
    out = np.stack([nx * 0.5 + 0.5, ny * 0.5 + 0.5, nz * 0.5 + 0.5, a], axis=-1)
    Image.fromarray(np.clip(out * 255.0, 0, 255).astype(np.uint8), mode="RGBA").save(output_path)


def normal_generation_strength(intensity: int | float) -> float:
    try:
        value = float(intensity)
    except Exception:
        value = float(SMARTNORMAL_BIAS)
    value = max(0.0, min(255.0, value))
    return value * (NORMAL_REFERENCE_STRENGTH / NORMAL_REFERENCE_INTENSITY)


def generate_normal_from_base(input_path: Path, output_path: Path, bias: int = SMARTNORMAL_BIAS) -> float:
    image = open_image(input_path).convert("RGBA")
    image, _ = resize_to_limit(image)
    arr = np.asarray(image).astype(np.float32) / 255.0
    luminance = arr[..., 0] * 0.2126 + arr[..., 1] * 0.7152 + arr[..., 2] * 0.0722
    padded = np.pad(luminance, 1, mode="edge")
    dx = padded[1:-1, 2:] - padded[1:-1, :-2]
    dy = padded[2:, 1:-1] - padded[:-2, 1:-1]
    strength = normal_generation_strength(bias)
    nx = -dx * strength
    ny = dy * strength
    nz = np.ones_like(nx)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx /= length
    ny /= length
    nz /= length
    out = np.stack([nx * 0.5 + 0.5, ny * 0.5 + 0.5, nz * 0.5 + 0.5, arr[..., 3]], axis=-1)
    Image.fromarray(np.clip(out * 255.0, 0, 255).astype(np.uint8), mode="RGBA").save(output_path)
    return strength


def save_base_png(input_path: Path, output_path: Path) -> tuple[tuple[int, int], tuple[int, int], bool]:
    image = open_image(input_path).convert("RGBA")
    original_size = image.size
    image, resized = resize_to_limit(image)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return original_size, image.size, resized


def save_normal_png(input_path: Path, output_path: Path) -> tuple[tuple[int, int], tuple[int, int], bool]:
    image = open_image(input_path).convert("RGBA")
    original_size = image.size
    image, resized = resize_to_limit(image)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return original_size, image.size, resized


def analyze_textures(input_path: Path, analysis_json: Path, plan_json: Path) -> dict[str, Any]:
    materials, workspace_root, material_dir, materials_json = load_material_entries(input_path)
    output_dir = workspace_root / "12_param_texture_render_materials"
    png_dir = output_dir / "png"
    normal_dir = output_dir / "png_normals"
    rows: list[dict[str, Any]] = []
    emit(f"[Step12 Textures] Loaded {len(materials)} material mappings.")
    for index, material in enumerate(materials, start=1):
        warnings = list(material.warnings)
        base_path, resolved_warnings = resolve_base_texture_path(material.base_source_path, workspace_root, material.base_color_file)
        warnings.extend(resolved_warnings)
        base_exists = bool(base_path and base_path.exists())
        base_size = [0, 0]
        output_size = [0, 0]
        base_action = "missing"
        if base_exists and base_path is not None:
            try:
                width, height = image_size(base_path)
                base_size = [width, height]
                longest = max(width, height)
                if longest > MAX_TEXTURE_EDGE:
                    scale = MAX_TEXTURE_EDGE / float(longest)
                    output_size = [max(1, int(round(width * scale))), max(1, int(round(height * scale)))]
                    base_action = "convert_downscale"
                    warnings.append(f"Base texture will be clamped to {MAX_TEXTURE_EDGE}px max edge.")
                else:
                    output_size = [width, height]
                    base_action = "copy_png" if base_path.suffix.lower() == ".png" else "convert_png"
            except Exception as exc:
                warnings.append(f"Could not inspect base texture: {exc}")
        else:
            warnings.append("Base texture source file is missing.")

        normal_source: Path | None = None
        normal_score = 0.0
        normal_type = "missing"
        normal_action = "skip_missing"
        normal_stats: dict[str, float] = {}
        if base_exists and base_path is not None:
            normal_source, normal_score, normal_warnings = find_normal_candidate(base_path, workspace_root)
            warnings.extend(normal_warnings)
            if normal_source:
                try:
                    normal_type, normal_stats, normal_warnings = classify_normal_map(normal_source)
                    warnings.extend(normal_warnings)
                    if normal_type == "ue_rg":
                        normal_action = "convert_ue_rg"
                    elif normal_type == "blue":
                        normal_action = "copy_blue"
                    else:
                        normal_action = "ambiguous_copy"
                        warnings.append("Normal candidate is ambiguous; direct PNG conversion is available if enabled.")
                    warnings.append("Normal candidate found but disabled by default to reduce addon size.")
                except Exception as exc:
                    normal_type = "unreadable"
                    normal_action = "skip_missing"
                    warnings.append(f"Could not inspect normal candidate: {exc}")
            elif max(base_size or [0, 0]) >= GENERATE_NORMAL_MIN_EDGE:
                normal_type = "generatable"
                normal_action = "skip_generate"
                warnings.append(
                    "No normal map found; normal generation is available but disabled by default to reduce addon size."
                )
            else:
                normal_type = "missing"
                normal_action = "skip_small"
                warnings.append("No normal map found; base texture is below the normal generation threshold.")

        base_output = png_dir / f"{material.output_name}.png"
        normal_output = normal_dir / f"{material.output_name}_n.png"
        row = {
            "uid": material.uid,
            "material_name": material.material_name,
            "output_name": material.output_name,
            "enabled": True,
            "base_source_path": str(base_path) if base_path else "",
            "base_source_path_original": material.base_source_path,
            "base_source_exists": base_exists,
            "base_color_file": material.base_color_file,
            "base_output_path": str(base_output),
            "base_action": base_action,
            "base_size": base_size,
            "output_size": output_size,
            "normal_source_path": str(normal_source) if normal_source else "",
            "normal_output_path": str(normal_output),
            "normal_action": "disabled",
            "normal_action_default": normal_action,
            "normal_type": normal_type,
            "normal_candidate_score": round(float(normal_score), 3),
            "normal_stats": normal_stats,
            "use_normal": False,
            "generate_normal": False,
            "force_generate_normal": False,
            "normal_intensity": SMARTNORMAL_BIAS,
            "normal_bias": SMARTNORMAL_BIAS,
            "vertex_count": material.vertex_count,
            "face_count": material.face_count,
            "warnings": warnings,
        }
        rows.append(row)
        emit(
            f"[Step12 Textures] [{index}/{len(materials)}] {material.output_name}: "
            f"base={base_action}, normal={normal_action} available, disabled by default."
        )

    analysis = {
        "version": 1,
        "input": str(input_path.resolve()),
        "workspace_root": str(workspace_root),
        "material_dir": str(material_dir),
        "materials_json": str(materials_json) if materials_json else "",
        "output_dir": str(output_dir),
        "png_dir": str(png_dir),
        "normal_dir": str(normal_dir),
        "material_count": len(rows),
        "rows": rows,
    }
    plan = {
        "version": 1,
        "input": str(input_path.resolve()),
        "workspace_root": str(workspace_root),
        "output_dir": str(output_dir),
        "png_dir": str(png_dir),
        "normal_dir": str(normal_dir),
        "rows": rows,
    }
    analysis_json.parent.mkdir(parents=True, exist_ok=True)
    analysis_json.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    plan_json.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    emit(f"[Step12 Textures] Wrote analysis: {analysis_json}")
    emit(f"[Step12 Textures] Wrote plan: {plan_json}")
    return analysis


def process_textures(input_path: Path, plan_json: Path, report_json: Path, manifest_json: Path) -> dict[str, Any]:
    plan = json.loads(plan_json.read_text(encoding="utf-8"))
    rows = [row for row in plan.get("rows", []) if isinstance(row, dict)]
    output_dir = Path(str(plan.get("output_dir") or report_json.parent))
    png_dir = Path(str(plan.get("png_dir") or output_dir / "png"))
    normal_dir = Path(str(plan.get("normal_dir") or output_dir / "png_normals"))
    png_dir.mkdir(parents=True, exist_ok=True)
    normal_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    started = time.monotonic()
    emit(f"[Step12 Textures] Processing {len(rows)} texture rows.")
    for index, row in enumerate(rows, start=1):
        if not row.get("enabled", True):
            continue
        material_name = str(row.get("material_name") or row.get("output_name") or f"material_{index:03d}")
        base_source, base_resolve_warnings = resolve_base_texture_path(
            str(row.get("base_source_path") or ""),
            output_dir.parent if output_dir.name == "12_param_texture_render_materials" else output_dir,
            str(row.get("base_color_file") or Path(str(row.get("base_source_path") or "")).name),
        )
        base_output = Path(str(row.get("base_output_path") or png_dir / f"{row.get('output_name', material_name)}.png"))
        normal_source = as_path(str(row.get("normal_source_path") or ""))
        normal_output = Path(str(row.get("normal_output_path") or normal_dir / f"{row.get('output_name', material_name)}_n.png"))
        row_report = {
            "uid": row.get("uid"),
            "material_name": material_name,
            "output_name": row.get("output_name"),
            "base_source_path": str(base_source) if base_source else "",
            "base_output_path": str(base_output),
            "normal_source_path": str(normal_source) if normal_source else "",
            "normal_output_path": "",
            "normal_status": row.get("normal_action", "disabled"),
            "warnings": list(row.get("warnings", [])) if isinstance(row.get("warnings"), list) else [],
        }
        if base_source and base_source.exists() and base_resolve_warnings:
            row_report["warnings"] = [
                warning for warning in row_report["warnings"] if warning != "Base texture source file is missing."
            ]
        row_report["warnings"].extend(base_resolve_warnings)
        try:
            if not base_source or not base_source.exists():
                raise FileNotFoundError(f"Base texture not found for {material_name}: {base_source}")
            original_size, final_size, resized = save_base_png(base_source, base_output)
            row_report["base_original_size"] = list(original_size)
            row_report["base_output_size"] = list(final_size)
            row_report["base_resized"] = resized
        except Exception as exc:
            errors.append(str(exc))
            row_report["error"] = str(exc)
            manifest_rows.append(row_report)
            emit(f"[Step12 Textures] [{index}/{len(rows)}] {material_name}: ERROR {exc}")
            continue

        normal_action = str(row.get("normal_action") or "disabled")
        default_normal_action = str(row.get("normal_action_default") or normal_action or "skip_missing")
        use_normal = bool(row.get("use_normal", row.get("generate_normal", False)))
        force_generate = bool(row.get("force_generate_normal", False))
        if force_generate:
            use_normal = True
        normal_intensity = int(row.get("normal_intensity") or row.get("normal_bias") or SMARTNORMAL_BIAS)
        normal_applied_strength = normal_generation_strength(normal_intensity)
        row_report["use_normal"] = use_normal
        row_report["generate_normal"] = force_generate or (use_normal and default_normal_action in {"generate", "skip_generate"})
        row_report["force_generate_normal"] = force_generate
        row_report["normal_intensity"] = normal_intensity
        row_report["normal_applied_strength"] = round(float(normal_applied_strength), 6)
        try:
            if not use_normal:
                row_report["normal_status"] = "disabled"
            elif force_generate:
                normal_output.parent.mkdir(parents=True, exist_ok=True)
                generate_normal_from_base(base_source, normal_output, normal_intensity)
                validate_or_regenerate_normal(normal_output, base_source, normal_intensity, row_report, "Generated")
                row_report["normal_output_path"] = str(normal_output)
                row_report["normal_status"] = "generated_override"
            elif normal_source and normal_source.exists() and default_normal_action in {"copy_blue", "ambiguous_copy"}:
                _orig, _final, resized = save_normal_png(normal_source, normal_output)
                validate_or_regenerate_normal(normal_output, base_source, normal_intensity, row_report, "Copied")
                row_report["normal_output_path"] = str(normal_output)
                row_report["normal_resized"] = resized
                row_report["normal_status"] = "regenerated_for_tone" if row_report.get("normal_regenerated_for_tone") else default_normal_action
            elif normal_source and normal_source.exists() and default_normal_action == "convert_ue_rg":
                normal_output.parent.mkdir(parents=True, exist_ok=True)
                convert_ue_rg_normal_to_rgb(normal_source, normal_output)
                validate_or_regenerate_normal(normal_output, base_source, normal_intensity, row_report, "Converted")
                row_report["normal_output_path"] = str(normal_output)
                row_report["normal_status"] = "regenerated_for_tone" if row_report.get("normal_regenerated_for_tone") else default_normal_action
            elif default_normal_action in {"generate", "skip_generate"}:
                normal_output.parent.mkdir(parents=True, exist_ok=True)
                generate_normal_from_base(base_source, normal_output, normal_intensity)
                validate_or_regenerate_normal(normal_output, base_source, normal_intensity, row_report, "Generated")
                row_report["normal_output_path"] = str(normal_output)
                row_report["normal_status"] = "generated"
            elif default_normal_action in {"copy_blue", "ambiguous_copy", "convert_ue_rg"}:
                # Normal use is enabled, but the recorded source no longer exists.
                raise FileNotFoundError(f"Normal source file is missing: {normal_source or row.get('normal_source_path') or '(unknown)'}")
            else:
                row_report["normal_status"] = default_normal_action
        except Exception as exc:
            row_report["warnings"].append(f"Normal processing failed: {exc}")
            row_report["normal_status"] = "failed"
        manifest_rows.append(row_report)
        emit(
            f"[Step12 Textures] [{index}/{len(rows)}] {material_name}: "
            f"base -> {base_output.name}, normal={row_report['normal_status']}."
        )

    manifest = {
        "version": 1,
        "input": str(input_path.resolve()),
        "output_dir": str(output_dir),
        "png_dir": str(png_dir),
        "normal_dir": str(normal_dir),
        "textures": manifest_rows,
    }
    report = {
        "version": 1,
        "input": str(input_path.resolve()),
        "output_dir": str(output_dir),
        "processed_count": len([row for row in manifest_rows if not row.get("error")]),
        "error_count": len(errors),
        "errors": errors,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "manifest_path": str(manifest_json),
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    emit(f"[Step12 Textures] Wrote report: {report_json}")
    emit(f"[Step12 Textures] Wrote manifest: {manifest_json}")
    if errors:
        raise RuntimeError(f"Texture processing completed with {len(errors)} blocking error(s).")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("analyze", "process"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--analysis-json", type=Path)
    parser.add_argument("--plan-json", type=Path, required=True)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--manifest-json", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "analyze":
        if not args.analysis_json:
            parser.error("--analysis-json is required for analyze mode")
        analyze_textures(args.input, args.analysis_json, args.plan_json)
        return 0
    if not args.report_json or not args.manifest_json:
        parser.error("--report-json and --manifest-json are required for process mode")
    process_textures(args.input, args.plan_json, args.report_json, args.manifest_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
