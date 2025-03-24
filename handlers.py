import bpy
from bpy.app.handlers import persistent
from .utils import is_bizarre_armature, ik_maps, build_ik_map, is_auto_posing_bone, apply_visual_transform, toggle_ik

ignoreDepsgraphUpdate = False
previous_is_manipulated = False

def fetch_constraints_from_reference(reference_armature, target_armature, bone_name):
    """Fetch constraints from the reference armature and apply them to the target armature's bone."""
    ref_bone = reference_armature.pose.bones.get(bone_name)
    target_bone = target_armature.pose.bones.get(bone_name)    

    if not ref_bone or not target_bone:
        return

    # Remove existing constraints from the target bone
    while target_bone.constraints:
        target_bone.constraints.remove(target_bone.constraints[0])

    # Copy constraints from the reference bone
    for ref_constraint in ref_bone.constraints:
        new_constraint = target_bone.constraints.new(type=ref_constraint.type)
        for attr in dir(ref_constraint):
            if not attr.startswith("_") and hasattr(new_constraint, attr):
                try:
                    setattr(new_constraint, attr, getattr(ref_constraint, attr))
                except AttributeError:
                    pass

        # Update target to point to the target armature
        if hasattr(new_constraint, "target"):
            new_constraint.target = target_armature

        # A lazy fix for a case when reference armature uses empty objects for autoposing targets instead of bones.
        # I've updated main armature to use bones, but I don't want to update the reference armature.
        if hasattr(new_constraint, "subtarget") and ref_constraint.target and not isinstance(ref_constraint.target.data, bpy.types.Armature):
            new_constraint.subtarget = f"Bip01 {ref_constraint.target.name}"

def apply_quaternion_from_reference(reference_armature, target_armature, bone_name):
    """Apply quaternion rotation from the reference armature to the target armature's bone."""
    ref_bone = reference_armature.pose.bones.get(bone_name)
    target_bone = target_armature.pose.bones.get(bone_name)

    if ref_bone and target_bone:
        target_bone.rotation_quaternion = ref_bone.rotation_quaternion

