#!/usr/bin/env python3
"""Execute the addon's operators against the mock bpy and assert on the results.

Run:  python3 tests/run_tests.py <package_dir>

Each test drives a real operator's execute() method, so any NameError,
AttributeError, wrong branch or lost cleanup shows up as a failure here rather
than in Blender.
"""

import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # the mock in this directory

PACKAGE = None  # set by main()
from bpy import Matrix, Object, Action

# Authored transforms read out of morrowind_reference_armatures.blend
BEAST_LOC = (1.7564, 0.0171, 0.7628)
DRIVER_LOC = (1.7570, 0.0171, 0.7634)
Z90 = 1.5708

MW_BONES = [
    "Bip01 Pelvis", "Bip01 Spine", "Bip01 Spine1", "Bip01 Neck", "Bip01 Head",
    "Bip01 Calf.L", "Bip01 Calf.R", "Bip01 Foot.L", "Bip01 Foot.R",
    "Bip01 Hand.L", "Bip01 Hand.R",
]
BEAST_BONES = MW_BONES + ["Bip01 Tail", "Tail1", "Tail2"]
PHANTOM = "Bip01 Finger02.L"

bpy._Libraries.CONTENTS = {
    "1st Person Reference Armat": {"bones": MW_BONES, "matrix": Matrix.from_loc_rot_z((-4.5416, -0.0011, 0.7672), Z90)},
    "3rd Person Reference Armat": {"bones": MW_BONES, "matrix": Matrix.from_loc_rot_z((-3.3310, 0.0180, 0.7637), Z90)},
    "3rd Person Khajiit Reference Armature": {"bones": BEAST_BONES, "matrix": Matrix.from_loc_rot_z((-5.8928, 0.0119, 0.7485), Z90)},
    # Khajiit Armature carries an object-level Child Of targeting the driver,
    # with the inverse baked to the driver's authored transform -- as in the
    # real morrowind_reference_armatures.blend.
    "Khajiit Armature": {"bones": BEAST_BONES, "matrix": Matrix.from_loc_rot_z(BEAST_LOC, Z90),
                         "action": "Khajiit Default Stance",
                         "child_of": {"target": "Khajiit Retarget Driver Armature",
                                      "inverse": Matrix.from_loc_rot_z(DRIVER_LOC, Z90).inverted()}},
    "Khajiit Retarget Driver Armature": {"bones": BEAST_BONES, "matrix": Matrix.from_loc_rot_z(DRIVER_LOC, Z90)},
}


class Prefs:
    def __init__(self, export_folder, export_as='3RD_PERSON'):
        self.export_folder = export_folder
        self.retained_extra_bones = ""
        self.enable_root_motion_arp = False
        self.export_as = export_as
        self.verbose_logging = False


def build_scene(package_name, export_folder, export_as='3RD_PERSON', rig_matrix=None):
    bpy.reset()
    bpy._Libraries.CONTENTS = bpy._Libraries.CONTENTS  # keep contents across reset
    bpy.context.preferences.addons[package_name] = bpy._AddonEntry(Prefs(export_folder, export_as))

    rig = Object("Bip01", 'ARMATURE', MW_BONES, rig_matrix or Matrix())
    rig.animation_data_create()
    paths = [f'pose.bones["{b}"].location' for b in MW_BONES]
    paths.append(f'pose.bones["{PHANTOM}"].rotation_quaternion')
    paths.append("location")
    rig.animation_data.action = Action("[Raw] Test Anim", paths)

    bpy.context.scene.collection.objects.link(rig)
    bpy.context.object = rig
    bpy.context.view_layer.objects.active = rig
    bpy.context.selected_objects = [rig]
    return rig


# ------------------------------------------------------------------ tests

def test_export_third_person(exporter, folder):
    rig = build_scene(PACKAGE, folder, '3RD_PERSON')
    original_action = rig.animation_data.action
    result = exporter.ExportAnimationOperator().execute(bpy.context)

    assert result == {'FINISHED'}, f"export returned {result}; reports={bpy.REPORTS}"

    exports = [kw for name, kw in bpy.CALLS if name == 'export_scene.mw']
    assert exports, "export_scene.mw was never called"
    path = exports[0]['filepath']
    assert path.endswith("TestAnim.nif"), path
    assert os.path.dirname(path) == os.path.normpath(folder), path

    assert rig.name == "Bip01", f"armature left renamed as {rig.name}"
    assert rig.animation_data.action is original_action, (
        f"user action not restored (holding {rig.animation_data.action})")
    assert bpy.data.actions.get("[Baked][Temp] Test Anim") is None, "temp action leaked"


