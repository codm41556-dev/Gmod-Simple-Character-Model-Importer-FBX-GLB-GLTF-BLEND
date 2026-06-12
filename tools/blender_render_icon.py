#!/usr/bin/env python3
"""Blender-side Step 13 PMX/VMD icon renderer."""

from __future__ import annotations

import argparse
import bmesh
import json
import math
import os
import struct
import sys
import tempfile
import time
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pmx", type=Path, required=True)
    parser.add_argument("--vmd", "--body-vmd", dest="body_vmd", type=Path, required=True)
    parser.add_argument("--face-vmd", action="append", default=[], type=Path)
    parser.add_argument("--frame", type=int, default=334)
    parser.add_argument("--output-png", type=Path, required=True)
    parser.add_argument("--spawn-output-png", type=Path)
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
        return operator(**kwargs)
    except Exception as exc:
        raise RuntimeError(f"{operator.idname()} failed with arguments {sorted(kwargs)}: {exc}") from exc


def mmd_tools_registered() -> bool:
    return get_mmd_tool_ops() is not None


def get_mmd_tool_ops():
    for namespace in ("mmd_tools", "mmd_tools_local"):
        try:
            ops = getattr(bpy.ops, namespace)
            ops.import_model.get_rna_type()
            ops.import_vmd.get_rna_type()
            return ops
        except Exception:
            continue
    return None


def dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def mmd_tools_candidates() -> list[str]:
    import addon_utils

    preferred = [
        "bl_ext.user_default.cats_blender_plugin",
        "cats_blender_plugin",
        "mmd_tools_local",
        "mmd_tools",
        "bl_ext.user_default.mmd_tools",
    ]
    discovered: list[str] = []
    try:
        for module in addon_utils.modules(refresh=True):
            name = getattr(module, "__name__", "")
            lowered = name.lower()
            if "mmd_tools" in lowered or "mmd_tools_local" in lowered or "cats_blender_plugin" in lowered:
                discovered.append(name)
    except Exception:
        pass
    return dedupe(preferred + discovered)


def enable_mmd_tools() -> None:
    import addon_utils

    errors: list[str] = []
    if mmd_tools_registered():
        print("[Step13 Render] MMD Tools operators are already available.", flush=True)
        return
    for module_name in mmd_tools_candidates():
        try:
            addon_utils.enable(module_name, default_set=False, persistent=False)
            print(f"[Step13 Render] Enabled add-on module: {module_name}", flush=True)
            if mmd_tools_registered():
                return
        except Exception as exc:
            errors.append(f"{module_name}: {exc}")
    detail = "; ".join(errors) if errors else "no MMD Tools module candidates were found"
    raise RuntimeError(f"MMD Tools PMX/VMD operators are not available: {detail}")


