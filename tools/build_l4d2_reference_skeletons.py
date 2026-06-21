#!/usr/bin/env python3
"""Offline generator: extract L4D2 survivor base skeletons for the Step 9 proportion trick.

In the GMod pipeline the Step 9 proportion-trick blend ships a built-in GMod ValveBiped
armature (the `proportions`/`reference_female`/`reference_male` armatures inside
`proportion_trick_4.5.10.blend`). The MMD model is *processed against that armature*: the
mesh is retargeted onto it and bound to it, so the compiled model lives in GMod's bone
convention -- which matches the GMod player animations.

For L4D2 the included animations (`anim_<slot>.mdl`) are authored in the SURVIVOR skeleton's
own bone convention, so the model must be built on the survivor's skeleton instead. Step 9
therefore swaps the built-in GMod armature for the selected survivor's skeleton (see
`blender_export_proportion_trick.py`), and this tool produces that skeleton.

It extracts the survivor's ESSENTIAL ValveBiped bones (the same 53-bone core the GMod
template `proportions` armature uses -- biped + spine + arms + all fingers + legs/toes),
in the survivor's native `.mdl` bone convention (local pos + RadianEuler verbatim, which is
exactly what an SMD frame stores). The survivor's decoration / helper bones (jigglebones,
weapon bones, attachment bones, procedural Knee/Ulna/Wrist/Elbow, etc.) are excluded, so the
proportion subtract only ever operates on the essential bones the MMD model actually shares.

Input: an L4D2 survivor `.mdl` (e.g. `L4D2_Support/orig_models/survivor_<slot>.mdl`).
Output: `tools/l4d2_reference_skeletons/<slot>.smd` (essential bones, survivor convention).

Pure Python (no Blender). Run:
  python build_l4d2_reference_skeletons.py --survivor-mdl <survivor_<slot>.mdl> --out-smd <out.smd>
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


# The 53 essential ValveBiped bones the GMod proportion-trick `proportions` armature carries
# (biped core + 4-segment spine + arms + 5 fingers x 3 segments + legs + toes). The proportion
# trick retargets / subtracts only these; survivor decoration bones are intentionally dropped.
_FINGER_SEGMENTS = []
for _side in ("L", "R"):
    for _f in range(5):
        _FINGER_SEGMENTS.append(f"ValveBiped.Bip01_{_side}_Finger{_f}")
        _FINGER_SEGMENTS.append(f"ValveBiped.Bip01_{_side}_Finger{_f}1")
        _FINGER_SEGMENTS.append(f"ValveBiped.Bip01_{_side}_Finger{_f}2")
_CORE_BONES = [
    "ValveBiped.Bip01_Pelvis",
    "ValveBiped.Bip01_Spine",
    "ValveBiped.Bip01_Spine1",
    "ValveBiped.Bip01_Spine2",
    "ValveBiped.Bip01_Spine4",
    "ValveBiped.Bip01_Neck1",
    "ValveBiped.Bip01_Head1",
    "ValveBiped.Bip01_L_Clavicle",
    "ValveBiped.Bip01_L_UpperArm",
    "ValveBiped.Bip01_L_Forearm",
    "ValveBiped.Bip01_L_Hand",
    "ValveBiped.Bip01_R_Clavicle",
    "ValveBiped.Bip01_R_UpperArm",
    "ValveBiped.Bip01_R_Forearm",
    "ValveBiped.Bip01_R_Hand",
    "ValveBiped.Bip01_L_Thigh",
    "ValveBiped.Bip01_L_Calf",
    "ValveBiped.Bip01_L_Foot",
    "ValveBiped.Bip01_L_Toe0",
    "ValveBiped.Bip01_R_Thigh",
    "ValveBiped.Bip01_R_Calf",
    "ValveBiped.Bip01_R_Foot",
    "ValveBiped.Bip01_R_Toe0",
]

# Functional (non-deforming) survivor bones the L4D2 QC's $attachment / $ikchain set needs:
# - weapon_bone / L_weapon_bone: the held weapon world-model bone-merges onto these, so without
#   them the game has nowhere to place the weapon and drops it at the model origin.
# - weapon_bone_Clip: target of the "ikclip" IK chain (correct weapon/hand placement).
# - weapon_bone_extra: extra weapon merge point used by some weapon models.
# - forward: the "forward" aim attachment.
# - attachment_bandage_* / attachment_arm*_T: incap/bandage and arm attachment points.
# They hang off essential bones (hands/forearms/calf/head), so the proportion trick carries
# them along with their retargeted parent at the survivor's local offset.
_FUNCTIONAL_BONES = [
    "ValveBiped.forward",
    "ValveBiped.weapon_bone",
    "ValveBiped.weapon_bone_Clip",
    "ValveBiped.weapon_bone_extra",
    "ValveBiped.L_weapon_bone",
    "ValveBiped.attachment_bandage_legL",
    "ValveBiped.attachment_bandage_armL",
    "ValveBiped.attachment_armL_T",
    "ValveBiped.attachment_armR_T",
]
ESSENTIAL_BONES = frozenset(_CORE_BONES + _FINGER_SEGMENTS + _FUNCTIONAL_BONES)


def parse_mdl_skeleton(mdl_path: Path) -> list[dict]:
    """Parse the studiohdr_t v44-49 bone table (numbones@156, boneindex@160; mstudiobone_t
    216 bytes: sznameindex@0, parent@4, pos(3f)@32, rot RadianEuler(3f)@60)."""
    data = mdl_path.read_bytes()
    numbones = struct.unpack_from("<i", data, 156)[0]
    boneindex = struct.unpack_from("<i", data, 160)[0]
    bones: list[dict] = []
    for i in range(numbones):
        base = boneindex + i * 216
        szname = struct.unpack_from("<i", data, base + 0)[0]
        parent = struct.unpack_from("<i", data, base + 4)[0]
        pos = struct.unpack_from("<3f", data, base + 32)
        rot = struct.unpack_from("<3f", data, base + 60)
        nstart = base + szname
        nend = data.index(b"\x00", nstart)
        name = data[nstart:nend].decode("ascii", "replace")
        bones.append({"name": name, "parent": parent, "pos": pos, "rot": rot})
    return bones


def extract_essential(bones: list[dict]) -> list[dict]:
    """Keep only the essential ValveBiped bones, remapping parents to the filtered list.

    Every essential bone's parent chain is itself essential (the ValveBiped biped is
    self-contained), so filtering preserves valid parenting.
    """
    keep_idx = [i for i, b in enumerate(bones) if b["name"] in ESSENTIAL_BONES]
    old_to_new = {old: new for new, old in enumerate(keep_idx)}
    out: list[dict] = []
    for old in keep_idx:
        b = bones[old]
        parent = b["parent"]
        # Walk up to the nearest kept ancestor (essential parents are kept, but be safe).
        while parent >= 0 and parent not in old_to_new:
            parent = bones[parent]["parent"]
        out.append(
            {
                "name": b["name"],
                "parent": old_to_new.get(parent, -1),
                "pos": b["pos"],
                "rot": b["rot"],
            }
        )
    return out


def write_skeleton_smd(bones: list[dict], out_path: Path) -> None:
    lines = ["version 1", "nodes"]
    for i, b in enumerate(bones):
        lines.append(f'{i} "{b["name"]}" {b["parent"]}')
    lines.append("end")
    lines.append("skeleton")
    lines.append("time 0")
    for i, b in enumerate(bones):
        px, py, pz = b["pos"]
        rx, ry, rz = b["rot"]
        lines.append(f"{i} {px:.6f} {py:.6f} {pz:.6f} {rx:.6f} {ry:.6f} {rz:.6f}")
    lines.append("end")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(survivor_mdl: Path, out_smd: Path) -> None:
    if not survivor_mdl.exists():
        raise FileNotFoundError(survivor_mdl)
    bones = parse_mdl_skeleton(survivor_mdl)
    essential = extract_essential(bones)
    missing = sorted(ESSENTIAL_BONES - {b["name"] for b in essential})
    if missing:
        print(f"[BuildL4D2Ref] WARNING: {survivor_mdl.name} is missing essential bones: {missing}", file=sys.stderr)
    out_smd.parent.mkdir(parents=True, exist_ok=True)
    write_skeleton_smd(essential, out_smd)
    print(f"[BuildL4D2Ref] {survivor_mdl.name}: {len(bones)} bones -> {len(essential)} essential -> {out_smd}")


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--survivor-mdl", required=True)
    parser.add_argument("--out-smd", required=True)
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    run(Path(args.survivor_mdl).resolve(), Path(args.out_smd).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