@persistent
def check_manipulation(scene, depsgraph):
    global previous_is_manipulated, ignoreDepsgraphUpdate

    if ignoreDepsgraphUpdate:
        return

    wm = bpy.context.window_manager
    armature = bpy.context.object

    # Do nothing if "This Rig is Bizarre" is OFF
    if not is_bizarre_armature(armature):
        return
    
    # Collect IK chain bones
    if armature not in ik_maps:
        build_ik_map(armature)

    reference_armature = bpy.data.objects.get("Autopose Reference Armature")

    if armature and armature.type == 'ARMATURE':
        is_manipulated = False

        # Check if any transform operator is active
        for w in wm.windows:
            for operator in w.modal_operators:
                if operator.bl_idname in {'TRANSFORM_OT_translate', 'TRANSFORM_OT_rotate', 'TRANSFORM_OT_resize'}:
                    is_manipulated = True


    
        # Ensure that autopose bones cant be manipulated
        if is_manipulated:
            reference_armature = bpy.data.objects.get("Autopose Reference Armature")
            if not reference_armature:
                return

            selected_bones = bpy.context.selected_pose_bones
            if not selected_bones:
                return

            for bone in selected_bones:
                if bone.bone.auto_posing and is_auto_posing_bone(bone):
                    # Reset the bone's rotation using the reference armature
                    apply_quaternion_from_reference(reference_armature, armature, bone.name)
                    # Display an error message
                    """ bpy.ops.object.mode_set(mode='OBJECT')  # Temporarily switch to object mode to display the error
                    bpy.ops.object.mode_set(mode='POSE')   # Switch back to pose mode
                    bpy.context.window_manager.popup_menu(
                        lambda self, context: self.layout.label(text="Disable auto-posing before manipulation"),
                        title="Error",
                        icon='ERROR'
                    ) """
                    # print(f"Manipulation prevented for auto-posing bone: {bone.name}")

        # Handle ghost bones during manipulation
        # This is a very sneaky way to sometimes force blender to not break in dependency cycles
        # the ghost bone always closely follows the parent, but during manipulation (when all complicated autoposing is active)
        # it is snapped to parent via python instead, without the use of constraint. This migh help blender not break down parts of the
        # armature/mesh due to constraint dependency cycles.
        for bone in armature.pose.bones:
            if bone.name.startswith("[Ghost] "):  # Check if the bone is a ghost bone
                target_bone_name = bone.name.replace("[Ghost] ", "")
                target_bone = armature.pose.bones.get(target_bone_name)

                if is_manipulated:
                    # Remove child-of constraint from the ghost bone
                    for constraint in bone.constraints:
                        if constraint.type == 'CHILD_OF':
                            bone.constraints.remove(constraint)
                            # print(f"Removed child-of constraint from ghost bone '{bone.name}'")

                    # Snap ghost bone's position to the target bone's position
                    if target_bone:
                        bone.matrix = target_bone.matrix
                        # print(f"Snapped ghost bone '{bone.name}' to target bone '{target_bone_name}'")

        # Only proceed if the manipulation state has changed
        if is_manipulated != previous_is_manipulated:
            previous_is_manipulated = is_manipulated

            if not is_manipulated:
                # Handle ghost bones when manipulation ends                
                for bone in armature.pose.bones:
                    if bone.name.startswith("[Ghost] "):  # Check if the bone is a ghost bone
                        target_bone_name = bone.name.replace("[Ghost] ", "")
                        target_bone = armature.pose.bones.get(target_bone_name)

                        # Snap ghost bone's position to the target bone's position
                        if target_bone:
                            bone.matrix = target_bone.matrix
                            # print(f"Snapped ghost bone '{bone.name}' to target bone '{target_bone_name}'")

                        # Re-add child-of constraint to the ghost bone
                        if target_bone:
                            child_of_constraint = bone.constraints.new(type='CHILD_OF')
                            child_of_constraint.target = armature
                            child_of_constraint.subtarget = target_bone.name
                            # print(f"Re-added child-of constraint to ghost bone '{bone.name}' targeting '{target_bone_name}'")

                # Collect all bones that need their transforms applied
                bones_to_apply = []

                # Collect auto-posing bones
                if reference_armature:
                    bones_to_apply.extend([
                        bone for bone in armature.pose.bones
                        if bone.bone.auto_posing and is_auto_posing_bone(bone)
                    ])
                

                for ik_data in ik_maps.get(armature, {}).values():
                    ik_target_bone = ik_data['target_bone']
                    chain_bones = ik_data['chain_bones']

                    if ik_target_bone.bone.mode == 'MIXED_KINEMATICS':
                        bones_to_apply.extend(chain_bones)

                # Apply visual transform to all collected bones
                # print("Applying all visual transforms")
                apply_visual_transform(bones_to_apply)

                # Handle auto-posing bones
                for bone in bones_to_apply:
                    if bone.bone.auto_posing and is_auto_posing_bone(bone):
                        # Remove constraints from the bone
                        while bone.constraints:
                            bone.constraints.remove(bone.constraints[0])

                # Handle IK chains
                for ik_data in ik_maps.get(armature, {}).values():
                    ik_target_bone = ik_data['target_bone']
                    if ik_target_bone.bone.mode == 'MIXED_KINEMATICS':
                        toggle_ik(ik_data, False)

            else:
                # Handle Auto-Posing bones during manipulation
                if reference_armature:
                    for bone in armature.pose.bones:
                        if bone.bone.auto_posing and is_auto_posing_bone(bone):
                            # Add constraints from the reference armature
                            fetch_constraints_from_reference(reference_armature, armature, bone.name)

                            # Fetch quaternion rotation from the reference armature
                            apply_quaternion_from_reference(reference_armature, armature, bone.name)

                # Handle IK chains during manipulation
                for ik_data in ik_maps.get(armature, {}).values():
                    ik_constraint_bone = ik_data['constraint_bone']
                    ik_target_bone = ik_data['target_bone']
                    leaf_bone = ik_data['leaf_bone']

                    if ik_target_bone.bone.mode == 'MIXED_KINEMATICS':
                        toggle_ik(ik_data, True)




def register():
    if not check_manipulation in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(check_manipulation)  # Register handler
    

def unregister():
    if check_manipulation in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(check_manipulation)  # Unregister handler



