import bpy
import re
import os

# Authors: ChatGPT 4.o and Maksim Eremenko
# A one-click stop to exporting current action into a .nif/.kf files.
# Bakes, decimates and exports the current action into the specified location
# Non-destructive, all processing will be done in a copy of a current action
# Requires current action's name to start with "[Raw]". Example:
# For an action "[Raw] My Fancy Anim" - will create a "[Baked] My Fancy Anim" action
# and export it to your specified location as a set of MyFancyAnim.nif/.kf files

refArmaturesFilePath = os.path.join(os.path.dirname(__file__), "morrowind_reference_armatures.blend")

def sanitize_filename(filename):
    """Remove invalid characters and whitespace from the filename."""
    return re.sub(r'[^\w\-_.]', '', filename.replace(" ", ""))

def has_raw_tag(action_name):
    """Check if the action name contains the '[Raw]' tag."""
    return '[Raw]' in action_name

def replace_raw_with_baked(action_name):
    """Replace 'Raw' with 'Baked' in the action name."""
    return action_name.replace('[Raw]', '[Baked]')

def remove_tags(action_name):
    """Remove any '[tag]' from the action name."""
    return re.sub(r'\[.*?\]', '', action_name)

def set_interpolation_to_linear(action):
    """Set all keyframe interpolations to linear for a given action."""
    for fcurve in action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = 'LINEAR'

def load_object_from_blend(filepath, object_name):
    """Load an object from an external .blend file and add it to the current scene, ignoring objects starting with 'Tri Shadow'."""
    if object_name.startswith("Tri Shadow"):
        return None  # Ignore objects starting with "Tri Shadow"

    with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
        if object_name in data_from.objects:
            data_to.objects.append(object_name)
    
    obj = bpy.data.objects.get(object_name)
    if obj:
        existing_obj = bpy.context.scene.collection.objects.get(object_name)
        if existing_obj:
            bpy.data.objects.remove(existing_obj, do_unlink=True)
        # Add object to scene    
        bpy.context.scene.collection.objects.link(obj)
    
    return obj

def load_objects_from_blend_bulk(filepath, object_names):
    """Load multiple objects from an external .blend file, link them to the scene, and clean up unlinked objects, ignoring objects starting with 'Tri Shadow'."""
    loaded_objects = {}

    # Load all objects from the external file
    with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
        data_to.objects = [name for name in data_from.objects if not name.startswith("Tri Shadow")]

    # Store loaded objects in a dictionary
    # Outside of loading context data_to.objects becomes a list of objects
    for obj in data_to.objects:            
        if obj:  # Ensure the object is not None
            loaded_objects[obj.name] = obj

    # Link the desired object and its children to the scene
    def link_to_scene(obj):
        """Recursively link an object and its children to the scene."""
        existing_obj = bpy.context.scene.collection.objects.get(obj.name)
        if existing_obj:            
            bpy.data.objects.remove(existing_obj, do_unlink=True)
        # Add object to scene    
        bpy.context.scene.collection.objects.link(obj)
        
        for child in obj.children:
            link_to_scene(child)

    root_objects = []
    for object_name in object_names:
        if object_name.startswith("Tri Shadow"):
            continue  # Ignore objects starting with "Tri Shadow"
        root_obj = loaded_objects.pop(object_name, None)
        if root_obj:
            link_to_scene(root_obj)
            root_objects.append(root_obj)

    # Clean up unlinked objects
    for obj_name, obj in loaded_objects.items():
        if obj and obj.users == 0:  # If the object is not linked to any scene or collection
            bpy.data.objects.remove(obj, do_unlink=True)

    return root_objects

def remove_object_from_scene(object_name):
    """Remove an object from the scene if it exists."""
    obj = bpy.data.objects.get(object_name)
    if obj:
        bpy.data.objects.remove(obj, do_unlink=True)


