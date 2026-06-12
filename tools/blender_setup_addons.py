#!/usr/bin/env python3
"""Install and verify Blender add-ons required by the importer."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import sysconfig
import zipfile
from pathlib import Path

import bpy


def hidden_subprocess_kwargs() -> dict[str, object]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    return {
        "startupinfo": startupinfo,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cats-zip", type=Path, required=True)
    parser.add_argument("--source-tools-zip", type=Path, required=True)
    parser.add_argument("--bones-merger-zip", type=Path, required=True)
    parser.add_argument("--material-combiner-zip", type=Path, required=True)
    parser.add_argument("--coacd-addon-zip", type=Path, required=True)
    parser.add_argument("--l4d2-tools-zip", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
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


def cats_registered() -> bool:
    try:
        bpy.ops.cats_importer.import_any_model.get_rna_type()
        return True
    except Exception:
        return False


def mmd_tools_registered() -> bool:
    for namespace in ("mmd_tools", "mmd_tools_local"):
        try:
            getattr(bpy.ops, namespace).import_model.get_rna_type()
            getattr(bpy.ops, namespace).import_vmd.get_rna_type()
            return True
        except Exception:
            continue
    return False


def source_tools_registered() -> bool:
    try:
        bpy.ops.import_scene.smd.get_rna_type()
        return True
    except Exception:
        return False


def bones_merger_registered() -> bool:
    try:
        bpy.ops.armature.voyage_vrsns_merge_bones.get_rna_type()
        return True
    except Exception:
        return False


def material_combiner_registered() -> bool:
    try:
        bpy.ops.smc.refresh_ob_data.get_rna_type()
        bpy.ops.smc.combiner.get_rna_type()
        return True
    except Exception:
        return False


def coacd_registered() -> bool:
    try:
        bpy.ops.mesh.coacd_generate_collision.get_rna_type()
        return True
    except Exception:
        return False


def l4d2_tools_registered() -> bool:
    try:
        bpy.ops.vrd.auto_pose.get_rna_type()
        bpy.ops.vrd.export_bones.get_rna_type()
        return hasattr(bpy.types.Scene, "project_items")
    except Exception:
        return False


def pillow_registered() -> bool:
    try:
        import PIL  # noqa: F401

        return True
    except Exception:
        return False


def sklearn_registered() -> bool:
    try:
        import scipy  # noqa: F401
        import sklearn  # noqa: F401
        from sklearn.cluster import DBSCAN, OPTICS  # noqa: F401

        local_site = Path(sysconfig.get_paths().get("purelib", ""))
        modules = [scipy, sklearn]
        if local_site:
            for module in modules:
                module_file = Path(getattr(module, "__file__", "")).resolve()
                try:
                    if not module_file.is_relative_to(local_site.resolve()):
                        return False
                except Exception:
                    return False
        return True
    except Exception:
        return False


def module_names(predicate) -> list[str]:
    import addon_utils

    out: list[str] = []
    try:
        modules = addon_utils.modules(refresh=True)
    except Exception:
        modules = []
    for module in modules:
        name = getattr(module, "__name__", "")
        if name and predicate(name) and name not in out:
            out.append(name)
    return out


def enable_modules(candidates: list[str], label: str) -> list[str]:
    import addon_utils

    errors: list[str] = []
    for name in candidates:
        try:
            addon_utils.enable(name, default_set=True, persistent=True)
            print(f"Enabled {label} add-on module: {name}")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    return errors


def cats_candidates() -> list[str]:
    preferred = [
        "bl_ext.user_default.cats_blender_plugin",
        "bl_ext.blender_org.cats_blender_plugin",
        "cats_blender_plugin",
    ]
    discovered = module_names(lambda name: name.endswith("cats_blender_plugin") or "cats_blender_plugin" in name)
    return dedupe(preferred + discovered)


def mmd_tools_candidates() -> list[str]:
    preferred = [
        "bl_ext.user_default.cats_blender_plugin",
        "cats_blender_plugin",
        "mmd_tools_local",
        "mmd_tools",
        "bl_ext.user_default.mmd_tools",
    ]
    discovered = module_names(
        lambda name: "mmd_tools" in name.lower() or "mmd_tools_local" in name.lower() or "cats_blender_plugin" in name.lower()
    )
    return dedupe(preferred + discovered)


def source_tools_candidates() -> list[str]:
    preferred = ["io_scene_valvesource"]
    discovered = module_names(lambda name: name == "io_scene_valvesource" or name.endswith(".io_scene_valvesource"))
    return dedupe(preferred + discovered)


def bones_merger_candidates() -> list[str]:
    preferred = ["bones_merger"]
    discovered = module_names(lambda name: name == "bones_merger" or name.endswith(".bones_merger"))
    return dedupe(preferred + discovered)


def material_combiner_candidates() -> list[str]:
    preferred = ["material_combiner_addon", "material-combiner-addon-master"]
    discovered = module_names(lambda name: name in preferred or "material_combiner" in name or "material-combiner" in name)
    return dedupe(preferred + discovered)


def coacd_candidates() -> list[str]:
    preferred = ["coacd_blender_addon"]
    discovered = module_names(lambda name: name == "coacd_blender_addon" or name.endswith(".coacd_blender_addon") or "coacd" in name.lower())
    return dedupe(preferred + discovered)


def l4d2_tools_candidates() -> list[str]:
    preferred = ["Blender_L4D2_Character_Tools"]
    discovered = module_names(lambda name: name == "Blender_L4D2_Character_Tools" or "l4d2_character_tools" in name.lower())
    return dedupe(preferred + discovered)


def dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def safe_extract_destination(target: Path, member: str, rel: str) -> Path:
    """Resolve an archive member's output path, rejecting zip-slip escapes."""
    rel_path = Path(rel.replace("\\", "/"))
    if rel_path.is_absolute() or rel_path.drive:
        raise RuntimeError(f"unsafe absolute archive member path: {member}")
    destination = (target / rel_path).resolve()
    if not destination.is_relative_to(target.resolve()):
        raise RuntimeError(f"archive member escapes the install directory: {member}")
    return destination


