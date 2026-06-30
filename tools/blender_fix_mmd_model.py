#!/usr/bin/env python3
"""Blender-side step 2 model fix and Source skeleton conversion helper."""

from __future__ import annotations

import argparse
import json
import re
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
    parser.add_argument("--vrm-spine-merge", dest="vrm_spine_merge", action="store_true", default=False)
    parser.add_argument(
        "--skip-cats-fix",
        dest="skip_cats_fix",
        action="store_true",
        default=False,
        help=(
            "Skip CATS' fix_armature_warning/translate/convert_to_valve passes. "
            "Used for generic FBX/GLB/blend imports whose bones were already "
            "renamed to ValveBiped names by the heuristic mapper in Step 1, and "
            "for armature structures (e.g. Rigify control/mechanism/deform "
            "layers) that CATS explicitly refuses to process."
        ),
    )
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


# Bones whose names contain these tokens are normally treated as the humanoid
# spine by CATS' Fix Model / Convert to Valve. A bone that matches one of these
# AND sits far off the body's center axis is not a real spine bone — it is a
# decoration/physics chain the modeler merely named "spine". Left untouched it
# hijacks the ValveBiped spine conversion and produces an off-center
# ValveBiped.Bip01_Spine1 that step 3 cannot repair (GitHub issue #86).
MISDETECTED_SPINE_TOKENS = ("spine",)
# Off-center tolerance for the gate above, expressed as a fraction of the
# armature's vertical extent (with an absolute floor for tiny rigs). Real
# humanoid spine bones sit on the center axis (offset ~0), so this never touches
# a correct spine; only sideways accessories exceed it. The 0.075 value sits in
# a clean, empirically measured gap: across the known-good model corpus the most
# off-center benign "spine"-named accessory (a ribbon chain) reaches ~0.055 of
# height, while the spine-hijacking chain from issue #86 starts at ~0.099 — so
# 0.075 catches the real culprits with margin and leaves every benign accessory
# (and every correctly centered spine) untouched.
SPINE_ACCESSORY_OFFCENTER_FRACTION = 0.075
SPINE_ACCESSORY_OFFCENTER_FLOOR = 0.03


def _unique_bone_name(base: str, taken: set[str]) -> str:
    candidate = base
    index = 1
    while candidate in taken or not candidate:
        candidate = f"{base}.{index:03d}"
        index += 1
    taken.add(candidate)
    return candidate


