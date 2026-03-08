import bpy
from .operators import (    
    AssignBoneGroupOperator,
    SelectBoneGroupOperator    
)

def register():
    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='Pose', space_type='EMPTY')

    # Register hotkeys for assigning and selecting bone groups
    keymap_numbers = ['ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE']
    for i, key in enumerate(keymap_numbers, start=1):
        km.keymap_items.new(AssignBoneGroupOperator.bl_idname, type=key, value='PRESS', ctrl=True).properties.group_number = i
        km.keymap_items.new(SelectBoneGroupOperator.bl_idname, type=key, value='PRESS').properties.group_number = i
   

def unregister():
    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.get('Pose')
    if km:
        for kmi in km.keymap_items:
            if kmi.idname in {
                AssignBoneGroupOperator.bl_idname,
                SelectBoneGroupOperator.bl_idname                
            }:
                km.keymap_items.remove(kmi)