def copy_pose_markers(source_action, target_action):
    """Copy all pose markers from source action to target action."""
    if not source_action or not target_action:
        return
    if source_action.pose_markers:
        for marker in source_action.pose_markers:
            new_marker = target_action.pose_markers.new(name=marker.name)
            new_marker.frame = marker.frame


def find_morrowind_rig_controlled_by(arp_rig):
    """
    Find the Morrowind rig (armature starting with 'Bip01') that is controlled by the given ARP rig.
    Checks if the first bone of each Bip01 armature has a constraint targeting the ARP rig.
    Returns the Morrowind rig object or None if not found.
    """
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE' and (obj.name.startswith('Bip01') or obj.name.startswith('Bip01.')):
            # Check the first bone's constraints
            if obj.pose.bones:
                first_bone = obj.pose.bones[0]
                for constraint in first_bone.constraints:
                    if constraint.target == arp_rig:
                        return obj
    return None


def duplicate_rig_setup(source_armature):
    """
    Duplicate the entire rig setup: the given armature, any controlled Morrowind rig, and attached meshes.
    Returns a tuple: (duplicated_main_armature, duplicated_morrowind_rig_or_none, duplicated_meshes_list)
    """
    # Find the Morrowind rig controlled by this armature (if any)
    morrowind_rig = find_morrowind_rig_controlled_by(source_armature)
    
    # Find all meshes that are children of either armature
    meshes_to_duplicate = []
    for child in source_armature.children:
        if child.type == 'MESH':
            meshes_to_duplicate.append(child)
    if morrowind_rig:
        for child in morrowind_rig.children:
            if child.type == 'MESH' and child not in meshes_to_duplicate:
                meshes_to_duplicate.append(child)
    
    # Select all objects to duplicate
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    
    objects_to_duplicate = [source_armature]
    if morrowind_rig:
        objects_to_duplicate.append(morrowind_rig)
    objects_to_duplicate.extend(meshes_to_duplicate)
    
    for obj in objects_to_duplicate:
        obj.select_set(True)
    
    # Duplicate
    bpy.ops.object.duplicate_move()
    
    # Get the duplicated objects (they are now selected and active)
    duplicated_objects = list(bpy.context.selected_objects)
    
    # Find which duplicated object corresponds to which original
    duplicated_main = None
    duplicated_morrowind = None
    duplicated_meshes = []
    
    for dup_obj in duplicated_objects:
        # Match by original name (Blender adds .001 suffix)
        base_name = dup_obj.name.rsplit('.00', 1)[0] if '.00' in dup_obj.name else dup_obj.name
        
        if base_name == source_armature.name or dup_obj.name.startswith(source_armature.name + '.'):
            duplicated_main = dup_obj
        elif morrowind_rig and (base_name == morrowind_rig.name or dup_obj.name.startswith(morrowind_rig.name + '.')):
            duplicated_morrowind = dup_obj
        elif dup_obj.type == 'MESH':
            duplicated_meshes.append(dup_obj)
    
    return duplicated_main, duplicated_morrowind, duplicated_meshes


