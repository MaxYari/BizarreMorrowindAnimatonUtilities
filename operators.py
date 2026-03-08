import bpy
from .utils import assign_bone_group, select_bone_group
from .exporter import ExportAnimationOperator, TransferToBeastsOperator

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

def register():
    bpy.utils.register_class(AssignBoneGroupOperator)
    bpy.utils.register_class(SelectBoneGroupOperator)
    bpy.utils.register_class(ExportAnimationOperator)
    bpy.utils.register_class(TransferToBeastsOperator)
    bpy.utils.register_class(MuteConstraintsOperator)
    bpy.utils.register_class(RestoreConstraintsOperator)

def unregister():
    bpy.utils.unregister_class(SelectBoneGroupOperator)
    bpy.utils.unregister_class(AssignBoneGroupOperator)
    bpy.utils.unregister_class(ExportAnimationOperator)
    bpy.utils.unregister_class(TransferToBeastsOperator)
    bpy.utils.unregister_class(MuteConstraintsOperator)
    bpy.utils.unregister_class(RestoreConstraintsOperator)