def clear_scene() -> None:
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def set_active(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def read_glb_json(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != b"glTF":
        return {}
    offset = 12
    while offset + 8 <= len(data):
        chunk_len, chunk_type = struct.unpack_from("<I4s", data, offset)
        offset += 8
        if chunk_type == b"JSON":
            return json.loads(data[offset : offset + chunk_len])
        offset += chunk_len
    return {}


def import_vrm_model(vrm_path: Path) -> bpy.types.Object:
    """Import a VRM via the bundled glTF importer for icon rendering."""
    print(f"[Step13 Render] Importing VRM with the glTF importer: {vrm_path}", flush=True)
    is_vrm0 = False
    try:
        doc = read_glb_json(vrm_path)
        is_vrm0 = isinstance(doc.get("extensions"), dict) and "VRM" in doc["extensions"]
    except Exception:
        pass
    before = set(bpy.data.objects)
    call_operator(bpy.ops.import_scene.gltf, filepath=str(vrm_path))
    imported = [obj for obj in bpy.data.objects if obj not in before]
    armatures = [obj for obj in imported if obj.type == "ARMATURE"] or [
        obj for obj in bpy.data.objects if obj.type == "ARMATURE"
    ]
    if not armatures:
        raise RuntimeError("VRM import produced no armature.")
    if is_vrm0:
        # VRM 0.x models face +Y after glTF import; rotate the scene roots 180
        # degrees so the character faces -Y like MMD imports (camera framing
        # and the F/E icon angles assume that convention).
        from mathutils import Matrix

        rotation = Matrix.Rotation(math.pi, 4, "Z")
        for obj in imported:
            if obj.parent is None:
                obj.matrix_world = rotation @ obj.matrix_world
        bpy.context.view_layer.update()
        print("[Step13 Render] Rotated VRM 0.x scene 180 degrees to face the camera.", flush=True)
    return armatures[0]


def import_model(pmx_path: Path) -> bpy.types.Object:
    ops = get_mmd_tool_ops()
    if ops is None:
        raise RuntimeError("MMD Tools PMX/VMD operators are not available.")
    print(f"[Step13 Render] Importing PMX with MMD Tools: {pmx_path}", flush=True)
    before = set(bpy.data.objects)
    call_operator(
        ops.import_model,
        filepath=str(pmx_path),
        types={"MESH", "ARMATURE", "DISPLAY", "MORPHS"},
    )
    imported = [obj for obj in bpy.data.objects if obj not in before]
    armatures = [obj for obj in imported if obj.type == "ARMATURE"] or [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if not armatures:
        raise RuntimeError("PMX import completed but no armature was created.")
    armature = armatures[0]
    set_active(armature)
    print(f"[Step13 Render] Imported armature: {armature.name}", flush=True)
    return armature


def find_mmd_root_or_armature(armature: bpy.types.Object) -> bpy.types.Object:
    for obj in bpy.context.scene.objects:
        if str(getattr(obj, "mmd_type", "")).upper() == "ROOT":
            return obj
    root = armature
    while root.parent is not None:
        root = root.parent
    return root


def _trim_fixed_vmd_section(data: bytes, offset: int, record_size: int, frame: int, named: bool) -> tuple[bytes, int]:
    """Trim one fixed-record VMD section to the keyframes that determine the pose at ``frame``.

    For named sections (bones, morphs) the pose at F depends only on the last
    keyframe <= F and the first keyframe > F per channel (the segment's
    interpolation bytes live in the *later* keyframe, so both survive intact).
    Returns (section bytes including the count header, new offset).
    """

    (count,) = struct.unpack_from("<I", data, offset)
    offset += 4
    frame_offset = 15 if named else 0
    last_le: dict[bytes, tuple[int, bytes]] = {}
    first_gt: dict[bytes, tuple[int, bytes]] = {}
    for _ in range(count):
        record = data[offset : offset + record_size]
        offset += record_size
        name = bytes(record[:15]) if named else b""
        (record_frame,) = struct.unpack_from("<I", record, frame_offset)
        if record_frame <= frame:
            current = last_le.get(name)
            if current is None or record_frame >= current[0]:
                last_le[name] = (record_frame, record)
        else:
            current = first_gt.get(name)
            if current is None or record_frame < current[0]:
                first_gt[name] = (record_frame, record)
    kept = [entry for entry in last_le.values()]
    for name, entry in first_gt.items():
        # The next keyframe carries the interpolation curve into frame F; it is
        # also the pose source for channels whose keys all lie beyond F.
        kept.append(entry)
    kept.sort(key=lambda item: item[0])
    section = struct.pack("<I", len(kept)) + b"".join(record for _, record in kept)
    return section, offset


def trim_vmd_to_frame(vmd_path: Path, frame: int) -> Path | None:
    """Write a temp VMD containing only the keyframes needed to pose ``frame``.

    The reference dance VMD is ~50 MB / hundreds of thousands of keyframes;
    importing it just to read one frame dominates Step 13. Returns None when
    the file cannot be parsed (caller falls back to the original).
    """

    try:
        data = vmd_path.read_bytes()
        magic = data[:30]
        if not magic.startswith(b"Vocaloid Motion Data"):
            return None
        header_len = 30 + (20 if b"0002" in magic else 10)
        out = bytearray(data[:header_len])
        offset = header_len
        original_size = len(data)
        # Bone (111 bytes) and morph (23 bytes) sections are the huge ones.
        section, offset = _trim_fixed_vmd_section(data, offset, 111, frame, named=True)
        out += section
        section, offset = _trim_fixed_vmd_section(data, offset, 23, frame, named=True)
        out += section
        # Camera (61), light (28), shadow (9): small but trim the same way.
        for record_size in (61, 28, 9):
            if offset >= len(data):
                break
            section, offset = _trim_fixed_vmd_section(data, offset, record_size, frame, named=False)
            out += section
        # IK/show section is variable-length: keep bracketing records.
        if offset + 4 <= len(data):
            (ik_count,) = struct.unpack_from("<I", data, offset)
            offset += 4
            ik_last_le: tuple[int, bytes] | None = None
            ik_first_gt: tuple[int, bytes] | None = None
            for _ in range(ik_count):
                start = offset
                (ik_frame,) = struct.unpack_from("<I", data, offset)
                (entry_count,) = struct.unpack_from("<I", data, offset + 5)
                offset = offset + 9 + entry_count * 21
                record = data[start:offset]
                if ik_frame <= frame:
                    if ik_last_le is None or ik_frame >= ik_last_le[0]:
                        ik_last_le = (ik_frame, record)
                elif ik_first_gt is None or ik_frame < ik_first_gt[0]:
                    ik_first_gt = (ik_frame, record)
            ik_kept = [entry for entry in (ik_last_le, ik_first_gt) if entry is not None]
            ik_kept.sort(key=lambda item: item[0])
            out += struct.pack("<I", len(ik_kept)) + b"".join(record for _, record in ik_kept)
        handle = tempfile.NamedTemporaryFile(prefix=f"{vmd_path.stem}_frame{frame}_", suffix=".vmd", delete=False)
        with handle:
            handle.write(bytes(out))
        print(
            f"[Step13 Render] Trimmed VMD for frame {frame}: {original_size:,} -> {len(out):,} bytes.",
            flush=True,
        )
        return Path(handle.name)
    except Exception as exc:
        print(f"[Step13 Render] VMD trim skipped ({exc}); importing the full motion.", flush=True)
        return None


def import_motion(armature: bpy.types.Object, vmd_path: Path, frame: int, label: str = "VMD motion") -> None:
    ops = get_mmd_tool_ops()
    if ops is None:
        raise RuntimeError("MMD Tools PMX/VMD operators are not available.")
    trimmed_path = trim_vmd_to_frame(vmd_path, frame)
    if trimmed_path is not None:
        vmd_path = trimmed_path
    print(f"[Step13 Render] Importing {label}: {vmd_path}", flush=True)
    # MMD Tools imports both bone and morph animation only when the model root is
    # selected. It also processes its ImportHelper `files` collection rather
    # than `filepath` alone, so pass both forms explicitly for background runs.
    root = find_mmd_root_or_armature(armature)
    set_active(root)
    try:
        call_operator(
            ops.import_vmd,
            filepath=str(vmd_path),
            directory=str(vmd_path.parent) + os.sep,
            files=[{"name": vmd_path.name}],
            bone_mapper="PMX",
            margin=0,
            update_scene_settings=True,
            create_new_action=False,
            use_nla=False,
        )
    finally:
        if trimmed_path is not None:
            try:
                trimmed_path.unlink(missing_ok=True)
            except Exception:
                pass
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    print(f"[Step13 Render] Scene set to frame {frame}.", flush=True)


def import_motions(armature: bpy.types.Object, body_vmd: Path, face_vmds: list[Path], frame: int) -> None:
    import_motion(armature, body_vmd, frame, "body VMD motion")
    for index, face_vmd in enumerate(face_vmds, start=1):
        import_motion(armature, face_vmd, frame, f"facial/flex VMD #{index}")


def visible_mesh_objects() -> list[bpy.types.Object]:
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and not obj.hide_get()]


def evaluated_bounds() -> tuple[Vector, Vector, int]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points: list[Vector] = []
    for obj in visible_mesh_objects():
        try:
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
        except Exception:
            mesh = None
        if not mesh:
            continue
        try:
            matrix = obj.matrix_world.copy()
            for vertex in mesh.vertices:
                points.append(matrix @ vertex.co)
        finally:
            try:
                evaluated.to_mesh_clear()
            except Exception:
                pass
    if not points:
        raise RuntimeError("No evaluated mesh vertices were found for camera framing.")
    min_point = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    max_point = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return min_point, max_point, len(points)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, q)) * (len(ordered) - 1)
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return ordered[low]
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def evaluated_points() -> list[Vector]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points: list[Vector] = []
    for obj in visible_mesh_objects():
        try:
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
        except Exception:
            mesh = None
        if not mesh:
            continue
        try:
            matrix = obj.matrix_world.copy()
            points.extend(matrix @ vertex.co for vertex in mesh.vertices)
        finally:
            try:
                evaluated.to_mesh_clear()
            except Exception:
                pass
    if not points:
        raise RuntimeError("No evaluated mesh vertices were found for camera framing.")
    return points


