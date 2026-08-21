# Changelog

## 1.6.4 — the offset lives inside a Child Of constraint

1.6.2 and 1.6.3 assigned `khajiit_armature.matrix_world = source_obj.matrix_world`.
That cannot work, and reading the object-level constraints out of the blend shows
why.

### What is actually on the object

`Khajiit Armature` carries an **object-level Child Of constraint** targeting
`Khajiit Retarget Driver Armature`. All nine channels enabled
(`flag = 0x01ff`), no bone subtarget, and a baked inverse matrix:

    inverse_matrix translation = (-0.0171, 1.7577, -0.7640)

That is the inverse of the driver's authored transform `(1.7570, 0.0171, 0.7634)`
rotated 90 degrees about Z — i.e. whatever the driver's world matrix was when
somebody pressed **Set Inverse**. The stubborn ~1.757 offset is not on the object
at all. It is stored inside the constraint.

Child Of evaluates as:

    world = target_world @ inverse_matrix @ basis

Assigning `matrix_world` on a constrained object writes the **basis** — Blender
does not invert constraints out — and the constraint then recomputes the world
matrix on the next depsgraph evaluation. So the assignment was silently discarded
every time, which is exactly the behaviour reported: some axes appear to shift,
the main horizontal offset does not budge.

Running the new test against 1.6.3 reproduces it:

    Khajiit at Matrix(loc=(-0.0171, 1.757, -0.7634)), source at Matrix(loc=(0.0, 0.0, 0.0))

### The fix

The constraint is deliberate — it propagates the driver's root motion onto the
beast rig — and it is neutral only while the driver sits where it was when the
inverse was baked. So move the driver, set the Khajiit basis, then **re-derive the
inverse**, which is what Blender's Set Inverse button does:

```python
source_matrix = source_obj.matrix_world.copy()

driver_armature.matrix_basis = source_matrix.copy()   # no parent, no constraints
bpy.context.view_layer.update()

khajiit_armature.matrix_basis = source_matrix.copy()
for constraint in khajiit_armature.constraints:
    if constraint.type == 'CHILD_OF':
        if constraint.target is None:
            constraint.target = driver_armature
        constraint.inverse_matrix = constraint.target.matrix_world.inverted_safe()
bpy.context.view_layer.update()
```

Which leaves:

    world = driver_world @ inverse(driver_world) @ source = source

and once the action moves the driver by some delta `D`:

    world = D @ source

so root motion still propagates. The constraint is not removed, disabled or
cleared.

### New regression test

`test_childof_does_not_defeat_alignment` builds the Khajiit rig with the real
Child Of setup — target, and the inverse baked to the driver's authored transform
— then asserts two things for both an identity source rig and an offset one:

* the **evaluated** world matrix equals the source rig's, and
* moving the driver still moves the beast rig by the same delta.

`tests/bpy.py` now models Child Of evaluation, `matrix_basis` vs `matrix_world`,
matrix multiply and inverse, so this class of fault is catchable at all. The
mock's computed inverse of the driver's authored transform reproduces the
blend-stored `invmat` to rounding, which is what confirms the formula.

Against 1.6.3 the suite reports 3 of 7 failing; against this build, 7 of 7 pass.

### Note on the residual

If the beast rig still does not land exactly on the Bip01 root after this, the
next thing to check is whether your Bip01 armature object itself has a
non-identity transform — the operator now warns when it does. `matrix_world`
alignment is exact, but if the source rig is offset then both rigs are offset
together and io_scene_mw will wrap the exported root in an extra NiNode.

---

## 1.6.3 — fixes for the regressions I introduced in 1.6.2

### Fixed: `NameError: purge_action_by_name is not defined`

When I removed `beast_rigs_are_zeroed()` in 1.6.2 I sliced from its `def` to the
start of `copy_pose_markers`, which took `purge_action_by_name` with it. It is
called from `prepare_action_for_export` (twice) and `prepare_arp_rig_for_export`,
so every export and every transfer died at the first call. The function is
restored verbatim from `main`.

`py_compile` passes on a call to a deleted function, which is why my checks
missed it. There is now a proper checker (below).

**This single fault explains both reported symptoms.** `prepare_action_for_export`
runs after the 1st/3rd-person reference armature is chosen but before anything
observable is produced, so the toggle appeared inert and no Khajiit armature was
ever created. Neither is a separate bug — the `export_as` chain is byte-identical
to `main` and is now covered by a test that asserts the two modes load different
reference armatures.

