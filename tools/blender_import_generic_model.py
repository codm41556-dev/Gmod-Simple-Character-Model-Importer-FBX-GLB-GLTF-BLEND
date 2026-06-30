#!/usr/bin/env python3
"""Blender-side importer for FBX, GLB, and GLTF formats.

This script is called headlessly by mmd_character_importer_core.py.
It imports the model, maps common bone names to the ValveBiped skeleton,
rescales the model, and saves a .blend ready for the 'fix' step.
"""

import bpy
import sys
import json
import argparse
from pathlib import Path


# ---------------------------------------------------------------------------
# Heuristic Bone Mapping Dictionary
# Maps common FBX/GLB bone names (Mixamo, Unity, Unreal, generic) to
# ValveBiped names.
#
# Spine chain notes:
#   Spine        -> Bip01_Spine   (lower spine)
#   Chest/Spine1 -> Bip01_Spine1  (mid spine)
#   UpperChest/Spine2 -> Bip01_Spine4  (upper chest / shoulder anchor)
#   Bip01_Spine2 is NOT mapped here; it is auto-added by
#   blender_fix_spine_bones.py at the correct interpolated position.
# ---------------------------------------------------------------------------
HEURISTIC_BONE_MAP = {
    # ---- Hips / Root ----
    "Hips":                     "ValveBiped.Bip01_Pelvis",
    "mixamorig:Hips":           "ValveBiped.Bip01_Pelvis",
    "Root":                     "ValveBiped.Bip01_Pelvis",
    "Pelvis":                   "ValveBiped.Bip01_Pelvis",

    # ---- Spine ----
    "Spine":                    "ValveBiped.Bip01_Spine",
    "mixamorig:Spine":          "ValveBiped.Bip01_Spine",
    "Chest":                    "ValveBiped.Bip01_Spine1",
    "mixamorig:Spine1":         "ValveBiped.Bip01_Spine1",
    "Spine1":                   "ValveBiped.Bip01_Spine1",
    # UpperChest/Spine2 -> Spine4 (upper-chest anchor in Source Engine).
    # Spine2 (mid-chest) is auto-added by the fix script.
    "UpperChest":               "ValveBiped.Bip01_Spine4",
    "mixamorig:Spine2":         "ValveBiped.Bip01_Spine4",
    "Spine2":                   "ValveBiped.Bip01_Spine4",

    # ---- Neck & Head ----
    # Fix script requires Bip01_Neck1 and Bip01_Head1 (trailing 1).
    "Neck":                     "ValveBiped.Bip01_Neck1",
    "mixamorig:Neck":           "ValveBiped.Bip01_Neck1",
    "Neck1":                    "ValveBiped.Bip01_Neck1",
    "Head":                     "ValveBiped.Bip01_Head1",
    "mixamorig:Head":           "ValveBiped.Bip01_Head1",

    # ---- Left Arm ----
    "LeftShoulder":             "ValveBiped.Bip01_L_Clavicle",
    "mixamorig:LeftShoulder":   "ValveBiped.Bip01_L_Clavicle",
    "LeftArm":                  "ValveBiped.Bip01_L_UpperArm",
    "mixamorig:LeftArm":        "ValveBiped.Bip01_L_UpperArm",
    "LeftForeArm":              "ValveBiped.Bip01_L_Forearm",
    "mixamorig:LeftForeArm":    "ValveBiped.Bip01_L_Forearm",
    "LeftHand":                 "ValveBiped.Bip01_L_Hand",
    "mixamorig:LeftHand":       "ValveBiped.Bip01_L_Hand",

    # ---- Right Arm ----
    "RightShoulder":            "ValveBiped.Bip01_R_Clavicle",
    "mixamorig:RightShoulder":  "ValveBiped.Bip01_R_Clavicle",
    "RightArm":                 "ValveBiped.Bip01_R_UpperArm",
    "mixamorig:RightArm":       "ValveBiped.Bip01_R_UpperArm",
    "RightForeArm":             "ValveBiped.Bip01_R_Forearm",
    "mixamorig:RightForeArm":   "ValveBiped.Bip01_R_Forearm",
    "RightHand":                "ValveBiped.Bip01_R_Hand",
    "mixamorig:RightHand":      "ValveBiped.Bip01_R_Hand",

    # ---- Left Leg ----
    "LeftUpLeg":                "ValveBiped.Bip01_L_Thigh",
    "mixamorig:LeftUpLeg":      "ValveBiped.Bip01_L_Thigh",
    "LeftLeg":                  "ValveBiped.Bip01_L_Calf",
    "mixamorig:LeftLeg":        "ValveBiped.Bip01_L_Calf",
    "LeftFoot":                 "ValveBiped.Bip01_L_Foot",
    "mixamorig:LeftFoot":       "ValveBiped.Bip01_L_Foot",
    "LeftToeBase":              "ValveBiped.Bip01_L_Toe0",
    "mixamorig:LeftToeBase":    "ValveBiped.Bip01_L_Toe0",

    # ---- Right Leg ----
    "RightUpLeg":               "ValveBiped.Bip01_R_Thigh",
    "mixamorig:RightUpLeg":     "ValveBiped.Bip01_R_Thigh",
    "RightLeg":                 "ValveBiped.Bip01_R_Calf",
    "mixamorig:RightLeg":       "ValveBiped.Bip01_R_Calf",
    "RightFoot":                "ValveBiped.Bip01_R_Foot",
    "mixamorig:RightFoot":      "ValveBiped.Bip01_R_Foot",
    "RightToeBase":             "ValveBiped.Bip01_R_Toe0",
    "mixamorig:RightToeBase":   "ValveBiped.Bip01_R_Toe0",
}