def setup_world_and_lighting() -> None:
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.color = (1.0, 1.0, 1.0)
    world.use_nodes = True
    if world.node_tree:
        background = world.node_tree.nodes.get("Background")
        if background:
            background.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
            background.inputs["Strength"].default_value = 1.0
    for obj in list(bpy.data.objects):
        if obj.type == "LIGHT":
            bpy.data.objects.remove(obj, do_unlink=True)


def image_node_identity(node: bpy.types.Node) -> str:
    image = getattr(node, "image", None)
    parts = [str(getattr(node, "name", "") or ""), str(getattr(node, "label", "") or "")]
    if image is not None:
        parts.extend(
            [
                str(getattr(image, "name", "") or ""),
                str(getattr(image, "filepath", "") or ""),
                str(getattr(image, "filepath_raw", "") or ""),
            ]
        )
    return " ".join(parts).lower()


def is_toon_or_sphere_image_node(node: bpy.types.Node) -> bool:
    identity = image_node_identity(node)
    if not identity:
        return False
    hints = (
        "toon",
        "mmd_toon",
        "mmd_toon_tex",
        "sphere",
        "mmd_sphere",
        "mmd_sphere_tex",
        "\\sph\\",
        "/sph/",
        ".sph",
        ".spa",
        "_sph",
        "_spa",
        "スフィア",
        "トゥーン",
        "toontexture",
        "spheretexture",
    )
    return any(hint in identity for hint in hints)