def install_cats(zip_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        print(f"Installing CATS extension from {zip_path}")
        call_operator(
            bpy.ops.extensions.package_install_files,
            filepath=str(zip_path),
            repo="user_default",
            enable_on_install=True,
            overwrite=True,
        )
    except Exception as exc:
        errors.append(f"extension install failed: {exc}")
        try:
            print("Falling back to legacy add-on install for CATS")
            call_operator(
                bpy.ops.preferences.addon_install,
                filepath=str(zip_path),
                overwrite=True,
                enable_on_install=True,
            )
        except Exception as legacy_exc:
            errors.append(f"legacy install failed: {legacy_exc}")
    return errors


def install_mmd_tools_from_cats(zip_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        print(f"Extracting MMD Tools local package from CATS archive: {zip_path}")
        addon_root = Path(bpy.utils.user_resource("SCRIPTS", path="addons", create=True))
        target = addon_root / "mmd_tools_local"
        if target.exists():
            shutil.rmtree(target)
        with zipfile.ZipFile(zip_path) as archive:
            prefix = ""
            for member in archive.namelist():
                if member.endswith("extern_tools/mmd_tools_local/__init__.py"):
                    prefix = member[: -len("__init__.py")]
                    break
            if not prefix:
                raise RuntimeError("mmd_tools_local package was not found inside the CATS archive")
            for member in archive.namelist():
                if member.endswith("/") or not member.startswith(prefix):
                    continue
                rel = member[len(prefix) :]
                if not rel:
                    continue
                destination = safe_extract_destination(target, member, rel)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
        print(f"Extracted MMD Tools local add-on to {target}")
    except Exception as exc:
        errors.append(f"MMD Tools local extraction failed: {exc}")
    return errors


def install_source_tools(zip_path: Path) -> list[str]:
    try:
        print(f"Installing Blender Source Tools from {zip_path}")
        call_operator(
            bpy.ops.preferences.addon_install,
            filepath=str(zip_path),
            overwrite=True,
            enable_on_install=True,
        )
        return []
    except Exception as exc:
        return [f"source tools install failed: {exc}"]


def install_bones_merger(zip_path: Path) -> list[str]:
    try:
        print(f"Installing Blender Bones Merger from {zip_path}")
        call_operator(
            bpy.ops.preferences.addon_install,
            filepath=str(zip_path),
            overwrite=True,
            enable_on_install=True,
        )
        return []
    except Exception as exc:
        return [f"bones merger install failed: {exc}"]


def install_material_combiner(zip_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        print(f"Installing Material Combiner from {zip_path}")
        addon_root = Path(bpy.utils.user_resource("SCRIPTS", path="addons", create=True))
        target = addon_root / "material_combiner_addon"
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            members = archive.namelist()
            roots = {name.split("/", 1)[0] for name in members if "/" in name}
            root = sorted(roots)[0] if roots else ""
            for member in members:
                if member.endswith("/"):
                    continue
                rel = member[len(root) + 1 :] if root and member.startswith(root + "/") else member
                if not rel:
                    continue
                destination = safe_extract_destination(target, member, rel)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
        print(f"Extracted Material Combiner add-on to {target}")
        return []
    except Exception as exc:
        errors.append(f"material combiner manual install failed: {exc}")
    try:
        call_operator(
            bpy.ops.preferences.addon_install,
            filepath=str(zip_path),
            overwrite=True,
            enable_on_install=True,
        )
    except Exception as exc:
        errors.append(f"material combiner legacy install failed: {exc}")
    return errors


def install_coacd(zip_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        print(f"Installing CoACD collision add-on from {zip_path}")
        call_operator(
            bpy.ops.preferences.addon_install,
            filepath=str(zip_path),
            overwrite=True,
            enable_on_install=True,
        )
        return []
    except Exception as exc:
        errors.append(f"coacd legacy install failed: {exc}")
    try:
        addon_root = Path(bpy.utils.user_resource("SCRIPTS", path="addons", create=True))
        target = addon_root / "coacd_blender_addon"
        if target.exists():
            shutil.rmtree(target)
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.namelist():
                if member.endswith("/"):
                    continue
                rel = member
                if rel.startswith("coacd_blender_addon/"):
                    rel = rel[len("coacd_blender_addon/") :]
                if not rel:
                    continue
                destination = safe_extract_destination(target, member, rel)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
        print(f"Extracted CoACD add-on to {target}")
    except Exception as exc:
        errors.append(f"coacd manual install failed: {exc}")
    return errors


def install_l4d2_tools(zip_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        print(f"Installing L4D2 Character Tools from {zip_path}")
        addon_root = Path(bpy.utils.user_resource("SCRIPTS", path="addons", create=True))
        target = addon_root / "Blender_L4D2_Character_Tools"
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            members = archive.namelist()
            roots = {name.split("/", 1)[0] for name in members if "/" in name}
            root = sorted(roots)[0] if roots else ""
            for member in members:
                if member.endswith("/"):
                    continue
                rel = member[len(root) + 1 :] if root and member.startswith(root + "/") else member
                if not rel:
                    continue
                destination = safe_extract_destination(target, member, rel)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
        print(f"Extracted L4D2 Character Tools add-on to {target}")
        return []
    except Exception as exc:
        errors.append(f"L4D2 tools manual install failed: {exc}")
    try:
        call_operator(
            bpy.ops.preferences.addon_install,
            filepath=str(zip_path),
            overwrite=True,
            enable_on_install=True,
        )
    except Exception as exc:
        errors.append(f"L4D2 tools legacy install failed: {exc}")
    return errors


def ensure_pillow(check_only: bool) -> None:
    if pillow_registered():
        print("Pillow is available for Material Combiner.")
        return
    if check_only:
        print("Warning: Pillow is not available; Material Combiner atlas generation may be unavailable.")
        return
    try:
        print("Installing Pillow for Blender's Python environment.")
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=False, **hidden_subprocess_kwargs())
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "Pillow"], check=True, **hidden_subprocess_kwargs())
    except Exception as exc:
        print(f"Warning: Pillow install failed; Material Combiner may be unavailable: {exc}")
        return
    if pillow_registered():
        print("Pillow is available for Material Combiner.")
    else:
        print("Warning: Pillow still is not available after install attempt.")


def ensure_sklearn(check_only: bool) -> None:
    if sklearn_registered():
        try:
            import sklearn

            print(f"Scikit-learn is available for advanced Step 6 clustering: {sklearn.__version__}")
        except Exception:
            print("Scikit-learn is available for advanced Step 6 clustering.")
        return
    if check_only:
        print("Warning: scikit-learn is not available; Step 6 will use fallback accessory clustering.")
        return
    try:
        print("Installing scikit-learn for Blender's Python environment.")
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=False, **hidden_subprocess_kwargs())
        env = dict(os.environ)
        env["PYTHONNOUSERSITE"] = "1"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--no-user",
                "scikit-learn",
                "scipy",
                "joblib",
                "threadpoolctl",
            ],
            check=True,
            env=env,
            **hidden_subprocess_kwargs(),
        )
    except Exception as exc:
        print(f"Warning: scikit-learn install failed; Step 6 will use fallback clustering: {exc}")
        return
    if sklearn_registered():
        try:
            import sklearn

            print(f"Scikit-learn is available for advanced Step 6 clustering: {sklearn.__version__}")
        except Exception:
            print("Scikit-learn is available for advanced Step 6 clustering.")
    else:
        print("Warning: scikit-learn still is not available after install attempt.")