def parse_args() -> argparse.Namespace:
    """Parse arguments from the section after '--' in sys.argv.

    Blender consumes everything before '--', so we must slice there.
    """
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    parser = argparse.ArgumentParser(description="Import generic FBX/GLB/GLTF models.")
    parser.add_argument("--input", required=True, help="Path to the input model file.")
    parser.add_argument("--output-blend", required=True, help="Path to save the output .blend file.")
    parser.add_argument("--report-json", required=True, help="Path to save the import report JSON.")
    parser.add_argument("--source-dir", help="Optional source asset directory (for textures).")
    return parser.parse_args(argv)


def map_bones_to_valve(armature_obj) -> int:
    """Rename bones in the armature using the heuristic map.

    Returns the number of bones successfully renamed.
    """
    if not armature_obj or armature_obj.type != "ARMATURE":
        return 0

    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode="EDIT")

    renamed_count = 0
    edit_bones = armature_obj.data.edit_bones

    # Collect renames first to avoid mid-loop name collisions.
    pending: list[tuple] = []
    for bone in edit_bones:
        target = HEURISTIC_BONE_MAP.get(bone.name)
        if target:
            pending.append((bone.name, target))

    for original, target in pending:
        if original not in edit_bones:
            continue
        if target in edit_bones:
            print(f"Warning: target name '{target}' already exists. Skipping rename of '{original}'.")
            continue
        edit_bones[original].name = target
        renamed_count += 1

    bpy.ops.object.mode_set(mode="OBJECT")
    print(f"Renamed {renamed_count} bones using heuristic mapping.")
    return renamed_count