def material_identity(material: bpy.types.Material | None) -> str:
    if material is None:
        return ""
    parts = [str(material.name or "")]
    if material.use_nodes and material.node_tree:
        for node in material.node_tree.nodes:
            if node.bl_idname == "ShaderNodeTexImage":
                parts.append(image_node_identity(node))
    return " ".join(parts).lower()


def first_image_node(material: bpy.types.Material) -> bpy.types.ShaderNodeTexImage | None:
    if not material or not material.use_nodes or not material.node_tree:
        return None
    nodes = list(material.node_tree.nodes)
    image_nodes = [
        node
        for node in nodes
        if node.bl_idname == "ShaderNodeTexImage" and getattr(node, "image", None) and not is_toon_or_sphere_image_node(node)
    ]
    preferred_names = ("mmd_base_tex", "base", "diffuse", "albedo", "color", "tex")
    for name_hint in preferred_names:
        for node in image_nodes:
            identity = image_node_identity(node)
            if name_hint in identity:
                return node
    if image_nodes:
        return image_nodes[0]
    return None


def material_alpha(material: bpy.types.Material) -> float:
    values: list[float] = []
    try:
        values.append(float(material.diffuse_color[3]))
    except Exception:
        pass
    if material and material.use_nodes and material.node_tree:
        node = material.node_tree.nodes.get("mmd_shader")
        if node:
            try:
                values.append(float(node.inputs[12].default_value))
            except Exception:
                pass
        for node in material.node_tree.nodes:
            if node.bl_idname == "ShaderNodeBsdfPrincipled":
                alpha_input = node.inputs.get("Alpha")
                if alpha_input is not None:
                    try:
                        values.append(float(alpha_input.default_value))
                    except Exception:
                        pass
    if not values:
        return 1.0
    return min(max(value, 0.0) for value in values)


def should_hide_material(material: bpy.types.Material) -> tuple[bool, str, bool, float]:
    image_node = first_image_node(material)
    has_base_image = bool(image_node and getattr(image_node, "image", None))
    alpha = material_alpha(material)
    identity = material_identity(material)
    name = str(material.name if material else "").lower()
    eye_shadow_like = any(
        hint in identity
        for hint in (
            "eyeshadow",
            "eye_shadow",
            "eye shadow",
            "eye-shad",
            "目影",
            "瞳影",
            "眼影",
            "目陰",
            "目阴",
        )
    )
    shadow_like = eye_shadow_like or any(hint in name for hint in ("shadow", "影", "陰", "阴"))
    only_toon_or_sphere = (
        bool(material and material.use_nodes and material.node_tree)
        and not has_base_image
        and any(
            node.bl_idname == "ShaderNodeTexImage" and getattr(node, "image", None) and is_toon_or_sphere_image_node(node)
            for node in material.node_tree.nodes
        )
    )
    if alpha <= 0.001:
        return True, "alpha <= 0.001", has_base_image, alpha
    if eye_shadow_like:
        return True, "eye-shadow material", has_base_image, alpha
    if only_toon_or_sphere:
        return True, "toon/sphere-only material", has_base_image, alpha
    if not has_base_image and shadow_like:
        return True, "shadow/no-base material", has_base_image, alpha
    return False, "", has_base_image, alpha