### Fixed: `AttributeError` on a freshly appended driver armature

```python
driver_armature.animation_data.action = cloned_action
```

An object appended from the reference blend can have no `animation_data` at all.
Now creates it first, and the `action_slot` assignment is guarded for Blender
versions without slots. Found by the new test harness, not by reading.

### Fixed: transfer aborted once Blender garbage-collected the stance action

"Khajiit Default Stance" is the only action in `morrowind_reference_armatures.blend`
and it arrives attached to the Khajiit Armature. After a transfer that armature
holds the baked `[Baked][Beast]` action instead, so the stance action drops to
zero users and Blender discards it on the next save/reload — while the armatures
survive in the file.

The next transfer then found the rigs present, skipped the append, and hit:

    Can't find Khajiit Default Stance action... Can't continue.

The append condition now also triggers on a missing stance action, which restores
it (appending an object brings its animation data along). This is a latent fault
from well before 1.6.x and a strong candidate for "no khajiit armature is
successfully created" on a reopened file.

### Added: two test tools, in `tests/`

Neither needs Blender or network access.

**`check_names.py`** — walks each module's scopes and reports any name load that
cannot resolve, plus any `from .module import name` that does not exist. Catches
exactly the class of fault above.

    python3 tests/check_names.py <addon_dir>

**`run_tests.py` + `bpy.py`** — a mock `bpy` faithful enough to execute the real
operator bodies, so `NameError`, `AttributeError`, wrong branches and lost cleanup
surface as failures. Six tests: third-person export, the 1st/3rd toggle changing
reference armature, beast rig creation and alignment, realignment of a rig damaged
by v1.5.0, the 1.6.0 regression guard that beast armatures keep their name, and
that export never mutates the rig transform.

    python3 tests/run_tests.py <addon_dir>

Both fail every test against the 1.6.2 I sent you and pass against this build.

They are not a Blender substitute — they cannot verify constraint evaluation,
bake output, or anything io_scene_mw writes. They verify that the addon's own
control flow is sound before it reaches Blender.

---

## 1.6.2 — beast rigs follow the source rig

1.6.1 removed the `location = (0,0,0)` lines but stopped there, leaving the beast
rigs at their authored offset ~1.9 units from the source rig. That was half the
answer: the offset is authored, but it is not meant to survive a transfer.

### What the retarget setup actually requires

Reading the constraints out of `morrowind_reference_armatures.blend`:

| type | count | space |
|---|---|---|
| Copy Rotation | 54 | WORLD |
| Copy Location | 4 | WORLD |
| IK | 4 | WORLD |
| Copy Transforms | 1 | CUSTOM* |
| Child Of | 1 | WORLD |

\* the four constraints flagged CUSTOM have `space_object = None`, so Blender
falls back to World. Everything evaluates in world space.

Copy Rotation in world space is orientation-only and does not care where the rigs
sit. **The four Copy Location constraints do** — they place Khajiit bones at the
driver's bone positions in world space, so the driver and the Khajiit rig have to
occupy the same world transform.

The driver does not keep its own transform. Assigning the source action
overwrites it every frame, because `bake_action_on_armature` bakes
`bake_types={'OBJECT'}` and those object-level keys carry the source rig's
transform. The driver lands wherever the source rig is; the Khajiit rig stays at
its authored offset; the four Copy Location constraints then drag part of the
skeleton across the gap while the Copy Rotation bones stay put.

### The fix

`TransferToBeastsOperator` now copies the source rig's full `matrix_world` —
rotation included — onto both beast rigs before baking:

```python
source_matrix = source_obj.matrix_world.copy()
driver_armature.matrix_world = source_matrix
khajiit_armature.matrix_world = source_matrix
bpy.context.view_layer.update()
```

No assumption about where the source rig is. Against the two things that matter:

| | driver↔Khajiit separation | Khajiit `matrix_local` |
|---|---|---|
| v1.5.0 (`.location` zeroed, rotation left at 90°) | 0.0000 | not identity → **wrapped** |
| v1.6.1 (authored offset restored) | **1.9150** | not identity → **wrapped** |
| v1.6.2 (`matrix_world` copied from source) | 0.0000 | identity → **file root** |

