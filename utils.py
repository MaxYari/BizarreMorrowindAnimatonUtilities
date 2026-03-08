import bpy

bone_groups = {}

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