def remove_hidden_material_faces() -> list[dict[str, object]]:
    hidden: list[dict[str, object]] = []
    material_reasons: dict[str, tuple[str, bool, float]] = {}
    for material in bpy.data.materials:
        hide, reason, has_base_image, alpha = should_hide_material(material)
        if hide:
            material_reasons[material.name] = (reason, has_base_image, alpha)

    if not material_reasons:
        print("[Step13 Render] No render-only material polygons needed hiding.", flush=True)
        return hidden

    for obj in visible_mesh_objects():
        mesh = obj.data
        hidden_indices: set[int] = set()
        for index, slot in enumerate(obj.material_slots):
            material = slot.material
            if material and material.name in material_reasons:
                hidden_indices.add(index)
        if not hidden_indices:
            continue
        if mesh.users > 1:
            obj.data = mesh.copy()
            mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        face_counts = {index: 0 for index in hidden_indices}
        for face in bm.faces:
            if int(face.material_index) in face_counts:
                face_counts[int(face.material_index)] += 1
        faces = [face for face in bm.faces if int(face.material_index) in hidden_indices]
        if faces:
            bmesh.ops.delete(bm, geom=faces, context="FACES")
            bmesh.ops.delete(bm, geom=[vert for vert in bm.verts if not vert.link_faces], context="VERTS")
            bm.to_mesh(mesh)
            mesh.update()
        bm.free()
        for index in sorted(hidden_indices):
            material = obj.material_slots[index].material
            if not material:
                continue
            reason, has_base_image, alpha = material_reasons[material.name]
            hidden.append(
                {
                    "object": obj.name,
                    "material": material.name,
                    "slot_index": index,
                    "reason": reason,
                    "has_base_image": has_base_image,
                    "alpha": round(alpha, 6),
                    "removed_faces": int(face_counts.get(index, 0)),
                }
            )
    print(f"[Step13 Render] Hid {len(hidden)} material slot usages for icon render.", flush=True)
    return hidden


def make_unshaded_materials() -> int:
    converted = 0
    for material in bpy.data.materials:
        source_image = None
        source_color = tuple(material.diffuse_color) if material.diffuse_color else (1.0, 1.0, 1.0, 1.0)
        image_node = first_image_node(material)
        if image_node is not None:
            source_image = image_node.image
        material.use_nodes = True
        material.node_tree.nodes.clear()
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (360, 0)
        emission = nodes.new("ShaderNodeEmission")
        emission.location = (120, 0)
        emission.inputs["Strength"].default_value = 1.0
        surface_node = emission
        surface_socket = "Emission"
        if source_image is not None:
            tex = nodes.new("ShaderNodeTexImage")
            tex.location = (-160, 0)
            tex.image = source_image
            links.new(tex.outputs["Color"], emission.inputs["Color"])
            if "Alpha" in tex.outputs:
                # Route texture alpha through a Transparent BSDF mix so
                # alpha-mapped MMD textures (hair fringes, accessory planes)
                # do not render as opaque rectangles in the icon.
                try:
                    transparent = nodes.new("ShaderNodeBsdfTransparent")
                    transparent.location = (120, -160)
                    mix = nodes.new("ShaderNodeMixShader")
                    mix.location = (240, 0)
                    links.new(tex.outputs["Alpha"], mix.inputs["Fac"])
                    links.new(transparent.outputs["BSDF"], mix.inputs[1])
                    links.new(emission.outputs["Emission"], mix.inputs[2])
                    surface_node = mix
                    surface_socket = "Shader"
                    try:
                        material.blend_method = "HASHED"  # EEVEE legacy (<= 4.1)
                    except Exception:
                        pass
                    try:
                        material.surface_render_method = "DITHERED"  # EEVEE Next (4.2+)
                    except Exception:
                        pass
                    try:
                        material.use_screen_refraction = False
                    except Exception:
                        pass
                except Exception:
                    surface_node = emission
                    surface_socket = "Emission"
        else:
            emission.inputs["Color"].default_value = source_color
        links.new(surface_node.outputs[surface_socket], output.inputs["Surface"])
        converted += 1
    print(f"[Step13 Render] Converted {converted} materials to unshaded emission.", flush=True)
    return converted