def prepare_arp_rig_for_export(arp_rig, report=None):
    """
    Prepare an AutoRig Pro rig for export by:
    1. Finding the controlled Morrowind rig
    2. Duplicating the entire rig setup
    3. Baking the animation on the Morrowind rig duplicate while clearing constraints
    
    Args:
        arp_rig: The ARP rig armature object to prepare
        report: Optional report callback function for error messages (e.g., self.report)
    
    Returns the duplicated Morrowind rig with baked animation, or None if preparation fails.
    """
    def report_error(message):
        if report:
            report({'ERROR'}, message)
        else:
            print(f"ERROR: {message}")
    
    # Find the Morrowind rig controlled by this ARP rig
    morrowind_rig = find_morrowind_rig_controlled_by(arp_rig)
    if not morrowind_rig:
        report_error(
            f"Could not find a Morrowind rig (armature starting with 'Bip01') controlled by '{arp_rig.name}'. "
            "Ensure the first bone of your Morrowind rig has a constraint targeting this ARP rig."
        )
        return None
    
    # Get the current action
    if not arp_rig.animation_data or not arp_rig.animation_data.action:
        report_error(
            f"ARP rig '{arp_rig.name}' has no active animation action. "
            "Make sure an action is assigned to the armature."
        )
        return None
    
    original_action = arp_rig.animation_data.action
    original_action_name = original_action.name
    
    # Duplicate the entire rig setup
    duplicated_arp, duplicated_morrowind, duplicated_meshes = duplicate_rig_setup(arp_rig)
    
    if not duplicated_morrowind:
        # Cleanup on failure
        for obj in [duplicated_arp] + duplicated_meshes:
            if obj:
                bpy.data.objects.remove(obj, do_unlink=True)
        report_error(
            f"Failed to duplicate the rig setup for '{arp_rig.name}'. "
            "Check if there are any issues with the armature or its children."
        )
        return None
    
    # Get action frame range
    keyframes = [kp.co[0] for fcurve in original_action.fcurves for kp in fcurve.keyframe_points]
    if not keyframes:
        # Cleanup on failure
        for obj in [duplicated_arp, duplicated_morrowind] + duplicated_meshes:
            if obj:
                bpy.data.objects.remove(obj, do_unlink=True)
        report_error(
            f"Action '{original_action_name}' on '{arp_rig.name}' has no keyframes. "
            "Cannot bake an empty action."
        )
        return None
    
    start_frame = int(min(keyframes))
    end_frame = int(max(keyframes))
    
    # Set frame range
    bpy.context.scene.frame_start = start_frame
    bpy.context.scene.frame_end = end_frame
    
    # Select the duplicated Morrowind rig
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    duplicated_morrowind.select_set(True)
    bpy.context.view_layer.objects.active = duplicated_morrowind
    
    # Bake the action with visual keying and clear constraints
    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.nla.bake(
        frame_start=start_frame,
        frame_end=end_frame,
        only_selected=False,
        visual_keying=True,
        clear_constraints=True,
        clear_parents=False,
        use_current_action=True,
        bake_types={'POSE'}
    )
    
    # Set interpolation to linear
    baked_action = duplicated_morrowind.animation_data.action
    if baked_action:
        set_interpolation_to_linear(baked_action)
        # Rename the baked action following naming conventions
        if '[Raw]' in original_action_name:
            baked_action.name = original_action_name.replace('[Raw]', '[Baked]')
        else:
            baked_action.name = f"[Baked] {remove_tags(original_action_name)}"
        
        # Copy pose markers from the original action to the baked action
        copy_pose_markers(original_action, baked_action)

    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Remove the duplicated ARP rig and meshes (we only need the Morrowind rig)
    if duplicated_arp:
        bpy.data.objects.remove(duplicated_arp, do_unlink=True)
    for mesh in duplicated_meshes:
        bpy.data.objects.remove(mesh, do_unlink=True)
    
    return duplicated_morrowind