def ensure_cats(zip_path: Path, check_only: bool) -> None:
    errors: list[str] = []
    errors.extend(enable_modules(cats_candidates(), "CATS"))
    if cats_registered():
        print("CATS importer operator is available.")
        return
    if check_only:
        raise RuntimeError("CATS importer operator is not available.")
    errors.extend(install_cats(zip_path))
    errors.extend(enable_modules(cats_candidates(), "CATS"))
    if cats_registered():
        print("CATS importer operator is available.")
        return
    raise RuntimeError("CATS importer operator is not available. " + "; ".join(errors))


def ensure_mmd_tools(cats_zip: Path, check_only: bool) -> None:
    errors: list[str] = []
    for module_name in mmd_tools_candidates():
        try:
            import addon_utils

            addon_utils.enable(module_name, default_set=True, persistent=True)
            print(f"Enabled MMD Tools add-on module: {module_name}")
            if mmd_tools_registered():
                print("MMD Tools PMX/VMD import operators are available.")
                return
        except Exception as exc:
            errors.append(f"{module_name}: {exc}")
    if mmd_tools_registered():
        print("MMD Tools PMX/VMD import operators are available.")
        return
    if check_only:
        raise RuntimeError("MMD Tools PMX/VMD import operators are not available.")
    errors.extend(install_mmd_tools_from_cats(cats_zip))
    for module_name in mmd_tools_candidates():
        try:
            import addon_utils

            addon_utils.enable(module_name, default_set=True, persistent=True)
            print(f"Enabled MMD Tools add-on module: {module_name}")
            if mmd_tools_registered():
                print("MMD Tools PMX/VMD import operators are available.")
                return
        except Exception as exc:
            errors.append(f"{module_name}: {exc}")
    if mmd_tools_registered():
        print("MMD Tools PMX/VMD import operators are available.")
        return
    raise RuntimeError("MMD Tools PMX/VMD import operators are not available. " + "; ".join(errors))