def make_emission_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.node_tree.nodes.clear()
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = 1.0
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def add_white_backdrop(center: Vector, view_dir: Vector, camera_distance: float, ortho_scale: float) -> None:
    if view_dir.length <= 1e-8:
        view_dir = Vector((0.0, 1.0, 0.0))
    view_dir = view_dir.normalized()
    location = center + view_dir * max(0.5, camera_distance * 0.35)
    bpy.ops.mesh.primitive_plane_add(
        size=ortho_scale * 3.2,
        location=location,
    )
    backdrop = bpy.context.object
    backdrop.name = "MCI_Release_Icon_White_Backdrop"
    try:
        backdrop.rotation_euler = view_dir.to_track_quat("Z", "Y").to_euler()
    except Exception:
        pass
    backdrop.data.materials.append(make_emission_material("MCI_Release_Icon_White", (1.0, 1.0, 1.0, 1.0)))
    backdrop.hide_select = True


def find_eye_focus_direction() -> tuple[Vector | None, Vector | None, dict[str, object]]:
    eye_hints = ("eye_l", "eye_r", "left_eye", "right_eye", "lefteye", "righteye", "左目", "右目", "目.L", "目.R")
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    vectors: list[Vector] = []
    centers: list[Vector] = []
    names: list[str] = []
    for armature in armatures:
        for pose_bone in armature.pose.bones:
            name_key = pose_bone.name.lower()
            if any(skip in name_key for skip in ("dummy", "shadow", "_shadow_", "_dummy_")):
                continue
            if not any(hint.lower() in name_key for hint in eye_hints):
                continue
            matrix = armature.matrix_world @ pose_bone.matrix
            center = matrix.translation
            # PMX eye bones usually face toward model front along local -Y. If
            # a model uses another local basis this only affects the optional
            # eye-follow camera; normal front framing remains the fallback.
            direction = (matrix.to_quaternion() @ Vector((0.0, -1.0, 0.0))).normalized()
            if direction.length > 1e-6:
                vectors.append(direction)
                centers.append(center)
                names.append(pose_bone.name)
    if not vectors:
        return None, None, {"mode": "front_fallback", "reason": "no eye bones found", "eye_bones": []}
    forward = Vector((0.0, 0.0, 0.0))
    center = Vector((0.0, 0.0, 0.0))
    for vector in vectors:
        forward += vector
    for value in centers:
        center += value
    forward /= max(1, len(vectors))
    center /= max(1, len(centers))
    if forward.length <= 1e-5 or abs(forward.normalized().z) > 0.92:
        return center, None, {"mode": "front_fallback", "reason": "eye direction was vertical/ambiguous", "eye_bones": names}
    return center, forward.normalized(), {"mode": "eye_follow", "eye_bones": names}


def front_camera_direction(eye_forward: Vector | None, eye_info: dict[str, object]) -> tuple[Vector, dict[str, object]]:
    """Return a target-to-camera direction that stays on the model front side.

    MMD/Blender imports consistently present the character front from negative Y
    for these renders. Eye bones are still useful for slight gaze-follow yaw, but
    some models have flipped/dummy eye bases. Clamp or flip the inferred vector
    so the camera can never end up behind the character.
    """

    canonical = Vector((0.0, -1.0, 0.0))
    info = dict(eye_info or {})
    info["canonical_front"] = [0.0, -1.0, 0.0]
    if eye_forward is None or eye_forward.length <= 1e-6:
        info["camera_direction_mode"] = "canonical_front"
        return canonical, info

    candidate = Vector((float(eye_forward.x), float(eye_forward.y), 0.0))
    if candidate.length <= 1e-6:
        info["camera_direction_mode"] = "canonical_front_eye_vertical"
        return canonical, info
    candidate.normalize()
    raw_dot = float(candidate.dot(canonical))
    info["raw_eye_front_dot"] = round(raw_dot, 6)
    if raw_dot < -0.05:
        candidate = -candidate
        info["camera_direction_correction"] = "flipped_eye_direction_to_front"
    elif raw_dot < 0.25:
        info["camera_direction_mode"] = "canonical_front_eye_sideways"
        return canonical, info

    # Keep most of the canonical front vector so gaze following cannot rotate the
    # icon into a side/back shot.
    direction = (canonical * 0.72 + candidate * 0.28)
    if direction.length <= 1e-6 or direction.normalized().dot(canonical) < 0.70:
        info["camera_direction_mode"] = "canonical_front_guard"
        return canonical, info
    direction.normalize()
    info["camera_direction_mode"] = "front_constrained_eye_follow"
    info["camera_direction"] = [round(float(direction.x), 6), round(float(direction.y), 6), round(float(direction.z), 6)]
    return direction, info