That second column is `io_scene_mw.get_root_output()`, which uses the armature as
the file root only when `np.allclose(matrix_local, ID44, rtol=0, atol=1e-4)`
passes. Otherwise it inserts an extra `NiNode` named after the file and demotes
the armature to a child carrying the offset. v1.5.0 failed it because zeroing
location left the authored 90° Z rotation; v1.6.1 failed it because of the offset
itself. Matching the source rig passes it, for the same reason humanoid exports
already work.

### Also in this release

* **Export-time root diagnostic.** If the armature about to be exported has a
  non-identity transform, the operator reports the offending translation and says
  the root will be wrapped. It **warns and continues** — it never blocks an
  export. (The 1.6.0 abort was a mistake and is not coming back.)
* Removed `beast_rigs_are_zeroed()` from 1.6.1. It is redundant now that the
  transform is set unconditionally on every transfer, so a rig left at the origin
  by v1.5.0 repairs itself the next time you run Transfer to Beasts.
* Replaced with `matrix_is_identity()`, which mirrors io_scene_mw's own tolerance
  exactly rather than guessing at a fingerprint.

**Still delete any `[Baked][Beast]` actions produced by v1.5.0 or v1.6.1** and
redo the transfer. The wrong transform was baked into them as object-level keys
and no code change repairs an existing action.

### Carried forward from 1.6.1

The armature rename block remains byte-identical to commits `2673858` and
`8bef591` — beast armatures keep their name, Morrowind rigs are renamed to
`Bip01`. `operators.py` and `utils.py` are still untouched. The number of
`CANCELLED` paths in `exporter.py` is unchanged from `main`.

---

## 1.6.1 — beast root transform

### Retracted from 1.6.0

1.6.0 made the temporary rename to `Bip01` unconditional, on the theory that the
beast skeleton root name was the fault. That was wrong: it broke non-beast
exports and did not address the actual problem. The rename block is now
byte-identical to commits `2673858` and `8bef591`, both of which worked — beast
armatures keep their own name, Morrowind rigs are renamed:

```python
is_beast = "Khajiit" in original_name or "Argonian" in original_name
if not is_beast and not (original_name.startswith('Bip01') or original_name.startswith('Bip01.')):
    current_armature.name = "Bip01"
```

The `effective_root_name` pre-flight check and its abort path are removed
entirely. This release is built by patching `main`, not by carrying 1.6.0
forward.

### Fixed: the beast root node was forced to the wrong place

Diffing `8bef591` (5 Apr, working) against `main` (16 Apr, broken) leaves four
changes in the beast path. Three are the ARP rig finder and the duplicate
method. The fourth is the fault:

```python
# The armatures may be saved with a positional offset in the blend file.
# Force both to the origin so they overlay the Bip01 rig correctly.
driver_armature.location = (0.0, 0.0, 0.0)
khajiit_armature.location = (0.0, 0.0, 0.0)
```

Neither earlier commit contains these lines, and
`morrowind_reference_armatures.blend` is byte-identical across all three
(`82cacbc1...`), so the offset the comment calls accidental is authored and
unchanged. Read out of the blend's DNA:

| object | location | rotation |
|---|---|---|
| `Khajiit Armature` | `(1.7564, 0.0171, 0.7628)` | `(0, 0, 1.5708)` |
| `Khajiit Retarget Driver Armature` | `(1.7570, 0.0171, 0.7634)` | `(0, 0, 1.5708)` |
| `3rd Person Khajiit Reference Armature` | `(-5.8928, 0.0119, 0.7485)` | `(0, 0, 1.5708)` |

The two beast rigs are a matched pair, co-located within 0.0006 and parked about
1.9 units away from the Bip01 rig so the skeletons do not overlap in the
viewport. Every reference armature in the file carries the same 90° Z rotation.

Zeroing `.location` while leaving `.rotation_euler` at 90° could never have
"overlaid the Bip01 rig" as claimed. What it did instead:

* Displaced the beast root by 1.9150 units — `dx=1.7564, dy=0.0171, dz=0.7628`.
* Left `matrix_local` non-identity, so `io_scene_mw.get_root_output()` still took
  its wrap branch. That test is exact:
  `np.allclose(roots[0].matrix_local, ID44, rtol=0, atol=1e-4)`. When it fails,
  the armature is demoted to a child of a new `NiNode` named after the file, and
  the wrong offset is written as that child's matrix.
* Got **baked in**. The beast bake runs `bake_types={'OBJECT'}` with
  `visual_keying=True`, so the object transform live at bake time becomes
  object-level keys inside the action. The damage travelled with the
  `[Baked][Beast]` action, which is why re-exporting an existing one never
  helped.

