import bpy

# Predefined lists of bones
limb_ik_bones = ["Bip01 Forearm.L", "Bip01 Forearm.R", "Bip01 Calf.L", "Bip01 Calf.R"]

upper_body_autopose_bones = ["Bip01 Spine1", "Bip01 Spine2", "Bip01 Clavicle.L", "Bip01 Clavicle.R"]
lower_body_autopose_bones = ["Bip01 Pelvis"]
all_autopose_bones = upper_body_autopose_bones + lower_body_autopose_bones

# Shared data
ik_target_to_autopose_map = {
    "Bip01 Arm IK Target.L": upper_body_autopose_bones,
    "Bip01 Arm IK Target.R": upper_body_autopose_bones,
    "Bip01 Leg IK Target.L": lower_body_autopose_bones,
    "Bip01 Leg IK Target.R": lower_body_autopose_bones,
}

bone_groups = {}

# Module-level variable to store IK maps
ik_maps = {}

def is_bizarre_armature(armature):
    """Check if the given armature contains the 'Bip01 Bizarre Bone' bone."""
    if armature and armature.type == 'ARMATURE':
        return "Bip01 Bizarre Bone" in armature.data.bones
    return False


def find_ik_chain_data(armature, bone):
    """Find IK chain data for a given bone in the armature."""
    if armature not in ik_maps:
        build_ik_map(armature)

    ik_map = ik_maps.get(armature)
    if ik_map:
        for ik_data in ik_map.values():
            if bone in ik_data['bones']:
                return ik_data
    return None

def insert_keyframes_for_bones(armature, bones, data_path="rotation_quaternion"):
    """Insert keyframes for a list of bones."""
    for bone_name in bones:
        if bone_name in armature.pose.bones:
            bone = armature.pose.bones[bone_name]
            bone.keyframe_insert(data_path)

def build_ik_map(armature):
    """Build a map of IK chains for the given armature."""
    ik_map = {}
    for bone in armature.pose.bones:
        if bone.name not in limb_ik_bones:
            continue  # Skip bones not in the predefined IK list
        for constraint in bone.constraints:
            if constraint.type == 'IK':
                chain_length = constraint.chain_count
                ik_target = constraint.target
                ik_target_bone = constraint.subtarget
                bones = []
                chain_bones = []
                current_bone = bone

                # Traverse the IK chain
                for _ in range(chain_length):
                    bones.append(current_bone)
                    chain_bones.append(current_bone)
                    current_bone = current_bone.parent
                    if not current_bone:
                        break

                # Add the IK target bone to the chain
                if ik_target and ik_target_bone:
                    target_bone = ik_target.pose.bones.get(ik_target_bone)
                    if target_bone:
                        bones.append(target_bone)

                # Find leaf bones (children with constraints targeting the IK target)
                leaf_bone = None
                for child_bone in bone.children:
                    for child_constraint in child_bone.constraints:
                        if child_constraint.subtarget == ik_target_bone:
                            bones.append(child_bone)
                            chain_bones.append(child_bone)
                            leaf_bone = child_bone
                            break

                # Store the IK chain data
                ik_map[bone.name] = {
                    "constraint_bone": bone,
                    "chain_bones": chain_bones,
                    "target_bone": target_bone,
                    "bones": bones,
                    "leaf_bone": leaf_bone,
                }

    # Update the module-level ik_maps variable
    ik_maps[armature] = ik_map

def is_ik_chain_target_bone(pose_bone):
    """Check if the given pose bone is an IK chain target."""
    armature = pose_bone.id_data
    ik_map = ik_maps.get(armature)
    if ik_map:
        for ik_data in ik_map.values():
            if pose_bone == ik_data["target_bone"]:
                return True
    return False

def is_auto_posing_bone(pose_bone):
    """Check if the given pose bone is in the autoposing bone list."""
    if pose_bone.name in all_autopose_bones:
        return True
    return False

def assign_bone_group(group_number):
    """Assign selected bones to a group."""
    selected_bones = [bone.name for bone in bpy.context.selected_pose_bones]
    bone_groups[group_number] = selected_bones
    print(f"Assigned bones to group {group_number}: {selected_bones}")

