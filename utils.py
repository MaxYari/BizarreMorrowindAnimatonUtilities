import bpy
import json

_SCENE_KEY = "bizarre_bone_groups"


def _load_groups():
    """Load bone groups from the current scene's custom property."""
    scene = bpy.context.scene
    raw = scene.get(_SCENE_KEY)
    if not raw:
        return {}
    try:
        # Keys are stored as strings in JSON; convert back to int
        return {int(k): v for k, v in json.loads(raw).items()}
    except (ValueError, TypeError):
        return {}


def _save_groups(groups):
    """Persist bone groups into the current scene's custom property."""
    bpy.context.scene[_SCENE_KEY] = json.dumps(groups)


def assign_bone_group(group_number):
    """Assign selected bones to a group and persist to scene."""
    selected_bones = [bone.name for bone in bpy.context.selected_pose_bones]
    groups = _load_groups()
    groups[group_number] = selected_bones
    _save_groups(groups)
    print(f"Assigned bones to group {group_number}: {selected_bones}")


def select_bone_group(group_number):
    """Select bones from a previously assigned group."""
    groups = _load_groups()
    if group_number in groups:
        bpy.ops.pose.select_all(action='DESELECT')
        for bone_name in groups[group_number]:
            pose_bone = bpy.context.object.pose.bones.get(bone_name)
            if pose_bone:
                if hasattr(pose_bone, 'select'):      # Blender 5.1+
                    pose_bone.select = True
                else:                                  # Blender 4.x
                    pose_bone.bone.select = True
        print(f"Selected bones from group {group_number}: {groups[group_number]}")
    else:
        print(f"No bones assigned to group {group_number}")
