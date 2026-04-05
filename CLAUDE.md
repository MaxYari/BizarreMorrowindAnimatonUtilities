# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Blender 4.4+ addon (`Bizarre Morrowind Anim Utils`) for retargeting and exporting animations to Morrowind's `.nif`/`.kf` format. It wraps the [Blender Morrowind Plugin](https://github.com/Greatness7/io_scene_mw/releases) (`io_scene_mw`) which must be installed separately and is invoked via `bpy.ops.export_scene.mw(...)`.

## Installation / Development Workflow

There is no build step. To test changes:
1. Zip the repository folder.
2. In Blender: `Edit > Preferences > Add-ons > Install from Disk`, select the zip.
3. Or for faster iteration: symlink the folder into Blender's addons directory and reload scripts via `bpy.ops.script.reload()` or the Blender scripting workspace.

There are no automated tests — all testing is done manually inside Blender.

## Module Structure

| File | Role |
|------|------|
| `__init__.py` | Addon entry point; defines `BizarreAnimUtils` preferences (export folder, extra bones, export type, root motion toggle); wires `register`/`unregister` |
| `exporter.py` | Core export logic — all animation baking, ARP rig detection/duplication, reference armature loading, bone filtering, decimation, and the two main operators (`ExportAnimationOperator`, `TransferToBeastsOperator`) |
| `operators.py` | Auxiliary operators: bone group assign/select, mute/restore constraints |
| `panels.py` | UI panels in `View3D > UI > Bizarre Anim` tab |
| `keymaps.py` | Registers `Ctrl+Number` (assign) / `Number` (select) hotkeys for bone groups in Pose mode |
| `utils.py` | In-memory `bone_groups` dict; `assign_bone_group` / `select_bone_group` helpers |
| `morrowind_reference_armatures.blend` | External blend file containing reference armatures loaded at export time: `"3rd Person Reference Armat"`, `"3rd Person Khajiit Reference Armature"`, `"1st Person Reference Armat"`, `"Khajiit Retarget Driver Armature"`, `"Khajiit Armature"` |

## Key Concepts

### Action naming convention
- `[Raw] My Anim` — source action with constraints active; required for export/baking
- `[Baked] My Anim` — already-baked action; can be exported directly (skips bake step)
- `[Baked][Temp] My Anim` — transient copy created during export, deleted after
- `[Baked][Beast] Beast My Anim` — output of TransferToBeasts

### Two export paths
1. **Direct Morrowind rig** (`Bip01*` armature): `prepare_action_for_export` bakes on the rig itself.
2. **AutoRig Pro rig** (detected by presence of `c_traj` pose bone): `prepare_arp_rig_for_export` finds the Morrowind rig constrained to the ARP rig, duplicates it, bakes onto the duplicate, then proceeds as path 1. The duplicate is always cleaned up in a `finally` block.

### Reference armatures
Loaded from `morrowind_reference_armatures.blend` at runtime using `bpy.data.libraries.load`. They define the canonical bone sets — `filter_action_bones` strips any bones not present in the chosen reference armature before export.

### Blender API compatibility
- Uses Blender 4.x layered action API (`action.layers` / `strip.fcurves`) with a legacy `action.fcurves` fallback in `iter_fcurves`.
- `panels.py` has a version check for `separator(type=...)` (4.3+).
- `utils.py` has a bone select compatibility shim for Blender 5.1+.