def ensure_source_tools(zip_path: Path, check_only: bool) -> None:
    errors: list[str] = []
    errors.extend(enable_modules(source_tools_candidates(), "Blender Source Tools"))
    if source_tools_registered():
        print("Blender Source Tools SMD importer operator is available.")
        return
    if check_only:
        raise RuntimeError("Blender Source Tools operator is not available.")
    errors.extend(install_source_tools(zip_path))
    errors.extend(enable_modules(source_tools_candidates(), "Blender Source Tools"))
    if source_tools_registered():
        print("Blender Source Tools SMD importer operator is available.")
        return
    raise RuntimeError("Blender Source Tools operator is not available. " + "; ".join(errors))


def ensure_bones_merger(zip_path: Path, check_only: bool) -> None:
    errors: list[str] = []
    errors.extend(enable_modules(bones_merger_candidates(), "Blender Bones Merger"))
    if bones_merger_registered():
        print("Blender Bones Merger operator is available.")
        return
    if check_only:
        raise RuntimeError("Blender Bones Merger operator is not available.")
    errors.extend(install_bones_merger(zip_path))
    errors.extend(enable_modules(bones_merger_candidates(), "Blender Bones Merger"))
    if bones_merger_registered():
        print("Blender Bones Merger operator is available.")
        return
    raise RuntimeError("Blender Bones Merger operator is not available. " + "; ".join(errors))