def setup_camera(crop_mode: str, camera_name: str) -> dict[str, object]:
    points = evaluated_points()
    vertex_count = len(points)
    min_point = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    max_point = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    size = max_point - min_point
    height = max(0.001, size.z)
    lower_fraction = 0.42 if crop_mode == "release_abdomen" else 0.62
    lower_min_z = min_point.z + height * lower_fraction
    upper_points = [p for p in points if p.z >= lower_min_z] or points
    x_lo = percentile([p.x for p in upper_points], 0.03)
    x_hi = percentile([p.x for p in upper_points], 0.97)
    y_lo = percentile([p.y for p in upper_points], 0.05)
    y_hi = percentile([p.y for p in upper_points], 0.95)
    z_lo = min(p.z for p in upper_points)
    z_hi = max(p.z for p in upper_points)
    upper_center_z = (z_lo + z_hi) * 0.5
    center_x = (x_lo + x_hi) * 0.5
    center_y = (y_lo + y_hi) * 0.5
    upper_height = max(0.001, z_hi - z_lo)
    upper_width = max(0.001, x_hi - x_lo)
    if crop_mode == "release_abdomen":
        ortho_scale = max(upper_height * 1.20, upper_width * 1.16, height * 0.48)
    else:
        ortho_scale = max(upper_height * 1.05, upper_width * 1.08, height * 0.30)
    camera_distance = max(8.0, size.y * 3.0, height * 1.8)
    target = Vector((center_x, center_y, upper_center_z))
    eye_center, eye_forward, eye_info = find_eye_focus_direction()
    if eye_center is not None and crop_mode != "release_abdomen":
        target.x = eye_center.x
        target.y = eye_center.y
        target.z = (target.z * 0.72) + (eye_center.z * 0.28)
    target_to_camera, camera_direction_info = front_camera_direction(eye_forward, eye_info)
    camera_location = target + target_to_camera * camera_distance
    view_dir = (target - camera_location).normalized()

    bpy.ops.object.camera_add(location=camera_location)
    camera = bpy.context.object
    camera.name = camera_name
    camera.rotation_euler = view_dir.to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale
    camera.data.clip_end = max(1000.0, camera_distance * 4.0)
    bpy.context.scene.camera = camera
    add_white_backdrop(target, view_dir, camera_distance, ortho_scale)
    return {
        "bounds_min": [round(min_point.x, 6), round(min_point.y, 6), round(min_point.z, 6)],
        "bounds_max": [round(max_point.x, 6), round(max_point.y, 6), round(max_point.z, 6)],
        "vertex_count": vertex_count,
        "crop": crop_mode,
        "crop_bounds_min": [round(x_lo, 6), round(y_lo, 6), round(z_lo, 6)],
        "crop_bounds_max": [round(x_hi, 6), round(y_hi, 6), round(z_hi, 6)],
        "upper_min_z": round(z_lo, 6),
        "camera_location": [round(value, 6) for value in camera.location],
        "target": [round(value, 6) for value in target],
        "ortho_scale": round(ortho_scale, 6),
        "eye_camera": camera_direction_info,
    }


def setup_render(output_path: Path) -> None:
    scene = bpy.context.scene
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.render.film_transparent = False
    scene.render.filepath = str(output_path)
    scene.render.image_settings.file_format = "PNG"
    try:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except Exception:
        pass
    try:
        scene.display.shading.light = "FLAT"
        scene.display.shading.color_type = "TEXTURE"
        scene.display.shading.background_type = "VIEWPORT"
        scene.display.shading.background_color = (1.0, 1.0, 1.0)
    except Exception:
        pass


