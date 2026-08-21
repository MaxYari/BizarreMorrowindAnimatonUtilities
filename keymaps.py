import bpy
from .operators import (
    AssignBoneGroupOperator,
    SelectBoneGroupOperator
)

# (keymap, keymap_item) pairs this addon added, so unregister removes exactly
# those rather than every matching item in the shared Pose keymap.
_addon_keymaps = []

_KEYMAP_NUMBERS = ('ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE')


def register():
    wm = bpy.context.window_manager
    keyconfigs = getattr(wm, "keyconfigs", None)
    addon_config = getattr(keyconfigs, "addon", None) if keyconfigs else None

    # keyconfigs.addon is None when Blender runs headless (-b).
    if addon_config is None:
        return

    km = addon_config.keymaps.new(name='Pose', space_type='EMPTY')

    for index, key in enumerate(_KEYMAP_NUMBERS, start=1):
        kmi = km.keymap_items.new(AssignBoneGroupOperator.bl_idname, type=key, value='PRESS', ctrl=True)
        kmi.properties.group_number = index
        _addon_keymaps.append((km, kmi))

        kmi = km.keymap_items.new(SelectBoneGroupOperator.bl_idname, type=key, value='PRESS')
        kmi.properties.group_number = index
        _addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in _addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except (RuntimeError, ReferenceError):
            pass
    _addon_keymaps.clear()