def protect_misdetected_spine_accessories() -> dict[str, object]:
    """Rename off-center "spine"-named accessory bones before CATS conversion.

    Some models carry decoration/physics chains literally named "...Spine..."
    that sit far to one side of the body. CATS' Fix Model + Convert to Valve
    treat them as humanoid spine bones and can map one onto
    ValveBiped.Bip01_Spine1, leaving the real (centered) spine collapsed and an
    off-center Spine1 that step 3's spine repair cannot resolve (issue #86).

    We rename such bones (and their matching vertex groups, so weights stay
    attached) to a neutral name that no longer contains a spine token, before
    CATS runs, so the real centered spine is used for the conversion instead.
    The off-center gate means correctly centered spine bones are never affected,
    so standard models are untouched.
    """
    result: dict[str, object] = {"checked": False, "renamed": []}
    renamed: list[dict[str, object]] = []
    rename_map: dict[str, str] = {}
    for armature in armatures():
        bones = armature.data.bones
        if not bones:
            continue
        result["checked"] = True
        zs = [coord for bone in bones for coord in (bone.head_local.z, bone.tail_local.z)]
        height = (max(zs) - min(zs)) if zs else 0.0
        sorted_x = sorted(bone.head_local.x for bone in bones)
        center_x = sorted_x[len(sorted_x) // 2] if sorted_x else 0.0
        tolerance = max(SPINE_ACCESSORY_OFFCENTER_FLOOR, SPINE_ACCESSORY_OFFCENTER_FRACTION * height)
        taken = {bone.name for bone in bones}
        targets: list[str] = []
        for bone in bones:
            name = bone.name
            if name.startswith("ValveBiped"):
                continue
            low = name.lower()
            if not any(token in low for token in MISDETECTED_SPINE_TOKENS):
                continue
            offset = abs(bone.head_local.x - center_x)
            if offset <= tolerance:
                continue
            base = re.sub(r"(?i)spine", "AccChain", name)
            if any(token in base.lower() for token in MISDETECTED_SPINE_TOKENS):
                base = "AccChain_" + re.sub(r"(?i)spine", "", name).strip("_")
            new_name = _unique_bone_name(base, taken)
            rename_map[name] = new_name
            targets.append(name)
            renamed.append(
                {
                    "armature": armature.name,
                    "old": name,
                    "new": new_name,
                    "x_offset": round(offset, 4),
                    "tolerance": round(tolerance, 4),
                }
            )
        if not targets:
            continue
        set_active_object(armature)
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            edit_bones = armature.data.edit_bones
            for name in targets:
                edit_bone = edit_bones.get(name)
                if edit_bone is not None:
                    edit_bone.name = rename_map[name]
        finally:
            ensure_object_mode()
    if rename_map:
        for obj in mesh_objects():
            for old_name, new_name in rename_map.items():
                group = obj.vertex_groups.get(old_name)
                if group is not None:
                    group.name = new_name
        print(f"Protected {len(renamed)} off-center spine-named accessory bone(s) before CATS conversion:")
        for entry in renamed:
            print(f"  {entry['old']} -> {entry['new']} (x offset {entry['x_offset']} > tolerance {entry['tolerance']})")
    else:
        print("No off-center spine-named accessory bones detected; spine conversion proceeds normally.")
    result["renamed"] = renamed
    return result


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


SPINE1_BONE = "ValveBiped.Bip01_Spine1"
SPINE2_BONE = "ValveBiped.Bip01_Spine2"


def merge_vertex_group(obj: bpy.types.Object, source: str, target: str) -> bool:
    if source not in obj.vertex_groups:
        return False
    source_group = obj.vertex_groups[source]
    if target not in obj.vertex_groups:
        source_group.name = target
        return True
    target_group = obj.vertex_groups[target]
    for vertex in obj.data.vertices:
        for group in vertex.groups:
            if group.group == source_group.index and group.weight > 0.0:
                target_group.add([vertex.index], group.weight, "ADD")
                break
    obj.vertex_groups.remove(source_group)
    return True


def merge_vrm_spine2_into_spine1() -> dict[str, object]:
    """Collapse the VRM upper chest into the chest after ValveBiped conversion.

    VRM humanoid skeletons map chest -> Spine1 and upperChest -> Spine2, which
    leaves the torso split differently from MMD models and breaks downstream
    spine repair. Merging Spine2 into Spine1 (weights + children) gives step 3
    the collapsed Pelvis/Spine/Spine1 chain it already knows how to rebuild.
    """
    result: dict[str, object] = {"merged": False, "source": SPINE2_BONE, "target": SPINE1_BONE}
    armature = next((obj for obj in armatures() if SPINE2_BONE in obj.data.bones), None)
    if armature is None:
        result["reason"] = f"{SPINE2_BONE} not found"
        print(f"VRM spine merge skipped: {SPINE2_BONE} does not exist after conversion.")
        return result
    if SPINE1_BONE not in armature.data.bones:
        result["reason"] = f"{SPINE1_BONE} not found"
        print(f"Warning: VRM spine merge skipped: {SPINE1_BONE} is missing, cannot merge {SPINE2_BONE} into it.")
        return result
    print(f"Merging VRM bone {SPINE2_BONE} into {SPINE1_BONE}.")
    weight_merged_objects = [obj.name for obj in mesh_objects() if merge_vertex_group(obj, SPINE2_BONE, SPINE1_BONE)]
    set_active_object(armature)
    reparented: list[str] = []
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        edit_bones = armature.data.edit_bones
        source_bone = edit_bones[SPINE2_BONE]
        target_bone = edit_bones[SPINE1_BONE]
        original_parent = source_bone.parent.name if source_bone.parent else None
        for child in list(source_bone.children):
            if child == target_bone:
                continue
            child.parent = target_bone
            child.use_connect = False
            reparented.append(child.name)
        if target_bone.parent == source_bone:
            target_bone.parent = edit_bones[original_parent] if original_parent and original_parent in edit_bones else None
            target_bone.use_connect = False
        edit_bones.remove(source_bone)
    finally:
        ensure_object_mode()
    result.update(
        {
            "merged": True,
            "reparented_children": reparented,
            "weight_merged_objects": weight_merged_objects,
        }
    )
    print(f"Merged {SPINE2_BONE} into {SPINE1_BONE}; reparented {len(reparented)} child bone(s): {', '.join(reparented) or 'none'}.")
    return result


def valve_bone_status(excluded: set[str] | None = None) -> dict[str, object]:
    required = VALVE_REQUIRED_BONES - (excluded or set())
    names: set[str] = set()
    for armature in armatures():
        names.update(bone.name for bone in armature.data.bones)
    missing = sorted(required - names)
    return {
        "required_count": len(required),
        "present_count": len(required) - len(missing),
        "missing": missing,
    }


def build_report(
    input_blend: Path,
    output_blend: Path,
    elapsed: float,
    clear_custom_normals_enabled: bool,
    initial_cleared_custom_normals: int,
    final_cleared_custom_normals: int,
    vrm_spine_merge: dict[str, object] | None = None,
    spine_accessory_protection: dict[str, object] | None = None,
) -> dict[str, object]:
    merged_away = {SPINE2_BONE} if vrm_spine_merge and vrm_spine_merge.get("merged") else set()
    status = valve_bone_status(excluded=merged_away)
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
        "vrm_spine_merge": vrm_spine_merge,
        "spine_accessory_protection": spine_accessory_protection,
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
    if args.skip_cats_fix:
        print("Generic import: CATS add-on is not required for this model and will not be loaded.")
    else:
        enable_cats()
    make_single_user()
    spine_accessory_protection = protect_misdetected_spine_accessories()
    if args.clear_custom_normals:
        initial_cleared_custom_normals = clear_custom_normals("before model fix")
    else:
        print("Skipping custom split normal cleanup before model fix.")
        initial_cleared_custom_normals = 0
    if args.skip_cats_fix:
        print(
            "Skipping CATS fix_armature/translate/convert_to_valve passes "
            "(generic FBX/GLB/blend import: bones already use ValveBiped "
            "names from Step 1's heuristic mapping)."
        )
    else:
        fix_armature_twice()
        translate_with_cats()
        convert_to_valve()
    vrm_spine_merge = merge_vrm_spine2_into_spine1() if args.vrm_spine_merge else None
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
        vrm_spine_merge,
        spine_accessory_protection,
    )
    missing_valve_bones = report["valve_bones"]["missing"]
    if missing_valve_bones:
        print("Warning: Missing expected ValveBiped bones after conversion: " + ", ".join(missing_valve_bones))
    args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote fix report: {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