def render_icon(output_path: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Delete any stale output from a previous run so a failed render can never
    # be reported as success through an old file passing the exists() checks.
    try:
        output_path.unlink(missing_ok=True)
    except Exception as exc:
        warnings.append(f"Could not remove stale output {output_path.name}: {exc}")
    setup_render(output_path)
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            bpy.context.scene.render.engine = engine
            print(f"[Step13 Render] Rendering unshaded still with {engine}.", flush=True)
            result = bpy.ops.render.render(write_still=True)
            if "FINISHED" not in result:
                warnings.append(f"{engine} render returned {sorted(result)}")
                print(f"[Step13 Render] {engine} render returned {sorted(result)}.", flush=True)
                continue
            if output_path.exists():
                return f"{engine.lower()}_unshaded", warnings
            warnings.append(f"{engine} render finished but wrote no output file")
        except Exception as exc:
            warnings.append(f"{engine} render failed: {exc}")
            print(f"[Step13 Render] {engine} render failed: {exc}", flush=True)
    try:
        bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
        print("[Step13 Render] Trying OpenGL still render with flat texture shading.", flush=True)
        result = bpy.ops.render.opengl(write_still=True, view_context=False)
        if "FINISHED" in result and output_path.exists():
            return "opengl_flat_texture", warnings
        if "FINISHED" not in result:
            warnings.append(f"OpenGL render returned {sorted(result)}")
    except Exception as exc:
        warnings.append(f"OpenGL render failed: {exc}")
        print(f"[Step13 Render] OpenGL render failed: {exc}", flush=True)
    for engine in ("BLENDER_WORKBENCH",):
        try:
            bpy.context.scene.render.engine = engine
            print(f"[Step13 Render] Rendering with {engine}.", flush=True)
            result = bpy.ops.render.render(write_still=True)
            if "FINISHED" in result and output_path.exists():
                return engine.lower(), warnings
            if "FINISHED" not in result:
                warnings.append(f"{engine} render returned {sorted(result)}")
        except Exception as exc:
            warnings.append(f"{engine} render failed: {exc}")
    raise RuntimeError("All Blender render methods failed.")


def write_report(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    if not args.pmx.exists():
        raise FileNotFoundError(args.pmx)
    is_vrm = args.pmx.suffix.lower() == ".vrm"
    if not is_vrm and not args.body_vmd.exists():
        raise FileNotFoundError(args.body_vmd)

    started = time.monotonic()
    print("[Step13 Render] Starting Step 13 icon render.", flush=True)
    if not is_vrm:
        enable_mmd_tools()
    clear_scene()
    setup_world_and_lighting()
    if is_vrm:
        armature = import_vrm_model(args.pmx)
        print(
            "[Step13 Render] VMD posing is not supported for VRM models; rendering the default pose.",
            flush=True,
        )
    else:
        armature = import_model(args.pmx)
        missing_face_vmds = [path for path in args.face_vmd if not path.exists()]
        if missing_face_vmds:
            raise FileNotFoundError(missing_face_vmds[0])
        import_motions(armature, args.body_vmd, args.face_vmd, args.frame)
    hidden_materials = remove_hidden_material_faces()
    converted_materials = make_unshaded_materials()
    camera_info = setup_camera("release_abdomen", "MCI_Release_Icon_Camera")
    method, warnings = render_icon(args.output_png)
    spawn_camera_info: dict[str, object] | None = None
    spawn_output = args.spawn_output_png
    if spawn_output:
        print("[Step13 Render] Rendering head-centered spawn icon source.", flush=True)
        # Replace the release camera/backdrop pair with a tighter head-centered
        # camera. The scene and imported pose stay unchanged.
        for obj in list(bpy.data.objects):
            if obj.name.startswith("MCI_Release_Icon_Camera") or obj.name.startswith("MCI_Spawn_Icon_Camera") or obj.name.startswith("MCI_Release_Icon_White_Backdrop"):
                bpy.data.objects.remove(obj, do_unlink=True)
        spawn_camera_info = setup_camera("spawn_head_center", "MCI_Spawn_Icon_Camera")
        spawn_method, spawn_warnings = render_icon(spawn_output)
        warnings.extend(f"spawn: {warning}" for warning in spawn_warnings)
        method = f"{method}; spawn={spawn_method}"
    report = {
        "step": 13,
        "pmx_path": str(args.pmx),
        "model_format": "vrm" if is_vrm else "pmx",
        "body_vmd_path": str(args.body_vmd),
        "vmd_path": str(args.body_vmd),
        "face_vmd_paths": [str(path) for path in args.face_vmd],
        "frame": args.frame,
        "output_png": str(args.output_png),
        "spawn_output_png": str(spawn_output) if spawn_output else "",
        "render_method": method,
        "unshaded_material_count": converted_materials,
        "hidden_materials": hidden_materials,
        "camera": camera_info,
        "spawn_camera": spawn_camera_info,
        "warnings": warnings,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    write_report(args.report_json, report)
    print(f"[Step13 Render] Wrote release icon: {args.output_png}", flush=True)
    print(f"[Step13 Render] Wrote render report: {args.report_json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
