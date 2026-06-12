#!/usr/bin/env python3
"""Blender-side step 2 model fix and Source skeleton conversion helper."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import bpy


VALVE_REQUIRED_BONES = {
    "ValveBiped.Bip01_Pelvis",
    "ValveBiped.Bip01_Spine",
    "ValveBiped.Bip01_Spine1",
    "ValveBiped.Bip01_Spine2",
    "ValveBiped.Bip01_Neck1",
    "ValveBiped.Bip01_Head1",
    "ValveBiped.Bip01_L_UpperArm",
    "ValveBiped.Bip01_R_UpperArm",
    "ValveBiped.Bip01_L_Forearm",
    "ValveBiped.Bip01_R_Forearm",
    "ValveBiped.Bip01_L_Hand",
    "ValveBiped.Bip01_R_Hand",
    "ValveBiped.Bip01_L_Thigh",
    "ValveBiped.Bip01_R_Thigh",
    "ValveBiped.Bip01_L_Calf",
    "ValveBiped.Bip01_R_Calf",
    "ValveBiped.Bip01_L_Foot",
    "ValveBiped.Bip01_R_Foot",
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-blend", type=Path, required=True)
    parser.add_argument("--output-blend", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--clear-custom-normals", dest="clear_custom_normals", action="store_true", default=False)
    parser.add_argument("--keep-custom-normals", dest="clear_custom_normals", action="store_false")
    return parser.parse_args(argv)


def operator_keywords(operator, desired: dict[str, object]) -> dict[str, object]:
    try:
        props = {prop.identifier for prop in operator.get_rna_type().properties}
    except Exception:
        return desired
    return {key: value for key, value in desired.items() if key in props}


def call_operator(operator, label: str = "", **desired):
    kwargs = operator_keywords(operator, desired)
    try:
        result = operator(**kwargs)
    except Exception as exc:
        name = label or operator.idname()
        raise RuntimeError(f"{name} failed with arguments {sorted(kwargs)}: {exc}") from exc
    if isinstance(result, set) and "CANCELLED" in result:
        name = label or operator.idname()
        raise RuntimeError(f"{name} was cancelled by Blender/CATS")
    return result


def dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def cats_registered() -> bool:
    try:
        bpy.ops.cats_armature.fix_armature_warning.get_rna_type()
        bpy.ops.cats_translate.bones.get_rna_type()
        bpy.ops.cats_translate.shapekeys.get_rna_type()
        bpy.ops.cats_translate.objects.get_rna_type()
        bpy.ops.cats_translate.materials.get_rna_type()
        bpy.ops.cats_manual.convert_to_valve.get_rna_type()
        return True
    except Exception:
        return False


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

    if cats_registered():
        print("CATS fix and conversion operators are already available.")
        return
    errors: list[str] = []
    for module_name in cats_candidates():
        try:
            addon_utils.enable(module_name, default_set=False, persistent=False)
            print(f"Enabled CATS add-on module: {module_name}")
            if cats_registered():
                return
        except Exception as exc:
            errors.append(f"{module_name}: {exc}")
    detail = "; ".join(errors) if errors else "no CATS add-on module candidates were found"
    raise RuntimeError(f"CATS fix/conversion operators are not available: {detail}")


def ensure_object_mode() -> None:
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")


def select_all_objects() -> None:
    ensure_object_mode()
    bpy.ops.object.select_all(action="SELECT")


def set_active_object(obj: bpy.types.Object) -> None:
    ensure_object_mode()
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def armatures() -> list[bpy.types.Object]:
    return [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]


def mesh_objects() -> list[bpy.types.Object]:
    return [obj for obj in bpy.data.objects if obj.type == "MESH"]


def set_active_armature() -> bpy.types.Object:
    candidates = armatures()
    if not candidates:
        raise RuntimeError("No armature found in the imported blend file.")
    armature = candidates[0]
    select_all_objects()
    bpy.context.view_layer.objects.active = armature
    return armature


def make_single_user() -> None:
    print("Making all imported objects, object data, materials, and animation single-user.")
    select_all_objects()
    call_operator(
        bpy.ops.object.make_single_user,
        "Make single user",
        object=True,
        obdata=True,
        material=True,
        animation=True,
        obdata_animation=True,
    )
    print("Single-user conversion completed.")


def custom_split_normals_clear_operator():
    for operator_name in ("customdata_custom_split_normals_clear", "customdata_custom_splitnormals_clear"):
        operator = getattr(bpy.ops.mesh, operator_name, None)
        if operator is None:
            continue
        try:
            operator.get_rna_type()
            return operator, operator_name
        except Exception:
            continue
    return None, ""


def clear_mesh_custom_normals_data(mesh: bpy.types.Mesh) -> bool:
    try:
        attribute = mesh.attributes.get("custom_normal")
        if attribute is not None:
            mesh.attributes.remove(attribute)
    except Exception:
        pass
    mesh.update()
    return not getattr(mesh, "has_custom_normals", False)


def clear_custom_normals(stage: str = "") -> int:
    cleared = 0
    suffix = f" ({stage})" if stage else ""
    print(f"Clearing custom split normals from mesh data when present{suffix}.")
    clear_operator, clear_operator_name = custom_split_normals_clear_operator()
    for obj in mesh_objects():
        mesh = obj.data
        if not getattr(mesh, "has_custom_normals", False):
            continue
        set_active_object(obj)
        try:
            if clear_operator is None:
                raise RuntimeError("No custom split normal clear operator is available.")
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            call_operator(clear_operator, f"Clear custom normals on {obj.name} via {clear_operator_name}")
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            ensure_object_mode()
            clear_mesh_custom_normals_data(mesh)
        if getattr(mesh, "has_custom_normals", False):
            print(f"Warning: could not clear custom split normals on {obj.name}{suffix}; the mesh keeps its custom normals.")
            continue
        cleared += 1
    ensure_object_mode()
    print(f"Cleared custom normals on {cleared} mesh object(s){suffix}.")
    return cleared


def fix_armature_twice() -> None:
    for index in range(2):
        print(f"Running CATS Fix Model pass {index + 1}/2.")
        set_active_armature()
        call_operator(bpy.ops.cats_armature.fix_armature_warning, f"CATS Fix Model pass {index + 1}")
    print("CATS Fix Model passes completed.")


def translate_with_cats() -> None:
    print("Translating bones, shapekeys, objects, and materials with CATS dictionaries.")
    set_active_armature()
    for label, operator in (
        ("Translate bones", bpy.ops.cats_translate.bones),
        ("Translate shapekeys", bpy.ops.cats_translate.shapekeys),
        ("Translate objects", bpy.ops.cats_translate.objects),
        ("Translate materials", bpy.ops.cats_translate.materials),
    ):
        try:
            call_operator(operator, label)
            print(f"{label} completed.")
        except Exception as exc:
            print(f"Warning: {label} failed or was skipped: {exc}")


def convert_to_valve() -> None:
    print("Converting CATS standard bones to ValveBiped names.")
    armature = set_active_armature()
    call_operator(bpy.ops.cats_manual.convert_to_valve, "Convert to Valve", armature_name=armature.name)
    print("ValveBiped bone conversion completed.")


def valve_bone_status() -> dict[str, object]:
    names: set[str] = set()
    for armature in armatures():
        names.update(bone.name for bone in armature.data.bones)
    missing = sorted(VALVE_REQUIRED_BONES - names)
    return {
        "required_count": len(VALVE_REQUIRED_BONES),
        "present_count": len(VALVE_REQUIRED_BONES) - len(missing),
        "missing": missing,
    }


def build_report(
    input_blend: Path,
    output_blend: Path,
    elapsed: float,
    clear_custom_normals_enabled: bool,
    initial_cleared_custom_normals: int,
    final_cleared_custom_normals: int,
) -> dict[str, object]:
    status = valve_bone_status()
    shapekey_count = 0
    for mesh in bpy.data.meshes:
        if mesh.shape_keys:
            shapekey_count += max(0, len(mesh.shape_keys.key_blocks) - 1)
    return {
        "input_blend": str(input_blend),
        "output_blend": str(output_blend),
        "elapsed_seconds": round(elapsed, 3),
        "object_count": len(bpy.data.objects),
        "mesh_object_count": len(mesh_objects()),
        "mesh_data_count": len(bpy.data.meshes),
        "vertex_count": sum(len(obj.data.vertices) for obj in mesh_objects()),
        "material_count": len({slot.material.name for obj in mesh_objects() for slot in obj.material_slots if slot.material}),
        "image_count": len([image for image in bpy.data.images if image.filepath or image.packed_file]),
        "armature_count": len(armatures()),
        "armature_bone_count": sum(len(obj.data.bones) for obj in armatures()),
        "shapekey_count": shapekey_count,
        "custom_normal_clear_enabled": bool(clear_custom_normals_enabled),
        "custom_normal_meshes_cleared": initial_cleared_custom_normals + final_cleared_custom_normals,
        "custom_normal_meshes_cleared_initial": initial_cleared_custom_normals,
        "custom_normal_meshes_cleared_final": final_cleared_custom_normals,
        "valve_bones": status,
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
    if not args.input_blend.exists():
        raise FileNotFoundError(args.input_blend)
    args.output_blend.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.parent.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    print("Starting MMD Character Importer Blender step 2.")
    print(f"Opening imported blend: {args.input_blend}")
    bpy.ops.wm.open_mainfile(filepath=str(args.input_blend))
    enable_cats()
    make_single_user()
    if args.clear_custom_normals:
        initial_cleared_custom_normals = clear_custom_normals("before model fix")
    else:
        print("Skipping custom split normal cleanup before model fix.")
        initial_cleared_custom_normals = 0
    fix_armature_twice()
    translate_with_cats()
    convert_to_valve()
    if args.clear_custom_normals:
        final_cleared_custom_normals = clear_custom_normals("after model fix")
    else:
        print("Skipping custom split normal cleanup after model fix.")
        final_cleared_custom_normals = 0
    print(f"Saving fixed blend file: {args.output_blend}")
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend))
    report = build_report(
        args.input_blend,
        args.output_blend,
        time.monotonic() - started,
        args.clear_custom_normals,
        initial_cleared_custom_normals,
        final_cleared_custom_normals,
    )
    missing_valve_bones = report["valve_bones"]["missing"]
    if missing_valve_bones:
        print("Warning: Missing expected ValveBiped bones after conversion: " + ", ".join(missing_valve_bones))
    args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote fix report: {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
