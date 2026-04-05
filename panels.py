import bpy
from .exporter import ExportAnimationOperator, TransferToBeastsOperator
from .operators import MuteConstraintsOperator, RestoreConstraintsOperator

# Check Blender version
BLENDER_VERSION = bpy.app.version


def add_separator(layout, factor=1.0, separator_type='LINE'):
    """Add a separator to the layout, compatible with different Blender versions."""
    if bpy.app.version >= (4, 3, 0):
        layout.separator(factor=factor, type=separator_type)
    else:
        layout.separator(factor=factor)

class BoneGroupsPanel(bpy.types.Panel):
    bl_label = "Selection Groups"
    bl_idname = "OBJECT_PT_bone_groups"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bizarre Anim'

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        column = box.column()

        # Add separator
        add_separator(column, factor=1.0, separator_type='LINE')

        column.label(text="Quickly save and invoke bone selection groups",icon="INFO")
        column.label(text="Assign: Ctrl + Number")
        column.label(text="Select: Number")
        

class ExportPanel(bpy.types.Panel):
    bl_label = "Conversion and Export"
    bl_idname = "OBJECT_PT_export_animation"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bizarre Anim'

    def draw(self, context):
        layout = self.layout
        addon_prefs = context.preferences.addons[__package__].preferences

        box = layout.box()
        column = box.column()

        # Add separator
        add_separator(column, factor=1.0, separator_type='LINE')

        # Transfer to Beasts button
        column.label(text="Conversion to Khajiit/Argonian",icon="ARMATURE_DATA")
        add_separator(column, factor=0.5, separator_type='SPACE')
        column.operator(TransferToBeastsOperator.bl_idname, text="Transfer to Beasts")
        add_separator(column, factor=1.0, separator_type='SPACE')

        box = layout.box()
        column = box.column()

        # Add separator
        add_separator(column, factor=1.0, separator_type='LINE')

        # Export folder field
        column.label(text="Export Folder:",icon="FILE_FOLDER")
        column.prop(addon_prefs, "export_folder", text="")

        # Retained extra bones field
        column.label(text="Extra Bones to Export:",icon="BONE_DATA")
        column.prop(addon_prefs, "retained_extra_bones", text="")

        # Export as dropdown
        column.label(text="Export as:",icon="ARMATURE_DATA")
        column.prop(addon_prefs, "export_as", text="")        

        # Export button
        add_separator(column, factor=1.0, separator_type='SPACE')
        add_separator(column, factor=1.0, separator_type='LINE')
        add_separator(column, factor=1.0, separator_type='SPACE')
        column.operator(ExportAnimationOperator.bl_idname, text="Export Animation")
        row = column.row(align=True)
        row.prop(addon_prefs, "enable_root_motion_arp", text="Root Motion (ARP)")
        row.label(text="", icon='INFO')
        add_separator(column, factor=1.0, separator_type='SPACE')
        

        box = layout.box()
        column = box.column()        

        # Add separator
        add_separator(column, factor=1.0, separator_type='LINE')
        

        # Constraints management section        
        column.label(text="Constraints management",icon="CONSTRAINT_BONE")
        add_separator(column, factor=0.5, separator_type='SPACE')

        # Buttons for muting and restoring constraints
        row = column.row(align=True)
        row.operator(MuteConstraintsOperator.bl_idname, text="Mute Constraints")
        row.operator(RestoreConstraintsOperator.bl_idname, text="Restore Constraints")

        column.label(text="Removing constraints allows you to properly view baked actions.", icon="INFO")
        add_separator(column, factor=1.0, separator_type='SPACE')




def register():     
    bpy.utils.register_class(ExportPanel)
    bpy.utils.register_class(BoneGroupsPanel)

def unregister():        
    bpy.utils.unregister_class(BoneGroupsPanel)    
    bpy.utils.unregister_class(ExportPanel)
