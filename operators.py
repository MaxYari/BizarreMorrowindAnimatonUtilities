import bpy
from bpy.app.handlers import persistent
from .utils import is_bizarre_armature, find_ik_chain_data, insert_keyframes_for_bones, ik_target_to_autopose_map, assign_bone_group, select_bone_group
from .exporter import ExportAnimationOperator, TransferToBeastsOperator

class AutoPoseKeyframeOperator(bpy.types.Operator):
    bl_idname = "pose.autopose_insert_keyframe"
    bl_label = "AutoPose Insert Keyframe"
    bl_description = "Automatically insert keyframes for bones based on IK chains and autopose mappings"

    def invoke(self, context, event):
        armature = context.object
        
        if not is_bizarre_armature(armature):
            return {'PASS_THROUGH'}           

        if context.mode != 'POSE' or context.area.type != 'VIEW_3D':
            return {'PASS_THROUGH'}  # Pass through the event if not in Pose Mode or 3D View

        active_bone = context.active_pose_bone

        if active_bone and active_bone.name in ik_target_to_autopose_map:
            relevant_bones = ik_target_to_autopose_map[active_bone.name]
            
            ik_data = find_ik_chain_data(armature, active_bone)
            if ik_data:
                insert_keyframes_for_bones(armature, [b.name for b in ik_data['chain_bones']])
            insert_keyframes_for_bones(armature, relevant_bones)

        return {'PASS_THROUGH'}

class AssignBoneGroupOperator(bpy.types.Operator):
    bl_idname = "pose.assign_bone_group"
    bl_label = "Assign Bone Group"
    bl_description = "Assign the selected bones to a specific bone group"
    bl_options = {'REGISTER', 'UNDO'}

    group_number: bpy.props.IntProperty()

    def execute(self, context):
        if context.mode != 'POSE' or context.area.type != 'VIEW_3D':
            return {'PASS_THROUGH'}  # Pass through the event if not in Pose Mode or 3D View

        assign_bone_group(self.group_number)
        return {'FINISHED'}

class SelectBoneGroupOperator(bpy.types.Operator):
    bl_idname = "pose.select_bone_group"
    bl_label = "Select Bone Group"
    bl_description = "Select all bones in the specified bone group"
    bl_options = {'REGISTER', 'UNDO'}

    group_number: bpy.props.IntProperty()

    def execute(self, context):
        if context.mode != 'POSE' or context.area.type != 'VIEW_3D':
            return {'PASS_THROUGH'}  # Pass through the event if not in Pose Mode or 3D View

        select_bone_group(self.group_number)
        return {'FINISHED'}

class DisableAutoPosingSelectedOperator(bpy.types.Operator):
    bl_idname = "pose.disable_autoposing_selected"
    bl_label = "Disable Auto-Posing ON/OFF for Selected Bones"
    bl_description = "Toggle auto-posing for the selected bones"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        armature = context.object
        if not is_bizarre_armature(armature):
            return {'PASS_THROUGH'}    
        
        if context.mode != 'POSE' or context.area.type != 'VIEW_3D':
            return {'PASS_THROUGH'}  # Pass through the event if not in Pose Mode or 3D View

        armature = context.object
        if armature and armature.type == 'ARMATURE':
            for bone in context.selected_pose_bones:
                if hasattr(bone.bone, "auto_posing"):
                    bone.bone.auto_posing = not bone.bone.auto_posing
        return {'FINISHED'}

class DisableAutoPosingAllOperator(bpy.types.Operator):
    bl_idname = "pose.disable_autoposing_all"
    bl_label = "Disable Auto-Posing for All Bones"
    bl_description = "Toggle auto-posing ON/OFF for all bones in the armature"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        armature = context.object
        if not is_bizarre_armature(armature):
            return {'PASS_THROUGH'}    
        
        if context.mode != 'POSE' or context.area.type != 'VIEW_3D':
            return {'PASS_THROUGH'}  # Pass through the event if not in Pose Mode or 3D View

        armature = context.object
        some_enabled = False
        if armature and armature.type == 'ARMATURE':
            for bone in armature.data.bones:
                if hasattr(bone, "auto_posing") and bone.auto_posing:
                    some_enabled = True
                    break
        
        if armature and armature.type == 'ARMATURE':
            for bone in armature.data.bones:
                if hasattr(bone, "auto_posing"):
                    if some_enabled: bone.auto_posing = False
                    else: bone.auto_posing = True
        return {'FINISHED'}