def select_bone_group(group_number):
    """Select bones from a previously assigned group."""
    if group_number in bone_groups:
        bpy.ops.pose.select_all(action='DESELECT')
        for bone_name in bone_groups[group_number]:
            bpy.context.object.data.bones[bone_name].select = True
        print(f"Selected bones from group {group_number}: {bone_groups[group_number]}")
    else:
        print(f"No bones assigned to group {group_number}")

def toggle_auto_posing(self, context):
    """Toggle the use of constraints for auto-posing bones."""
    bone = context.active_pose_bone
    if bone and is_auto_posing_bone(bone):
        armature = context.object
        update_bone_colors(armature)  # Automatically update bone colors
        #print(f"Auto-Posing toggled for {bone.name}: {bone.bone.auto_posing}")

def update_bone_colors(armature):
    """Update the colors of bones based on their auto_posing state."""
    if not armature or armature.type != 'ARMATURE':
        return
    # TO DO: Implement
    

def switch_kinematics_mode(self, context):
    """Update the kinematics mode for a bone."""
    bone = context.active_pose_bone
    if bone and is_ik_chain_target_bone(bone):
        armature = bpy.context.object
        ik_data = find_ik_chain_data(armature, bone)
        if ik_data:
            if bone.bone.mode == 'INVERSE_KINEMATICS':
                toggle_ik(ik_data, True)
            elif bone.bone.mode == 'FORWARD_KINEMATICS':
                apply_visual_transform(ik_data["chain_bones"])
                toggle_ik(ik_data, False)

def toggle_ik(ik_data, state):
    """Disable IK constraints for a given IK chain."""
    ik_constraint_bone = ik_data['constraint_bone']
    leaf_bone = ik_data['leaf_bone']
    ik_constraint_bone.constraints['IK'].mute = not state
    if leaf_bone:
        for constraint in leaf_bone.constraints:
            if constraint.subtarget == ik_data['target_bone'].name:
                constraint.mute = not state

def apply_visual_transform(pose_bones):
    global ignoreDepsgraphUpdate
    ignoreDepsgraphUpdate = True

    """  # Save current selection and visibility state
    selected_bones = [bone.name for bone in bpy.context.selected_pose_bones]
    hidden_bones = [bone for bone in pose_bones if bone.bone.hide]

    # Unhide hidden bones
    for bone in hidden_bones:
        bone.bone.hide = False

    # Deselect all bones
    bpy.ops.pose.select_all(action='DESELECT')

    # Select the bones passed to the function
    for pose_bone in pose_bones:
        pose_pone.bone.select = True

    # Apply visual transform
    bpy.ops.pose.visual_transform_apply()

    # Restore previous selection
    bpy.ops.pose.select_all(action='DESELECT')
    for bone_name in selected_bones:
        bpy.context.object.data.bones[bone_name].select = True

    # Re-hide previously hidden bones
    for bone in hidden_bones:
        bone.bone.hide = True """

    for bone in pose_bones:
        rot = get_bone_constrained_rotation(bone)
        bone.rotation_quaternion = rot

    ignoreDepsgraphUpdate = False


def get_bone_constrained_rotation(poseBone):
    # poseBone.matrix is in object space - we need to convert it to local space 
    if poseBone.parent is not None:
        parentRefPoseMtx = poseBone.parent.bone.matrix_local
        boneRefPoseMtx = poseBone.bone.matrix_local
        parentPoseMtx = poseBone.parent.matrix
        bonePoseMtx = poseBone.matrix
        boneLocMtx = ( parentRefPoseMtx.inverted() @ boneRefPoseMtx ).inverted() @ ( parentPoseMtx.inverted() @ bonePoseMtx )
    else:
        boneRefPoseMtx = poseBone.bone.matrix_local
        bonePoseMtx = poseBone.matrix
        boneLocMtx = boneRefPoseMtx.inverted() @ bonePoseMtx

    loc, rot, scale = boneLocMtx.decompose()    
    return rot