def ensure_material_combiner(zip_path: Path, check_only: bool) -> None:
    errors: list[str] = []
    errors.extend(enable_modules(material_combiner_candidates(), "Material Combiner"))
    if material_combiner_registered():
        print("Material Combiner operators are available.")
        ensure_pillow(check_only)
        return
    if check_only:
        print("Warning: Material Combiner operators are not available.")
        return
    errors.extend(install_material_combiner(zip_path))
    errors.extend(enable_modules(material_combiner_candidates(), "Material Combiner"))
    if material_combiner_registered():
        print("Material Combiner operators are available.")
        ensure_pillow(check_only)
        return
    print("Warning: Material Combiner operators are not available. " + "; ".join(errors))


def ensure_coacd(zip_path: Path, check_only: bool) -> None:
    errors: list[str] = []
    errors.extend(enable_modules(coacd_candidates(), "CoACD"))
    if coacd_registered():
        print("CoACD collision operator is available.")
        return
    if check_only:
        print("Warning: CoACD collision operator is not available; Step 8 will use internal fallback collision generation.")
        return
    errors.extend(install_coacd(zip_path))
    errors.extend(enable_modules(coacd_candidates(), "CoACD"))
    if coacd_registered():
        print("CoACD collision operator is available.")
        return
    print("Warning: CoACD collision operator is not available. " + "; ".join(errors))


def ensure_l4d2_tools(zip_path: Path, check_only: bool) -> None:
    errors: list[str] = []
    errors.extend(enable_modules(l4d2_tools_candidates(), "L4D2 Character Tools"))
    if l4d2_tools_registered():
        print("L4D2 Character Tools VRD operators are available.")
        return
    if check_only:
        raise RuntimeError("L4D2 Character Tools VRD operators are not available.")
    errors.extend(install_l4d2_tools(zip_path))
    errors.extend(enable_modules(l4d2_tools_candidates(), "L4D2 Character Tools"))
    if l4d2_tools_registered():
        print("L4D2 Character Tools VRD operators are available.")
        return
    raise RuntimeError("L4D2 Character Tools VRD operators are not available. " + "; ".join(errors))


def save_preferences() -> None:
    try:
        bpy.ops.wm.save_userpref()
        print("Saved Blender user preferences.")
    except Exception as exc:
        print(f"Warning: could not save Blender preferences: {exc}")


def main() -> int:
    args = parse_args()
    for path in (args.cats_zip, args.source_tools_zip, args.bones_merger_zip, args.material_combiner_zip, args.coacd_addon_zip, args.l4d2_tools_zip):
        if not path.exists():
            raise FileNotFoundError(path)
    ensure_cats(args.cats_zip, args.check_only)
    ensure_mmd_tools(args.cats_zip, args.check_only)
    ensure_source_tools(args.source_tools_zip, args.check_only)
    ensure_bones_merger(args.bones_merger_zip, args.check_only)
    ensure_material_combiner(args.material_combiner_zip, args.check_only)
    ensure_coacd(args.coacd_addon_zip, args.check_only)
    ensure_l4d2_tools(args.l4d2_tools_zip, args.check_only)
    ensure_sklearn(args.check_only)
    if not args.check_only:
        save_preferences()
    print("Blender add-on setup verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
