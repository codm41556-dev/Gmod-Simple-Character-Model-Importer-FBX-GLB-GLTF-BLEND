#!/usr/bin/env python3
"""Blender-side step 1 PMX import helper."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmx", type=Path, required=True)
    parser.add_argument("--output-blend", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    return parser.parse_args(argv)


def operator_keywords(operator, desired: dict[str, object]) -> dict[str, object]:
    try:
        props = {prop.identifier for prop in operator.get_rna_type().properties}
    except Exception:
        return desired
    return {key: value for key, value in desired.items() if key in props}


def call_operator(operator, **desired):
    kwargs = operator_keywords(operator, desired)
    try:
        result = operator(**kwargs)
    except Exception as exc:
        raise RuntimeError(f"{operator.idname()} failed with arguments {sorted(kwargs)}: {exc}") from exc
    if isinstance(result, set) and "CANCELLED" in result:
        raise RuntimeError(f"{operator.idname()} was cancelled by Blender/CATS")
    return result


def cats_registered() -> bool:
    try:
        bpy.ops.cats_importer.import_any_model.get_rna_type()
        return True
    except Exception:
        return False


def dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def cats_candidates() -> list[str]:
    import addon_utils

    preferred = [
        "bl_ext.user_default.cats_blender_plugin",
        "bl_ext.blender_org.cats_blender_plugin",
        "cats_blender_plugin",
    ]
    discovered: list[str] = []
    try:
        for module in addon_utils.modules(refresh=True):
            name = getattr(module, "__name__", "")
            if name.endswith("cats_blender_plugin") or "cats_blender_plugin" in name:
                discovered.append(name)
    except Exception:
        pass
    return dedupe(preferred + discovered)


def enable_cats() -> None:
    import addon_utils

    errors: list[str] = []
    if cats_registered():
        print("CATS importer operator is already available.")
        return
    for module_name in cats_candidates():
        try:
            addon_utils.enable(module_name, default_set=False, persistent=False)
            print(f"Enabled CATS add-on module: {module_name}")
            if cats_registered():
                return
        except Exception as exc:
            errors.append(f"{module_name}: {exc}")
    detail = "; ".join(errors) if errors else "no CATS add-on module candidates were found"
    raise RuntimeError(f"CATS importer operator is not available: {detail}")


def clear_scene() -> None:
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def setup_scene() -> None:
    scene = bpy.context.scene
    with context_suppressed():
        scene.render.engine = "CYCLES"
        scene.cycles.device = "GPU"
    scene.render.film_transparent = True
    scene.render.resolution_x = 2000
    scene.render.resolution_y = 2000
    world = bpy.data.worlds.get("World")
    if world and world.node_tree:
        background = world.node_tree.nodes.get("Background")
        if background:
            background.inputs[0].default_value = (1, 1, 1, 1)


class context_suppressed:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return exc_type is not None


def import_with_cats(pmx_path: Path) -> None:
    print(f"Importing PMX with CATS: {pmx_path}")
    call_operator(bpy.ops.cats_importer.import_any_model, filepath=str(pmx_path))
    print(f"Imported PMX with CATS: {pmx_path}")


def validate_imported_scene(pmx_path: Path) -> None:
    imported_meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    imported_armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    vertex_count = sum(len(obj.data.vertices) for obj in imported_meshes)
    if not imported_armatures or not imported_meshes or vertex_count == 0:
        raise RuntimeError(
            f"CATS import produced no usable model from {pmx_path}: "
            f"{len(imported_armatures)} armature(s), {len(imported_meshes)} mesh object(s), {vertex_count} vertices. "
            "The PMX file may be corrupt or unsupported."
        )


def build_report(pmx_path: Path, output_blend: Path, elapsed: float) -> dict[str, object]:
    mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    material_names = {
        material.name
        for obj in mesh_objects
        for material in getattr(obj.data, "materials", [])
        if material is not None
    }
    shapekey_count = 0
    for mesh in bpy.data.meshes:
        if mesh.shape_keys:
            shapekey_count += max(0, len(mesh.shape_keys.key_blocks) - 1)

    return {
        "pmx_path": str(pmx_path),
        "output_blend": str(output_blend),
        "elapsed_seconds": round(elapsed, 3),
        "object_count": len(bpy.data.objects),
        "mesh_object_count": len(mesh_objects),
        "mesh_data_count": len(bpy.data.meshes),
        "vertex_count": sum(len(obj.data.vertices) for obj in mesh_objects),
        "material_count": len(material_names),
        "image_count": len([image for image in bpy.data.images if image.filepath or image.packed_file]),
        "armature_count": len(armatures),
        "armature_bone_count": sum(len(obj.data.bones) for obj in armatures),
        "shapekey_count": shapekey_count,
        "objects": [
            {
                "name": obj.name,
                "type": obj.type,
                "vertices": len(obj.data.vertices) if obj.type == "MESH" else 0,
                "bones": len(obj.data.bones) if obj.type == "ARMATURE" else 0,
            }
            for obj in bpy.data.objects
        ],
    }


def main() -> int:
    args = parse_args()
    if not args.pmx.exists():
        raise FileNotFoundError(args.pmx)

    started = time.monotonic()
    args.output_blend.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.parent.mkdir(parents=True, exist_ok=True)

    print("Starting MMD Character Importer Blender step 1.")
    enable_cats()
    clear_scene()
    setup_scene()
    import_with_cats(args.pmx)
    validate_imported_scene(args.pmx)
    print(f"Saving blend file: {args.output_blend}")
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend))
    report = build_report(args.pmx, args.output_blend, time.monotonic() - started)
    args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote import report: {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