class ExportAnimationOperator(bpy.types.Operator):
    bl_idname = "export.animation"
    bl_label = "Export Animation"
    bl_description = "Export the current action as a .nif/.kf file, baking and decimating keyframes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Ensure we're in object mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Get the current object
        obj = context.object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "No armature selected.")
            return {'CANCELLED'}

        # Check if this is a Khajiit/Beast armature
        is_beast_armature = "Khajiit" in obj.name or "Argonian" in obj.name
        
        # Check if this is an ARP rig (doesn't start with "Bip01" and is not a beast armature)
        is_arp_rig = not (obj.name.startswith('Bip01') or obj.name.startswith('Bip01.')) and not is_beast_armature

        # If ARP rig, prepare it for export (creates duplicate with baked Morrowind rig)
        if is_arp_rig:
            morrowind_rig = prepare_arp_rig_for_export(obj, self.report)
            if not morrowind_rig:
                return {'CANCELLED'}

            # Switch to the prepared Morrowind rig for export
            obj = morrowind_rig
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)

        # Access properties from the add-on preferences
        addon_prefs = context.preferences.addons[__package__].preferences
        export_folder = addon_prefs.export_folder
        retained_extra_bones = [bone.strip() for bone in addon_prefs.retained_extra_bones.split(',')]  # Strip spaces
        export_as = addon_prefs.export_as

        # Determine the reference armature name
        if export_as == '1ST_PERSON':
            reference_armature_name = "1st Person Reference Armat"
        elif export_as == '3RD_PERSON':
            # Use "3rd Person Khajiit Reference Armature" if the action has the [Beast] tag or if using a beast armature
            if is_beast_armature or (obj.animation_data and obj.animation_data.action and "[Beast]" in obj.animation_data.action.name):
                reference_armature_name = "3rd Person Khajiit Reference Armature"
            else:
                reference_armature_name = "3rd Person Reference Armat"

        # Get the current object and its action
        if obj.animation_data and obj.animation_data.action:
            original_action = obj.animation_data.action
            original_action_name = original_action.name

            # Check if the action is already baked
            if "[Baked]" in original_action_name:
                # Clone the action into [Baked][Temp]
                temp_action = original_action.copy()
                temp_action.name = f"[Baked][Temp] {remove_tags(original_action_name)}"
                obj.animation_data.action = temp_action
                obj.animation_data.action_slot = temp_action.slots[0]
            elif has_raw_tag(original_action_name):
                # Copy the action and rename it
                temp_action = original_action.copy()
                temp_action.name = replace_raw_with_baked(original_action_name)
                obj.animation_data.action = temp_action
                obj.animation_data.action_slot = temp_action.slots[0]

                # Get all keyframes for the action
                keyframes = [kp.co[0] for fcurve in temp_action.fcurves for kp in fcurve.keyframe_points]
                start_frame = int(min(keyframes))
                end_frame = int(max(keyframes))

                # Limit the frame range for the action
                bpy.context.scene.frame_start = start_frame
                bpy.context.scene.frame_end = end_frame

                # Bake the action with visual keying
                bpy.ops.nla.bake(frame_start=start_frame, frame_end=end_frame, only_selected=False, visual_keying=True, clear_constraints=False, clear_parents=False, use_current_action=True, bake_types={'POSE'})
                bpy.ops.nla.bake(frame_start=start_frame, frame_end=end_frame, only_selected=False, visual_keying=True, clear_constraints=False, clear_parents=False, use_current_action=True, bake_types={'OBJECT'})
                set_interpolation_to_linear(temp_action)
            else:
                self.report({'ERROR'}, "The action must start with the '[Raw]' or '[Baked]' tag. Aborting operation.")
                return {'CANCELLED'}
            

            # Load the reference armature
            reference_armature = load_object_from_blend(refArmaturesFilePath, reference_armature_name)
            if not reference_armature:
                self.report({'ERROR'}, f"Reference armature '{reference_armature_name}' not found in external file.")
                return {'CANCELLED'}

            try:
                # Filter bones based on the reference armature
                reference_bone_names = {bone.name for bone in reference_armature.data.bones}
                for fcurve in temp_action.fcurves[:]:
                    bone_name = fcurve.data_path.split('"')[1] if '"' in fcurve.data_path else None
                    if bone_name and bone_name not in reference_bone_names and bone_name not in retained_extra_bones:
                        temp_action.fcurves.remove(fcurve)

                # Apply Decimate to all keyframes using graph.decimate
                bpy.ops.object.mode_set(mode='POSE')
                bpy.ops.pose.select_all(action='SELECT')  # Select all bones in pose mode
                current_area_type = bpy.context.area.type
                bpy.context.area.type = 'GRAPH_EDITOR'
                bpy.ops.graph.select_all(action='SELECT')  # Select all keyframes in the graph editor
                bpy.ops.graph.decimate(mode='ERROR', remove_error_margin=0.000005)
                bpy.ops.object.mode_set(mode='OBJECT')
                bpy.context.area.type = current_area_type

                # Get the sanitized action name without tags
                action_name = sanitize_filename(remove_tags(temp_action.name))

                # Select the currently active armature
                current_armature = context.object
                if current_armature and current_armature.type == 'ARMATURE':
                    original_name = current_armature.name  # Save the original name
                    
                    # Determine the temp name based on armature type
                    # Beast armatures keep their name, Morrowind rigs are renamed to "Bip01"
                    is_beast = "Khajiit" in original_name or "Argonian" in original_name
                    if not is_beast and not (original_name.startswith('Bip01') or original_name.startswith('Bip01.')):
                        current_armature.name = "Bip01"  # Temporarily rename the armature

                    try:
                        bpy.context.view_layer.objects.active = current_armature
                        current_armature.select_set(True)

                        # Export the object
                        export_path = f"{export_folder}{action_name}.nif"
                        print(f"Exporting animation to: {export_path}")
                        bpy.ops.export_scene.mw(filepath=export_path, use_selection=True, export_animations=True, extract_keyframe_data=True)
                    finally:
                        # Restore the original name after export
                        current_armature.name = original_name
                else:
                    self.report({'ERROR'}, "No valid armature selected.")
                    return {'CANCELLED'}
            finally:
                # Ensure the reference armature is removed from the scene
                remove_object_from_scene(reference_armature_name)

        else:
            self.report({'ERROR'}, "No animation action found on the current object.")
            return {'CANCELLED'}

        self.report({'INFO'}, "Animation exported successfully.")
        return {'FINISHED'}