The two lines are removed. Nothing in `exporter.py` now assigns to `.location`,
`.matrix*`, `.rotation_*`, `.scale` or `.delta_*` — verified by grep.

### Added: repair for rigs already damaged by 1.5.0

The old code mutated the appended objects in place. If you saved the .blend after
running Transfer to Beasts, `Khajiit Armature` is now parked at the origin
permanently — and because the operator reuses those objects when present, they
would never be re-appended and the damage would persist across every future
export.

`beast_rigs_are_zeroed()` detects this. Exact `(0, 0, 0)` is an unambiguous
fingerprint, since the authored values are never zero. On detection both rigs are
discarded and re-appended from the reference blend, with a warning telling you to
delete stale `[Baked][Beast]` actions and redo the transfer.

**Delete any `[Baked][Beast]` actions made with 1.5.0 and regenerate them.** They
carry the bad object keys and no code change can repair them in place.

### Also fixed

* **`and` where `or` was meant** when loading the beast rigs — a file containing
  exactly one of the two skipped the load and then dereferenced `None`.
* **Bone filtering was a silent no-op on Blender 4.4+.** `iter_fcurves` used
  `if hasattr(action, "layers") / elif hasattr(action, "fcurves")`, but on 4.4+ an
  action has both, so the `elif` was unreachable — and the taken branch looked
  for `strip.fcurves`, which is not where 4.4 keeps curves (they live under
  `strip.channelbags[].fcurves`; io_scene_mw itself uses
  `anim_utils.animdata_get_channelbag_for_assigned_slot`). Zero curves were
  yielded, so `filter_action_bones` and `set_interpolation_to_linear` both did
  nothing and every bone exported unfiltered. Now probes all three shapes and
  only falls back when the layered walk finds nothing.
  *If your output changes after this update, this is why — use **Extra Bones to
  Export** to keep anything that gets stripped, and turn on Verbose Logging to
  see the list.*
* **"Extra Bones to Export" was a dead preference** — parsed into a local and
  never passed to the filter. Now unioned into the allowed set. Empty input no
  longer yields a bogus `''` entry from `"".split(',')`.
* **Export paths were concatenated, not joined.** `f"{export_folder}{name}.nif"`
  wrote `.../Morrowind AnimationsMyAnim.nif` into the parent whenever the folder
  lacked a trailing separator, and `~` was never expanded, so the shipped default
  of `~/Morrowind Animations/` created a literal `~` folder. `resolve_export_path`
  expands `//` and `~`, joins properly and creates the directory. The
  overwrite-confirmation dialog uses the same resolver, so it no longer checks a
  different path than the one written.
* **A failed decimate left your editor as a Graph Editor.** The area-type swap had
  no `try/finally`, and `bpy.context.area` was dereferenced without a `None`
  check, which breaks when driven from the Python console.
* **Your action was left swapped out after every export.**
  `prepare_action_for_export` assigned the `[Baked][Temp]` copy and never put the
  original back; temp actions were never deleted despite `CLAUDE.md` saying they
  were. `restore_action_state` now runs in both operators' `finally` blocks.
* `bl_info["blender"]` said `(5, 1, 0)` while the README says 4.4+, so Blender
  refused to enable the addon on 4.4 and 5.0. Corrected to `(4, 4, 0)`.
* Preferences were registered *after* the panels and operators that read them.
* `panels.py` read `context.preferences.addons[__package__].preferences`
  unguarded; a `KeyError` there errors the whole panel.
* `keymaps.register()` touched `wm.keyconfigs.addon` without a `None` check,
  which raises under `blender -b`; `unregister()` removed *every* matching item
  from the shared Pose keymap rather than only its own.
* `sanitize_filename` could return `""` for an action named only of tags,
  producing a file called `.nif`.
* Bone names are extracted from data paths with a regex handling escaped quotes,
  instead of `data_path.split('"')[1]`.
* Debug `print()` calls — including one per bone constraint per export — moved
  behind a new **Verbose Logging** preference.
* Default export folder changed from `~/Morrowind Animations/` to `//`.

### Unchanged

* `operators.py` and `utils.py` are untouched.
* `morrowind_reference_armatures.blend`, `BizarreMorrowindRig.blend` and the
  images are untouched.
* The armature rename logic, verified byte-identical to `2673858` and `8bef591`.
* Operator `bl_idname`s, so existing keymaps and scripts still work.
