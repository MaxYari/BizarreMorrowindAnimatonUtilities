import bpy
from .utils import is_bizarre_armature, is_ik_chain_target_bone, is_auto_posing_bone, build_ik_map, ik_maps, toggle_auto_posing, switch_kinematics_mode
from .exporter import ExportAnimationOperator, TransferToBeastsOperator
from .operators import MuteConstraintsOperator, RestoreConstraintsOperator

class IKPanel(bpy.types.Panel):
    bl_label = "Bizarre Armature Bone"
    bl_idname = "OBJECT_PT_anim_utils"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bizarre Anim'

    def draw(self, context):
        layout = self.layout
        armature = context.object  # Get the object containing the armature

        # Disable the Bone Behaviour section if the checkbox is OFF
        box = layout.box()
        
        column = box.column()
        column.separator(factor=1.0, type='LINE')
        
        if armature and is_bizarre_armature(armature):
            # Ensure IK map is built for the armature
            if armature not in ik_maps:
                build_ik_map(armature)

            selected_bones = context.selected_pose_bones
            if selected_bones:
                pose_bone = selected_bones[0]
                bone = pose_bone.bone
                if is_ik_chain_target_bone(pose_bone):
                    column.prop(bone, "mode")
                if is_auto_posing_bone(pose_bone):
                    column.prop(bone, "auto_posing")
                    column.label(text="Ctrl+A: Toggle", icon="INFO")
                    column.label(text="Ctrl+Shift+A: Toggle All")
        else:
            column.label(text="Select either an IK controller or an autoposing bone of a Bizarre Morrowind armature distributed with this addon.",icon="INFO")

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
        column.separator(factor=1.0, type='LINE')
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
        column.separator(factor=1.0, type='LINE')

        # Transfer to Beasts button
        column.label(text="Conversion to Khajiit/Argonian",icon="ARMATURE_DATA")
        column.separator(factor=0.5, type='SPACE')
        column.operator(TransferToBeastsOperator.bl_idname, text="Transfer to Beasts")
        column.separator(factor=1.0, type='SPACE')

        box = layout.box()
        column = box.column()
        column.separator(factor=1.0, type='LINE')

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
        column.separator(factor=1.0, type='SPACE')
        column.separator(factor=1.0, type='LINE')
        column.separator(factor=1.0, type='SPACE')
        column.operator(ExportAnimationOperator.bl_idname, text="Export Animation")
        column.separator(factor=1.0, type='SPACE')
        

        box = layout.box()
        column = box.column()        
        column.separator(factor=1.0, type='LINE')
        

        # Constraints management section        
        column.label(text="Constraints management",icon="CONSTRAINT_BONE")
        column.separator(factor=0.5, type='SPACE')

        # Buttons for muting and restoring constraints
        row = column.row(align=True)
        row.operator(MuteConstraintsOperator.bl_idname, text="Mute Constraints")
        row.operator(RestoreConstraintsOperator.bl_idname, text="Restore Constraints")

        column.label(text="Removing constraints allows you to properly view baked actions.", icon="INFO")
        column.separator(factor=1.0, type='SPACE')

# Define custom properties for bones
def register_bone_properties():
    # print("Registering bone properties")
    bpy.types.Bone.auto_posing = bpy.props.BoolProperty(
        name="Auto-Posing",
        description="Enable or disable auto-posing for this bone",
        default=True,
        update=toggle_auto_posing
    )
    bpy.types.Bone.mode = bpy.props.EnumProperty(
        name="Mode",
        description="Kinematics mode",
        items=[
            ('INVERSE_KINEMATICS', "Inverse Kinematics", ""),
            ('MIXED_KINEMATICS', "Mixed Kinematics", ""),
            ('FORWARD_KINEMATICS', "Forward Kinematics", "")
        ],
        default='INVERSE_KINEMATICS',
        update=switch_kinematics_mode
    )

def unregister_bone_properties():
    del bpy.types.Bone.auto_posing
    del bpy.types.Bone.mode

def register():
    register_bone_properties()    
    bpy.utils.register_class(IKPanel)
    bpy.utils.register_class(ExportPanel)
    bpy.utils.register_class(BoneGroupsPanel)

def unregister():
    unregister_bone_properties()    
    bpy.utils.unregister_class(BoneGroupsPanel)
    bpy.utils.unregister_class(IKPanel)
    bpy.utils.unregister_class(ExportPanel)