def test_export_as_switches_reference(exporter, folder):
    """The 1st/3rd toggle must change which reference armature is loaded."""
    seen = {}
    for mode, expected in (('1ST_PERSON', "1st Person Reference Armat"),
                           ('3RD_PERSON', "3rd Person Reference Armat")):
        build_scene(PACKAGE, folder, mode)
        real_loader = exporter.load_object_from_blend
        captured = []

        def spy(filepath, object_name, _real=real_loader, _c=captured):
            _c.append(object_name)
            return _real(filepath, object_name)

        exporter.load_object_from_blend = spy
        try:
            result = exporter.ExportAnimationOperator().execute(bpy.context)
        finally:
            exporter.load_object_from_blend = real_loader
        assert result == {'FINISHED'}, f"{mode} returned {result}; reports={bpy.REPORTS}"
        assert captured and captured[0] == expected, f"{mode} loaded {captured}, expected {expected}"
        seen[mode] = captured[0]

    assert seen['1ST_PERSON'] != seen['3RD_PERSON'], "export_as had no effect"


def test_transfer_creates_beast_rig(exporter, folder):
    rig = build_scene(PACKAGE, folder, '3RD_PERSON')
    source_matrix = rig.matrix_world.copy()
    result = exporter.TransferToBeastsOperator().execute(bpy.context)

    assert result == {'FINISHED'}, f"transfer returned {result}; reports={bpy.REPORTS}"

    khajiit = bpy.data.objects.get("Khajiit Armature")
    driver = bpy.data.objects.get("Khajiit Retarget Driver Armature")
    assert khajiit is not None, "Khajiit Armature was not created"
    assert driver is not None, "driver armature was not created"

    assert khajiit.matrix_world == source_matrix, (
        f"Khajiit at {khajiit.matrix_world}, source at {source_matrix}")
    assert driver.matrix_world == source_matrix, (
        f"driver at {driver.matrix_world}, source at {source_matrix}")

    beast_actions = [a for a in bpy.data.actions if a.name.startswith("[Baked][Beast]")]
    assert beast_actions, f"no [Baked][Beast] action produced; have {[a.name for a in bpy.data.actions]}"


def test_childof_does_not_defeat_alignment(exporter, folder):
    """1.6.2 regression: Child Of recomputes world, so assigning matrix_world is discarded.

    The Khajiit rig must end up at the source rig's world transform even though an
    object-level Child Of constraint sits between it and the driver.
    """
    for label, rig_matrix in (("identity", Matrix()),
                              ("offset rig", Matrix.from_loc_rot_z((2.0, -1.0, 0.5), 0.3))):
        rig = build_scene(PACKAGE, folder, '3RD_PERSON', rig_matrix=rig_matrix)
        result = exporter.TransferToBeastsOperator().execute(bpy.context)
        assert result == {'FINISHED'}, f"[{label}] transfer returned {result}; {bpy.REPORTS}"

        khajiit = bpy.data.objects.get("Khajiit Armature")
        driver = bpy.data.objects.get("Khajiit Retarget Driver Armature")

        child_of = [c for c in khajiit.constraints if c.type == 'CHILD_OF']
        assert child_of, f"[{label}] the Child Of constraint was removed"

        assert khajiit.matrix_world == rig.matrix_world, (
            f"[{label}] evaluated Khajiit world {khajiit.matrix_world} != source {rig.matrix_world}")

        # root motion must still propagate: move the driver, the beast rig follows
        delta = Matrix.from_loc_rot_z((0.0, 0.0, 5.0))
        driver.matrix_basis = delta @ driver.matrix_basis
        expected = delta @ rig.matrix_world
        assert khajiit.matrix_world == expected, (
            f"[{label}] root motion not propagated: {khajiit.matrix_world} != {expected}")


