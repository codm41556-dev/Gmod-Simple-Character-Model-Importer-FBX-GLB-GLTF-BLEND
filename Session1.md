**Project Summary**

Repo: `C:\Users\1peng\Modding\ipg\!mmd_character_model_importer\MMD Character Importer`

This is a PySide/Blender-based MMD-to-Garry’s-Mod importer. The main GUI is in [mmd_character_importer_gui.py](</c:/Users/1peng/Modding/ipg/!mmd_character_model_importer/MMD Character Importer/tools/mmd_character_importer_gui.py>), with backend orchestration in [mmd_character_importer_core.py](</c:/Users/1peng/Modding/ipg/!mmd_character_model_importer/MMD Character Importer/tools/mmd_character_importer_core.py>). Most heavy model processing is done by step-specific Blender scripts under `tools/`.

**Workflow Steps**

- Step 1 imports PMX, runs preflight, previews model, and warns if many shapekeys match `reference/keywords/Warning_Keyword.txt`.
- Step 2 fixes source skeleton/model and clears custom split normals.
- Step 3 fixes Source spine bones and must preserve vertex groups/weights correctly.
- Step 4 sorts/merges bones, including a manual Blender bone-merge path before auto-merge.
- Step 5 sorts materials, defaults alpha `< 0.5` materials off, preserves user Keep overrides, can generate black fallback PNGs, and offsets stacked material face groups.
- Step 6 sorts bodygroups, supports auto and manual Blender editing, 65,535 / 32,767 vertex limits, scaling presets, and required `Face` / `Body`.
- Step 7 sorts flexes, normalizes Rest/Max, supports extra VTA/bodygroups such as `Face_02`, and keeps flex metadata in JSON.
- Step 8 generates collision with CoACD, supports bodygroup seed selection, caching/quality presets, and should not rerun CoACD during Apply.
- Step 9 exports raw SMD/VTA and runs repaired proportion trick from `reference/proportion_trick_script-main_new/Proportion_Trick`.
- Step 10 generates c_arms.
- Step 11 generates VRD with frame preview and adjustable intensity sliders.
- Step 12 processes textures; normal maps are disabled by default unless user enables per-row generation/use.
- Step 13 generates icons/art from PMX/VMD, unshaded on white background, with material filtering.
- Step 14 generates QC, compiles, composes addon folder/GMA, writes dynamic importer manifest, handles jigglebones/materials/Lua.
- Step 15 optionally generates release description/translations.

**Recent Important Fixes**

- Step 9 VTA replacement was fixed so all raw `.vta` files are preserved, not only `Face.vta` / `Body.vta`.
- Step 14 QC generation was fixed so any bodygroup with matching `.vta` gets a flex model block, e.g. `Face_02.smd` + `Face_02.vta`.
- Step 14 texture VTF conversion now stages non-power-of-two textures into power-of-two square PNGs before VTFCmd.
- Localization files were expanded under `tools/i18n/`; English is the source of truth.
- Build packaging was optimized to avoid bundling the full duplicate repaired proportion package.

**GMod Addon Runtime**

A separate addon exists at `reference/dynamic_model_importer/gmod_addon`. It discovers manifests written by Step 14 under:

`data_static/dynamic_model_importer/models/<model>_sheepylord.json`

It shows manifest and legacy models separately, selects one model at a time, and spawns only when the user clicks the world with the tool.

**Key Files**

- GUI: `tools/mmd_character_importer_gui.py`
- Core: `tools/mmd_character_importer_core.py`
- Step 5: `tools/blender_sort_materials.py`
- Step 6: `tools/blender_sort_bodygroups.py`
- Step 7: `tools/blender_sort_flexes.py`
- Step 8: `tools/blender_sort_collision.py`
- Step 9: `tools/blender_export_proportion_trick.py`
- Step 11: `tools/blender_sort_vrd.py`
- Step 12: `tools/sort_param_textures.py`
- Step 14: `tools/sort_qc_compile.py`
- i18n: `tools/i18n/en_us.json` plus translated locale JSONs

**Working Style**

Use `rg` for search, `apply_patch` for edits, and run `python -m py_compile` on modified Python files. The worktree may be dirty; do not revert unrelated changes. The user expects direct implementation unless explicitly asking for a plan.