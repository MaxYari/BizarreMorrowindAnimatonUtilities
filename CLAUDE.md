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


## Beast retargeting: do not touch the armature transforms

`morrowind_reference_armatures.blend` stores the beast rigs at an **authored**
offset:

    Khajiit Armature                   loc (1.7564, 0.0171, 0.7628)  rot Z 90 deg
    Khajiit Retarget Driver Armature   loc (1.7570, 0.0171, 0.7634)  rot Z 90 deg

They are a matched pair, deliberately parked ~1.9 units from the Bip01 rig so the
skeletons do not overlap in the viewport. Every reference armature in the file
carries the same 90 degree Z rotation.

That offset must not survive a transfer. Every retarget constraint in the file
evaluates in WORLD space (54 Copy Rotation, 4 Copy Location, 4 IK, 1 Copy
Transforms, 1 Child Of; the four flagged CUSTOM have no custom space object, so
Blender falls back to World). The 4 Copy Location constraints place Khajiit bones
at the driver's bone positions in world space, so driver and Khajiit MUST share a
world transform -- and the driver is dragged to the source rig by the action's
object-level keys.

So `TransferToBeastsOperator` copies `source_obj.matrix_world` onto both beast
rigs before baking. Copy the FULL matrix, never just `.location`: v1.5.0 zeroed
location only, which assumed the source rig was at the origin and left the
authored 90 degree Z rotation in place.

Why it is destructive:

* `io_scene_mw.get_root_output()` tests `np.allclose(roots[0].matrix_local, ID44,
  rtol=0, atol=1e-4)`. Any non-identity root transform makes it wrap the armature
  in an extra `NiNode` named after the file, demoting the armature to a child that
  carries the offset. Zeroing location while leaving the 90 degree rotation does
  not reach identity, so this branch is taken either way -- just with the wrong
  numbers.
* `bake_action_on_armature` bakes `bake_types={'OBJECT'}` with
  `visual_keying=True`, so whatever object transform is live at bake time becomes
  object-level keys inside the action. A transform error is therefore baked into
  the `[Baked][Beast]` action and cannot be fixed by re-exporting.

`beast_rigs_are_zeroed()` detects rigs left at exactly (0,0,0) by v1.5.0 and
re-appends them. Exact zero is safe as a fingerprint because the authored values
are never zero.

## Armature rename on export

`ExportAnimationOperator` renames the armature object to `Bip01` for the duration
of the export, **except** for beast armatures, which keep their own name. This
block is byte-identical to commits `2673858` and `8bef591`. v1.6.0 made the
rename unconditional and that broke every non-beast export; it was reverted in
1.6.1. Leave it alone.

## Blender action API

Go through `exporter.iter_fcurve_containers()`, which probes
`layer.strips[].channelbags[].fcurves`, then `layer.strips[].fcurves`, and falls
back to `action.fcurves` only when the layered walk found nothing. Do not
reintroduce an `if hasattr(action, "layers") / elif hasattr(action, "fcurves")`
chain: on 4.4+ an action has both, so the `elif` is unreachable and bone
filtering silently becomes a no-op.


## The beast rig's Child Of constraint

`Khajiit Armature` has an OBJECT-level Child Of constraint targeting
`Khajiit Retarget Driver Armature`, all nine channels on, with a baked inverse
matrix (translation `(-0.0171, 1.7577, -0.7640)` = the inverse of the driver's
authored world transform).

Child Of evaluates as `world = target_world @ inverse_matrix @ basis`. Assigning
`obj.matrix_world` writes the BASIS only -- Blender does not invert constraints
out -- so the constraint overwrites the result on the next depsgraph evaluation.
Never try to place this rig with a `matrix_world` assignment alone; v1.6.2 and
v1.6.3 both failed that way.

To relocate the pair: move the driver, set the Khajiit basis, then re-derive
`constraint.inverse_matrix = constraint.target.matrix_world.inverted_safe()`.
That is the Set Inverse button, and it keeps root-motion propagation intact.

Do not delete, mute or clear the constraint: it is what carries the driver's root
motion onto the beast rig.
