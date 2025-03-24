import bpy
from .operators import (
    AutoPoseKeyframeOperator,
    AssignBoneGroupOperator,
    SelectBoneGroupOperator,
    DisableAutoPosingSelectedOperator,
    DisableAutoPosingAllOperator
)

def register():
    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='Pose', space_type='EMPTY')

    # Register hotkeys for assigning and selecting bone groups
    keymap_numbers = ['ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE']
    for i, key in enumerate(keymap_numbers, start=1):
        km.keymap_items.new(AssignBoneGroupOperator.bl_idname, type=key, value='PRESS', ctrl=True).properties.group_number = i
        km.keymap_items.new(SelectBoneGroupOperator.bl_idname, type=key, value='PRESS').properties.group_number = i

    # Register hotkeys for disabling autoposing
    km.keymap_items.new(DisableAutoPosingSelectedOperator.bl_idname, type='A', value='PRESS', ctrl=True)
    km.keymap_items.new(DisableAutoPosingAllOperator.bl_idname, type='A', value='PRESS', ctrl=True, shift=True)

    # Register hotkey for AutoPoseKeyframeOperator
    km.keymap_items.new(AutoPoseKeyframeOperator.bl_idname, 'I', 'PRESS')

def unregister():
    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.get('Pose')
    if km:
        for kmi in km.keymap_items:
            if kmi.idname in {
                AssignBoneGroupOperator.bl_idname,
                SelectBoneGroupOperator.bl_idname,
                DisableAutoPosingSelectedOperator.bl_idname,
                DisableAutoPosingAllOperator.bl_idname,
                AutoPoseKeyframeOperator.bl_idname
            }:
                km.keymap_items.remove(kmi)