def test_transfer_realigns_damaged_rig(exporter, folder):
    """A rig left at the origin by v1.5.0 must be corrected on the next transfer."""
    rig = build_scene(PACKAGE, folder, '3RD_PERSON', rig_matrix=Matrix.from_loc_rot_z((2.0, 3.0, 0.5)))
    damaged = Object("Khajiit Armature", 'ARMATURE', BEAST_BONES, Matrix())
    Object("Khajiit Retarget Driver Armature", 'ARMATURE', BEAST_BONES, Matrix())
    bpy.context.scene.collection.objects.link(damaged)

    result = exporter.TransferToBeastsOperator().execute(bpy.context)
    assert result == {'FINISHED'}, f"transfer returned {result}; reports={bpy.REPORTS}"

    khajiit = bpy.data.objects.get("Khajiit Armature")
    assert khajiit.matrix_world == rig.matrix_world, (
        f"damaged rig not realigned: {khajiit.matrix_world} vs {rig.matrix_world}")


def test_beast_keeps_its_name_on_export(exporter, folder):
    """Regression guard for 1.6.0: beast armatures must NOT be renamed to Bip01."""
    build_scene(PACKAGE, folder, '3RD_PERSON')
    beast = Object("Khajiit Armature", 'ARMATURE', BEAST_BONES,
                   Matrix.from_loc_rot_z(BEAST_LOC, Z90))
    beast.animation_data_create()
    beast.animation_data.action = Action(
        "[Baked][Beast] Beast Test Anim",
        [f'pose.bones["{b}"].location' for b in BEAST_BONES])
    bpy.context.scene.collection.objects.link(beast)
    bpy.context.object = beast
    bpy.context.view_layer.objects.active = beast
    bpy.context.selected_objects = [beast]

    names_during_export = []
    original_ops = bpy.ops

    class Spy:
        def __getattr__(self, name):
            namespace = getattr(original_ops, name)
            if name != 'export_scene':
                return namespace

            class Inner:
                def __getattr__(inner_self, op):
                    real = getattr(namespace, op)

                    def call(*a, **kw):
                        names_during_export.append(beast.name)
                        return real(*a, **kw)
                    return call
            return Inner()

    bpy.ops = Spy()
    try:
        result = exporter.ExportAnimationOperator().execute(bpy.context)
    finally:
        bpy.ops = original_ops

    assert result == {'FINISHED'}, f"beast export returned {result}; reports={bpy.REPORTS}"
    assert names_during_export == ["Khajiit Armature"], (
        f"beast armature was renamed to {names_during_export} during export")


def test_no_transform_written_at_export(exporter, folder):
    """Export must not mutate the armature transform."""
    rig = build_scene(PACKAGE, folder, '3RD_PERSON',
                      rig_matrix=Matrix.from_loc_rot_z((1.0, 2.0, 3.0), 0.5))
    before = rig.matrix_world.copy()
    exporter.ExportAnimationOperator().execute(bpy.context)
    assert rig.matrix_world == before, "export changed the rig transform"


TESTS = [
    test_export_third_person,
    test_export_as_switches_reference,
    test_transfer_creates_beast_rig,
    test_childof_does_not_defeat_alignment,
    test_transfer_realigns_damaged_rig,
    test_beast_keeps_its_name_on_export,
    test_no_transform_written_at_export,
]


def main(package_dir):
    package_dir = os.path.abspath(package_dir)
    parent, package_name = os.path.split(package_dir)
    sys.path.insert(0, parent)

    global PACKAGE
    PACKAGE = package_name
    addon = __import__(package_name)
    exporter = __import__(f"{package_name}.exporter", fromlist=['exporter'])

    folder = tempfile.mkdtemp(prefix="mwanim-")
    failures = 0
    try:
        for test in TESTS:
            bpy.REPORTS.clear()
            try:
                test(exporter, folder)
                print(f"  PASS  {test.__name__}")
            except Exception:
                failures += 1
                print(f"  FAIL  {test.__name__}")
                for line in traceback.format_exc().strip().splitlines():
                    print(f"        {line}")
                if bpy.REPORTS:
                    for level, message in bpy.REPORTS:
                        print(f"        report[{level}] {message}")
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    print()
    if failures:
        print(f"{failures} of {len(TESTS)} test(s) failed.")
        return 1
    print(f"All {len(TESTS)} tests passed.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else '.'))