class TransferToBeastsOperator(bpy.types.Operator):
    bl_idname = "export.transfer_to_beasts"
    bl_label = "Transfer to Beasts"
    bl_description = "Retarget the current animation for beast armatures. A beast retargeting rig will be imported. You can export animation straight from the beast rig if you feel satisfied with the result."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Ensure we're in object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Get the current object
        obj = context.object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "No armature selected.")
            return {'CANCELLED'}
        
        # Check if this is an ARP rig (doesn't start with "Bip01")
        is_arp_rig = not (obj.name.startswith('Bip01') or obj.name.startswith('Bip01.'))
        
        # If ARP rig, prepare it for export (creates duplicate with baked Morrowind rig)
        if is_arp_rig:
            morrowind_rig = prepare_arp_rig_for_export(obj, self.report)
            if not morrowind_rig:
                return {'CANCELLED'}
            
            # Switch to the prepared Morrowind rig for transfer
            obj = morrowind_rig
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
        
        # Verify the armature is a Morrowind rig (starts with Bip01)
        if not (obj.name.startswith('Bip01') or obj.name.startswith('Bip01.')):
            self.report({'ERROR'}, "Selected armature must be a Morrowind rig (name starting with 'Bip01') or an ARP rig controlling one.")
            return {'CANCELLED'}
        
        # Get the current action
        if not obj.animation_data or not obj.animation_data.action:
            self.report({'ERROR'}, "No animation action found on the current object.")
            return {'CANCELLED'}
        
        original_action = obj.animation_data.action
        original_action_name = original_action.name
        
        # Handle action naming - accept both [Raw] and [Baked] tags
        if "[Baked]" in original_action_name:
            # Action is already baked, use it directly
            cloned_action = original_action
            
            # Get frame range from the existing action
            keyframes = [kp.co[0] for fcurve in cloned_action.fcurves for kp in fcurve.keyframe_points]
            if not keyframes:
                self.report({'ERROR'}, f"Action '{original_action_name}' has no keyframes. Cannot transfer an empty action.")
                return {'CANCELLED'}
            start_frame = int(min(keyframes))
            end_frame = int(max(keyframes))
        elif has_raw_tag(original_action_name):
            # Bake the action for the current object
            cloned_action = original_action.copy()
            cloned_action.name = replace_raw_with_baked(original_action_name)
            obj.animation_data.action = cloned_action
            obj.animation_data.action_slot = cloned_action.slots[0]
            
            keyframes = [kp.co[0] for fcurve in cloned_action.fcurves for kp in fcurve.keyframe_points]
            start_frame = int(min(keyframes))
            end_frame = int(max(keyframes))
            
            bpy.context.scene.frame_start = start_frame
            bpy.context.scene.frame_end = end_frame
            
            bpy.ops.nla.bake(frame_start=start_frame, frame_end=end_frame, only_selected=False, visual_keying=True, clear_constraints=False, clear_parents=False, use_current_action=True, bake_types={'POSE'})
            bpy.ops.nla.bake(frame_start=start_frame, frame_end=end_frame, only_selected=False, visual_keying=True, clear_constraints=False, clear_parents=False, use_current_action=True, bake_types={'OBJECT'})
            set_interpolation_to_linear(cloned_action)
        else:
            self.report({'ERROR'}, "The action must start with the '[Raw]' or '[Baked]' tag. Aborting operation.")
            return {'CANCELLED'}
        
        # Load related armatures
        driver_armature = bpy.data.objects.get("Khajiit Retarget Driver Armature")
        khajiit_armature = bpy.data.objects.get("Khajiit Armature")
        if not driver_armature and not khajiit_armature:
            driver_armature, khajiit_armature = load_objects_from_blend_bulk(refArmaturesFilePath, ["Khajiit Retarget Driver Armature","Khajiit Armature"])
            if not driver_armature or not khajiit_armature:
                self.report({'ERROR'}, "Driver armature 'Khajiit Retarget Driver Armature' or 'Khajiit Armature' not found in external file.")
                return {'CANCELLED'}      
        
        driver_armature.animation_data.action = cloned_action
        driver_armature.animation_data.action_slot = cloned_action.slots[0]
        
        # Set the Khajiit armature's action to "Khajiit Default Stance" if it exists
        default_stance_action = bpy.data.actions.get("Khajiit Default Stance")
        if default_stance_action:
            khajiit_armature.animation_data.action = default_stance_action
            khajiit_armature.animation_data.action_slot = default_stance_action.slots[0]
        else:
            self.report({'ERROR'}, "Can't find Khajiit Default Stance action. It should've been imported together with Khajiit armature. Can't continue.")
            return {'CANCELLED'}

        # Bake the action for the Khajiit armature
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = khajiit_armature
        khajiit_armature.select_set(True)
        bpy.ops.object.mode_set(mode='POSE')

        bpy.ops.nla.bake(frame_start=start_frame, frame_end=end_frame, only_selected=False, visual_keying=True, clear_constraints=False, clear_parents=False, use_current_action=False, bake_types={'POSE'})
        bpy.ops.nla.bake(frame_start=start_frame, frame_end=end_frame, only_selected=False, visual_keying=True, clear_constraints=False, clear_parents=False, use_current_action=True, bake_types={'OBJECT'})

        # Rename the baked action for the Khajiit armature
        baked_action = khajiit_armature.animation_data.action
        if baked_action:
            baked_action.name = f"[Baked][Beast] Beast {remove_tags(original_action_name)}"
            # Transfer markers from the original action to the baked action
            copy_pose_markers(original_action, baked_action)

        # Ensure the Khajiit armature is selected and active
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        khajiit_armature.select_set(True)
        bpy.context.view_layer.objects.active = khajiit_armature

        self.report({'INFO'}, "Transfer to Beasts completed successfully.")
        return {'FINISHED'}