def rescale_to_source_units(armature_obj, mesh_objects: list) -> None:
    """Scale the rig + meshes so the skeleton height is ~72 Blender units.

    Source Engine playermodels are 72 inches tall. FBX files in centimetres
    arrive at ~180 units; GLTF files in metres arrive at ~1.8 units. We
    normalise both to ~72 units so the proportion-trick step works correctly.
    """
    TARGET_HEIGHT = 72.0

    z_values: list[float] = []
    for bone in armature_obj.data.bones:
        head_world = armature_obj.matrix_world @ bone.head_local
        tail_world = armature_obj.matrix_world @ bone.tail_local
        z_values.append(head_world.z)
        z_values.append(tail_world.z)

    if not z_values:
        print("Warning: no bones found for height measurement; skipping rescale.")
        return

    height = max(z_values) - min(z_values)
    print(f"Skeleton height before rescale: {height:.4f} units")

    if abs(height) < 1e-6:
        print("Warning: skeleton height is effectively zero; skipping rescale.")
        return

    scale_factor = TARGET_HEIGHT / height
    if 0.99 < scale_factor < 1.01:
        print("Scale already close to target; skipping rescale.")
        return

    print(f"Applying uniform scale factor {scale_factor:.6f} to reach {TARGET_HEIGHT} units.")

    bpy.ops.object.select_all(action="DESELECT")
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj
    for mesh in mesh_objects:
        mesh.select_set(True)

    # Complex rigs (Rigify-style and similar) often have multiple objects
    # sharing one mesh datablock (linked duplicates -- e.g. mirrored eyelids,
    # symmetric visor halves). transform_apply() refuses to bake scale into a
    # mesh with more than one user, since that would distort every object
    # sharing it differently. Make a single-user copy of each linked mesh
    # first so the bake can proceed safely; this only affects the working
    # copy in this throwaway scene, never the original source file.
    multi_user_meshes = [mesh for mesh in mesh_objects if mesh.data and mesh.data.users > 1]
    if multi_user_meshes:
        print(f"Making {len(multi_user_meshes)} multi-user mesh(es) single-user before scaling.")
        bpy.ops.object.select_all(action="DESELECT")
        for mesh in multi_user_meshes:
            mesh.select_set(True)
        bpy.context.view_layer.objects.active = multi_user_meshes[0]
        bpy.ops.object.make_single_user(object=True, obdata=True)
        # Restore the full selection (armature + all meshes) for the resize/apply below.
        bpy.ops.object.select_all(action="DESELECT")
        armature_obj.select_set(True)
        bpy.context.view_layer.objects.active = armature_obj
        for mesh in mesh_objects:
            mesh.select_set(True)

    bpy.ops.transform.resize(value=(scale_factor, scale_factor, scale_factor))
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    print("Scale applied.")


def import_generic_model(
    input_path: str,
    output_blend_path: str,
    report_json_path: str,
    source_dir: str | None = None,
) -> None:
    """Main import routine."""
    ext = Path(input_path).suffix.lower()
    print(f"Importing {input_path} as {ext} ...")

    # For .blend files, open_mainfile() below fully replaces the scene, so the
    # empty-scene reset is unnecessary (and would be instantly discarded).
    if ext != ".blend":
        bpy.ops.wm.read_factory_settings(use_empty=True)

    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=input_path, use_manual_orientation=False)
    elif ext in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=input_path)
    elif ext == ".blend":
        # .blend files are opened directly rather than imported. We open the
        # source file itself (not append/link) so the working scene becomes
        # an editable copy; the output is later saved to a different path
        # (workspace.blend_path), so the original source .blend on disk is
        # never overwritten.
        bpy.ops.wm.open_mainfile(filepath=input_path)
    else:
        raise ValueError(f"Unsupported extension: {ext}")

    armature = None
    mesh_objects: list = []
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE" and armature is None:
            armature = obj
        elif obj.type == "MESH":
            mesh_objects.append(obj)

    if armature is None:
        raise RuntimeError(
            "No armature found in the imported file. "
            "The model must be rigged with bones to be usable in Gmod."
        )
    if not mesh_objects:
        print("Warning: No mesh found. Proceeding with armature only.")

    renamed_count = map_bones_to_valve(armature)
    rescale_to_source_units(armature, mesh_objects)

    Path(output_blend_path).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend_path))
    print(f"Saved blend to {output_blend_path}")

    warnings: list[str] = []
    if not mesh_objects:
        warnings.append("No mesh object found.")
    if renamed_count == 0:
        warnings.append(
            "No bones matched the heuristic map. "
            "The model may use non-standard bone names. "
            "Manual bone renaming may be required before the fix step."
        )

    report = {
        "format": "generic",
        "source_extension": ext.lstrip("."),
        "model_name": Path(input_path).stem,
        "imported": True,
        "bone_count": len(armature.data.bones),
        "bones_renamed": renamed_count,
        "mesh_count": len(mesh_objects),
        "heuristic_mapped": renamed_count > 0,
        "warnings": warnings,
    }

    Path(report_json_path).parent.mkdir(parents=True, exist_ok=True)
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Wrote report to {report_json_path}")


def main() -> int:
    args = parse_args()
    try:
        import_generic_model(
            input_path=args.input,
            output_blend_path=args.output_blend,
            report_json_path=args.report_json,
            source_dir=args.source_dir,
        )
    except Exception as exc:
        try:
            Path(args.report_json).parent.mkdir(parents=True, exist_ok=True)
            with open(args.report_json, "w", encoding="utf-8") as f:
                json.dump({"error": str(exc), "imported": False}, f, indent=2)
        except Exception:
            pass
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
