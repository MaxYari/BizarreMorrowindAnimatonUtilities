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



class ExportAnimationOperator(bpy.types.Operator):
    bl_idname = "export.animation"
    bl_label = "Export Animation"
    bl_description = "Export the current action as a .nif/.kf file, baking and decimating keyframes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Access properties from the add-on preferences
        addon_prefs = context.preferences.addons[__package__].preferences
        export_folder = addon_prefs.export_folder
        retained_extra_bones = [bone.strip() for bone in addon_prefs.retained_extra_bones.split(',')]  # Strip spaces
        export_as = addon_prefs.export_as

        # Determine the reference armature name
        if export_as == '1ST_PERSON':
            reference_armature_name = "1st Person Reference Armat"
        elif export_as == '3RD_PERSON':
            # Use "3rd Person Khajiit Reference Armature" if the action has the [Beast] tag
            obj = context.object
            if obj.animation_data and obj.animation_data.action and "[Beast]" in obj.animation_data.action.name:
                reference_armature_name = "3rd Person Khajiit Reference Armature"
            else:
                reference_armature_name = "3rd Person Reference Armat"

        # Ensure we're in object mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Get the current object and its action
        obj = context.object
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
                self.report({'ERROR'}, "The action not start with the '[Raw]' or '[Baked]' tag. Aborting operation.")
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

                # Select the currently active armature if its name starts with "Bip01" or "Bip01."
                current_armature = context.object
                if current_armature and current_armature.type == 'ARMATURE':
                    original_name = current_armature.name  # Save the original name
                    if not (current_armature.name.startswith('Bip01') or current_armature.name.startswith('Bip01.')):
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
                    self.report({'ERROR'}, "No valid armature selected or active armature name does not start with 'Bip01' or 'Bip01.'.")
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
        # Access the current object and its action
        obj = context.object
        if not obj or not obj.animation_data or not obj.animation_data.action:
            self.report({'ERROR'}, "No animation action found on the current object.")
            return {'CANCELLED'}

        original_action = obj.animation_data.action
        original_action_name = original_action.name

        # Ensure the action has the '[Raw]' tag
        if not has_raw_tag(original_action_name):
            self.report({'ERROR'}, "The action does not contain the '[Raw]' tag. Aborting operation.")
            return {'CANCELLED'}

        # Step 1: Bake the action for the current object
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
            if original_action and original_action.pose_markers:
                for marker in original_action.pose_markers:
                    new_marker = baked_action.pose_markers.new(name=marker.name)
                    new_marker.frame = marker.frame

        # Ensure the Khajiit armature is selected and active
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        khajiit_armature.select_set(True)
        bpy.context.view_layer.objects.active = khajiit_armature

        self.report({'INFO'}, "Transfer to Beasts completed successfully.")
        return {'FINISHED'}