class MuteConstraintsOperator(bpy.types.Operator):
    bl_idname = "export.mute_constraints"
    bl_label = "Mute Constraints"
    bl_description = "Mute all constraints on the armature and its bones. Constraint states are saved and can be later restored. Handy to view baked/vanilla animations without constraints affecting the motion."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Active object is not an armature.")
            return {'CANCELLED'}

        # Check if constraints are already muted
        if "saved_constraints" in obj:
            self.report({'ERROR'}, "Constraints are already muted. Restore them before muting again.")
            return {'CANCELLED'}

        # Save and mute all constraints on the armature object itself
        saved_constraints = {"object_constraints": [constraint.mute for constraint in obj.constraints]}

        for constraint in obj.constraints:
            constraint.mute = True

        # Save and mute all constraints on the armature's bones
        bone_constraints = {}
        for bone in obj.pose.bones:
            bone_constraints[bone.name] = [constraint.mute for constraint in bone.constraints]
            for constraint in bone.constraints:
                constraint.mute = True

        # Store the saved constraints in the armature's custom property
        saved_constraints["bone_constraints"] = bone_constraints
        obj["saved_constraints"] = saved_constraints
        self.report({'INFO'}, "All constraints muted and states saved.")
        return {'FINISHED'}

class RestoreConstraintsOperator(bpy.types.Operator):
    bl_idname = "export.restore_constraints"
    bl_label = "Restore Constraints"
    bl_description = "Restore all previously muted constraints on the armature and its bones"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'ARMATURE' and "saved_constraints" in obj

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Active object is not an armature.")
            return {'CANCELLED'}

        if "saved_constraints" not in obj:
            self.report({'ERROR'}, "No saved constraint states to restore.")
            return {'CANCELLED'}

        # Retrieve saved constraints
        saved_constraints = obj["saved_constraints"]

        # Restore constraints on the armature object itself
        for constraint, saved_state in zip(obj.constraints, saved_constraints["object_constraints"]):
            constraint.mute = saved_state

        # Restore constraints on the armature's bones
        for bone in obj.pose.bones:
            if bone.name in saved_constraints["bone_constraints"]:
                for constraint, saved_state in zip(bone.constraints, saved_constraints["bone_constraints"][bone.name]):
                    constraint.mute = saved_state

        # Remove the saved constraints from the armature's custom property
        del obj["saved_constraints"]
        self.report({'INFO'}, "Constraints restored to their previous states.")
        return {'FINISHED'}

@persistent
def clear_ik_map_on_load(dummy):
    print("FILE LOADED")
    """Clear the IK map when a new file is loaded."""
    global ik_target_to_autopose_map
    ik_target_to_autopose_map.clear()
    print("IK map cleared on file load.")

def register():
    bpy.utils.register_class(AutoPoseKeyframeOperator)
    bpy.utils.register_class(AssignBoneGroupOperator)
    bpy.utils.register_class(SelectBoneGroupOperator)
    bpy.utils.register_class(DisableAutoPosingSelectedOperator)
    bpy.utils.register_class(DisableAutoPosingAllOperator)
    bpy.utils.register_class(ExportAnimationOperator)
    bpy.utils.register_class(TransferToBeastsOperator)
    bpy.utils.register_class(MuteConstraintsOperator)
    bpy.utils.register_class(RestoreConstraintsOperator)

    # Register the file load handler
    if clear_ik_map_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(clear_ik_map_on_load)

def unregister():
    # Unregister the file load handler
    if clear_ik_map_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(clear_ik_map_on_load)

    bpy.utils.unregister_class(DisableAutoPosingAllOperator)
    bpy.utils.unregister_class(DisableAutoPosingSelectedOperator)
    bpy.utils.unregister_class(SelectBoneGroupOperator)
    bpy.utils.unregister_class(AssignBoneGroupOperator)
    bpy.utils.unregister_class(AutoPoseKeyframeOperator)
    bpy.utils.unregister_class(ExportAnimationOperator)
    bpy.utils.unregister_class(TransferToBeastsOperator)
    bpy.utils.unregister_class(MuteConstraintsOperator)
    bpy.utils.unregister_class(RestoreConstraintsOperator)
