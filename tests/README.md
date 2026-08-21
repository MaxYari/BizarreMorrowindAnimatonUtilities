# Test tools

Neither tool needs Blender or a network connection. Run both before shipping.

## check_names.py — static undefined-name check

    python3 tests/check_names.py .

`py_compile` only validates syntax, so a call to a function that was deleted
compiles cleanly and fails at runtime with `NameError`. This walks each module's
scopes, reports any name load that cannot resolve, and verifies every
`from .module import name` actually exists.

## run_tests.py — executes the operators

    python3 tests/run_tests.py .

`tests/bpy.py` is a mock `bpy` faithful enough to run `ExportAnimationOperator`
and `TransferToBeastsOperator` start to finish in a normal Python process, so
`NameError`, `AttributeError`, wrong branches and lost cleanup surface as
failures.

Requires the addon directory to be importable as a package whose name is a valid
Python identifier. The shipped folder name contains no hyphens, so
`python3 tests/run_tests.py .` works from inside it.

Covered:

| test | guards against |
|---|---|
| `test_export_third_person` | export path, rename restored, user action restored, temp action deleted |
| `test_export_as_switches_reference` | the 1st/3rd toggle actually changing reference armature |
| `test_transfer_creates_beast_rig` | beast rigs created and aligned to the source rig |
| `test_transfer_realigns_damaged_rig` | a rig left at the origin by v1.5.0 being corrected |
| `test_beast_keeps_its_name_on_export` | the v1.6.0 regression — beast armatures must not be renamed to Bip01 |
| `test_no_transform_written_at_export` | export never mutating the rig transform |

## What they cannot do

They do not evaluate constraints, run `nla.bake`, or exercise `io_scene_mw`.
Anything about what actually lands in the `.nif`/`.kf` still needs Blender.

## Running inside real Blender

For a genuine environment, headless Blender runs the same operators against the
real API:

    blender -b your_scene.blend --python-expr "
    import bpy
    bpy.ops.preferences.addon_enable(module='BizarreMorrowindAnimatonUtilities-main')
    bpy.context.view_layer.objects.active = bpy.data.objects['Bip01']
    print(bpy.ops.export.transfer_to_beasts())
    print(bpy.ops.export.animation())
    "

Add `--factory-startup` to rule out interference from your own preferences.
