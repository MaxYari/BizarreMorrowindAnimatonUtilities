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




##### Utility Functions ################################
########################################################

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

def detect_arp_rig(obj):
    """Detect AutoRigPro-style rig by presence of c_traj bone only.
    
    A rig is considered an ARP rig if and only if it has a c_traj pose bone.
    Classic Morrowind rigs (Bip01/Khajiit/Argonian) never have c_traj, so
    no additional name-based heuristics are needed.
    """
    if not obj or obj.type != 'ARMATURE':
        return False
    return obj.pose is not None and 'c_traj' in obj.pose.bones

def iter_fcurves(action):
    # New layered system
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                if hasattr(strip, "fcurves"):
                    for fc in strip.fcurves:
                        yield fc, strip

    # Legacy fallback (just in case)
    elif hasattr(action, "fcurves"):
        for fc in action.fcurves:
            yield fc, action

def filter_action_bones(action, allowed_bones):
    to_remove = []

    for fcurve, owner in iter_fcurves(action):
        data_path = fcurve.data_path

        bone_name = None
        if 'pose.bones["' in data_path:
            bone_name = data_path.split('"')[1]

        if bone_name and bone_name not in allowed_bones:
            to_remove.append((fcurve, owner))

    # Remove after iteration (important)
    for fcurve, owner in to_remove:
        try:
            if hasattr(owner, "fcurves"):
                owner.fcurves.remove(fcurve)
        except Exception as e:
            print(f"DEBUG: Failed to remove fcurve {fcurve}: {e}")

def set_interpolation_to_linear(action):
    """Set all keyframe interpolations to linear for a given action."""
    for fcurve, owner in iter_fcurves(action):    
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = 'LINEAR'


def get_action_frame_range(action):
    """Return (start_frame, end_frame) or None if no animation."""
    if not action:
        return None

    # Prefer curve-based range (actual keyframes)
    if hasattr(action, "curve_frame_range"):
        start, end = action.curve_frame_range
        if start != end:
            return int(start), int(end)

    # Fallback (may include manual frame range)
    if hasattr(action, "frame_range"):
        start, end = action.frame_range
        if start != end:
            return int(start), int(end)

    return None


def bake_action_on_armature(start_frame, end_frame):
    """Bake pose and object keyframes for the currently active armature, clearing constraints."""
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
    bpy.ops.nla.bake(
        frame_start=start_frame,
        frame_end=end_frame,
        only_selected=False,
        visual_keying=True,
        clear_constraints=True,
        clear_parents=False,
        use_current_action=True,
        bake_types={'OBJECT'}
    )


def prepare_action_for_export(obj, report=None):
    """Prepare an action for export: preserve [Baked] and bake [Raw] to [Baked][Temp]."""
    def report_error(message):
        if report:
            report({'ERROR'}, message)
        else:
            print(f"ERROR: {message}")

    if not obj.animation_data or not obj.animation_data.action:
        report_error("No animation action found on the current object.")
        return None, None, None

    original_action = obj.animation_data.action
    original_action_name = original_action.name

    if "[Baked]" in original_action_name:
        target_name = f"[Baked][Temp] {remove_tags(original_action_name)}"
        purge_action_by_name(target_name)
        temp_action = original_action.copy()
        temp_action.name = target_name
        obj.animation_data.action = temp_action
        obj.animation_data.action_slot = temp_action.slots[0]

        frame_range = get_action_frame_range(temp_action)
        if not frame_range:
            report_error(f"Action '{original_action_name}' has no keyframes. Cannot export an empty action.")
            return None, None, None

        bpy.context.scene.frame_start, bpy.context.scene.frame_end = frame_range
        return temp_action, frame_range, False

    if not has_raw_tag(original_action_name):
        report_error("The action must start with the '[Raw]' tag to proceed.")
        return None, None, None

    target_name = original_action_name.replace('[Raw]', '[Baked][Temp]')
    purge_action_by_name(target_name)
    temp_action = original_action.copy()
    temp_action.name = target_name
    obj.animation_data.action = temp_action
    obj.animation_data.action_slot = temp_action.slots[0]

    frame_range = get_action_frame_range(temp_action)
    if not frame_range:
        report_error(f"Action '{original_action_name}' has no keyframes. Cannot export an empty action.")
        return None, None, None

    bpy.context.scene.frame_start, bpy.context.scene.frame_end = frame_range
    start_frame, end_frame = frame_range

    bake_action_on_armature(start_frame, end_frame)
    set_interpolation_to_linear(temp_action)
    copy_pose_markers(original_action, temp_action)

    return temp_action, frame_range, True


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


def remove_object_safe(obj):
    """Remove an object from the scene if it still exists in bpy.data.objects."""
    if obj is not None and obj.name in bpy.data.objects:
        bpy.data.objects.remove(obj, do_unlink=True)


def purge_action_by_name(name):
    """Remove an existing action by name to prevent Blender auto-appending .001 suffixes."""
    existing = bpy.data.actions.get(name)
    if existing:
        bpy.data.actions.remove(existing)


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
    print(f"DEBUG: Finding morrowind rig for arp_rig: {arp_rig.name}")
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            print(f"DEBUG: Checking armature: {obj.name}")
            if (obj.name.startswith('Bip01') or obj.name.startswith('Bip01.')):
                print(f"DEBUG: {obj.name} starts with Bip01")
                if obj.pose.bones:
                    first_bone = obj.pose.bones[0]
                    for constraint in first_bone.constraints:
                        print(f"DEBUG: Constraint target: {constraint.target.name if constraint.target else 'None'}")
                        if constraint.target == arp_rig:
                            print(f"DEBUG: Found morrowind_rig: {obj.name}")
                            return obj
    print("DEBUG: No morrowind rig found")
    return None


def duplicate_rig_setup(morrowind_rig):
    """
    Duplicate the Morrowind rig (without meshes, to avoid unnecessary duplication).
    Returns the duplicated Morrowind rig.
    """
    print(f"DEBUG: Duplicating {morrowind_rig.name}")
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    morrowind_rig.select_set(True)
    bpy.context.view_layer.objects.active = morrowind_rig
    bpy.ops.object.duplicate_move()
    
    duplicated_morrowind = bpy.context.active_object
    print(f"DEBUG: Duplicated obj is {duplicated_morrowind.name}")
    
    return duplicated_morrowind




### ARP Rig Baker ################################################################
##################################################################################

def prepare_arp_rig_for_export(arp_rig, report=None, use_root_motion=False):
    """
    Prepare an AutoRig Pro rig for export by:
    1. Validating all prerequisites (fails fast, no side effects)
    2. Duplicating the Morrowind rig controlled by the ARP rig
    3. Baking the animation onto the duplicate

    All validation is done before duplicating, so this function either returns a
    ready-to-use duplicate or None — it never creates a duplicate that needs cleanup
    on failure. The caller is responsible for removing the returned object when done.

    Args:
        arp_rig: The ARP rig armature object to prepare
        report: Optional report callback function for error messages (e.g., self.report)
        use_root_motion: Whether to bake c_traj object-level root motion onto the duplicate
    """
    def report_error(message):
        if report:
            report({'ERROR'}, message)
        else:
            print(f"ERROR: {message}")

    print(f"DEBUG: prepare_arp_rig_for_export called with arp_rig: {arp_rig.name if arp_rig else 'None'}")

    # --- Validation (all checks before any scene mutation) ---

    if not detect_arp_rig(arp_rig):
        report_error(f"The selected object '{arp_rig.name}' does not look like an ARP rig (c_traj not found).")
        return None

    morrowind_rig = find_morrowind_rig_controlled_by(arp_rig)
    if not morrowind_rig:
        report_error(
            f"Could not find a Morrowind rig (armature starting with 'Bip01') controlled by '{arp_rig.name}'. "
            "Ensure the first bone of your Morrowind rig has a constraint targeting this ARP rig."
        )
        return None

    if not arp_rig.animation_data or not arp_rig.animation_data.action:
        report_error(
            f"ARP rig '{arp_rig.name}' has no active animation action. "
            "Make sure an action is assigned to the armature."
        )
        return None

    original_action = arp_rig.animation_data.action
    original_action_name = original_action.name

    if not has_raw_tag(original_action_name):
        report_error(
            f"ARP workflow requires the action name to include '[Raw]'. Found '{original_action_name}'. Aborting."
        )
        return None

    frame_range = get_action_frame_range(original_action)
    if not frame_range:
        report_error(
            f"Action '{original_action_name}' on '{arp_rig.name}' has no keyframes. "
            "Cannot bake an empty action."
        )
        return None

    # use_root_motion requires c_traj — verify it exists before duplicating anything
    if use_root_motion and not arp_rig.pose.bones.get('c_traj'):
        report_error("Root motion is enabled but c_traj bone was not found on the ARP rig. Aborting export.")
        return None

    # --- All checks passed. Scene mutations begin here ---

    start_frame, end_frame = frame_range
    bpy.context.scene.frame_start = start_frame
    bpy.context.scene.frame_end = end_frame

    duplicated_morrowind = duplicate_rig_setup(morrowind_rig)

    # Select the duplicate as the active object for baking
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    duplicated_morrowind.select_set(True)
    bpy.context.view_layer.objects.active = duplicated_morrowind

    # Add the root motion constraint if requested; it gets cleared by bake_action_on_armature
    # (clear_constraints=True) so no manual removal is needed
    if use_root_motion:
        rm_constraint = duplicated_morrowind.constraints.new('COPY_LOCATION')
        rm_constraint.name = 'BizarreRM_CopyLocation_c_traj'
        rm_constraint.target = arp_rig
        rm_constraint.subtarget = 'c_traj'
        rm_constraint.owner_space = 'WORLD'
        rm_constraint.target_space = 'WORLD'

    bake_action_on_armature(start_frame, end_frame)

    baked_action = duplicated_morrowind.animation_data.action
    target_name = original_action_name.replace('[Raw]', '[Baked][Temp]')
    purge_action_by_name(target_name)
    baked_action.name = target_name
    copy_pose_markers(original_action, baked_action)

    bpy.ops.object.mode_set(mode='OBJECT')

    print(f"DEBUG: prepare_arp_rig_for_export returning: {duplicated_morrowind.name}")
    return duplicated_morrowind





### Main Operators (Smooooth operator) ################################################################
#######################################################################################################

class ExportAnimationOperator(bpy.types.Operator):
    bl_idname = "export.animation"
    bl_label = "Export Animation"
    bl_description = "Export the current action as a .nif/.kf file, baking and decimating keyframes"
    bl_options = {'REGISTER', 'UNDO'}

    def _expected_export_path(self, context):
        """Compute the output .nif path without mutating anything, for pre-export checks."""
        obj = context.object
        if not obj or obj.type != 'ARMATURE':
            return None
        action = obj.animation_data.action if obj.animation_data else None
        if not action:
            return None
        addon_prefs = context.preferences.addons[__package__].preferences
        action_name = sanitize_filename(remove_tags(action.name))
        return f"{addon_prefs.export_folder}{action_name}.nif"

    def draw(self, context):
        path = getattr(self, '_overwrite_path', '')
        filename = os.path.basename(path) if path else ''
        col = self.layout.column()
        col.label(text=f'"{filename}" already exists in the export folder.')
        col.label(text="Overwrite?")

    def invoke(self, context, event):
        path = self._expected_export_path(context)
        if path and os.path.isfile(path):
            self._overwrite_path = path
            return context.window_manager.invoke_props_dialog(self, title="File Exists")
        return self.execute(context)

    def execute(self, context):
        # Ensure we're in object mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Get the current object
        obj = context.object
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "No armature selected.")
            return {'CANCELLED'}

        # Remember original selection so we can restore it after export
        original_active = context.object
        original_selected = list(context.selected_objects)

        # Check if this is a Khajiit/Beast armature.
        # Evaluated on the original obj before it is potentially replaced by the ARP clone,
        # which is correct — the clone is named "Bip01.001" etc. and is never a beast rig.
        is_beast_armature = "Khajiit" in obj.name or "Argonian" in obj.name

        # Access properties from the add-on preferences
        addon_prefs = context.preferences.addons[__package__].preferences
        export_folder = addon_prefs.export_folder
        retained_extra_bones = [bone.strip() for bone in addon_prefs.retained_extra_bones.split(',')]  # Strip spaces
        export_as = addon_prefs.export_as
        use_root_motion = addon_prefs.enable_root_motion_arp

        # Check if this is an ARP rig using helper
        is_arp_rig = detect_arp_rig(obj)

        # If root motion requested but not ARP path, stop.
        if use_root_motion and not is_arp_rig:
            self.report({'ERROR'}, "Root Motion (ARP) is enabled, but selected armature is not an ARP rig with c_traj. Aborting export.")
            return {'CANCELLED'}

        # Track any cloned rig so we can guarantee cleanup in the finally block below.
        # Only set when we actually create a clone (ARP path); direct Morrowind rig exports never set this.
        cloned_rig = None

        try:
            # If ARP rig, prepare it for export (creates duplicate with baked Morrowind rig)
            if is_arp_rig:
                print(f"DEBUG: Calling prepare_arp_rig_for_export with obj: {obj.name if obj else 'None'}")
                cloned_rig = prepare_arp_rig_for_export(obj, self.report, use_root_motion=use_root_motion)
                print(f"DEBUG: prepare_arp_rig_for_export returned: {cloned_rig.name if cloned_rig else 'None'}")
                if not cloned_rig or cloned_rig.name not in bpy.data.objects:
                    self.report({'ERROR'}, "ARP rig preparation failed, or duplicated rig was removed.")
                    return {'CANCELLED'}

                # Switch to the prepared Morrowind rig for export
                obj = cloned_rig
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)

            # Determine the reference armature name.
            # Two signals both route to the Khajiit reference:
            #   - is_beast_armature: user selected the Khajiit Armature directly after TransferToBeasts
            #   - [Beast] tag on the action: safety net if the armature was renamed but the action wasn't
            if export_as == '1ST_PERSON':
                reference_armature_name = "1st Person Reference Armat"
            elif export_as == '3RD_PERSON':
                action_is_beast = (obj.animation_data and obj.animation_data.action
                                   and "[Beast]" in obj.animation_data.action.name)
                if is_beast_armature or action_is_beast:
                    reference_armature_name = "3rd Person Khajiit Reference Armature"
                else:
                    reference_armature_name = "3rd Person Reference Armat"
            else:
                self.report({'ERROR'}, f"Unknown export_as value '{export_as}'. Cannot determine reference armature.")
                return {'CANCELLED'}

            # Get the current object and its action
            temp_action, frame_range, baked = prepare_action_for_export(obj, self.report)
            if not temp_action:
                return {'CANCELLED'}

            # Load the reference armature
            reference_armature = load_object_from_blend(refArmaturesFilePath, reference_armature_name)
            if not reference_armature:
                self.report({'ERROR'}, f"Reference armature '{reference_armature_name}' not found in external file.")
                return {'CANCELLED'}

            try:
                # Filter bones based on the reference armature
                reference_bone_names = {bone.name for bone in reference_armature.data.bones}
                filter_action_bones(temp_action, reference_bone_names)

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

        finally:
            # Always clean up the cloned Morrowind rig regardless of success or failure.
            # Skipped entirely when exporting directly from a Morrowind rig (cloned_rig stays None).
            remove_object_safe(cloned_rig)

            # Restore original armature selection regardless of success or failure.
            bpy.ops.object.select_all(action='DESELECT')
            for o in original_selected:
                if o and o.name in bpy.data.objects:
                    o.select_set(True)
            if original_active and original_active.name in bpy.data.objects:
                bpy.context.view_layer.objects.active = original_active

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
        
        # Capture original action for later use
        original_action = obj.animation_data.action if obj.animation_data else None
        original_action_name = original_action.name if original_action else ""
        
        # Detect if this is an ARP rig (c_traj bone present)
        is_arp_rig = detect_arp_rig(obj)

        # Track any cloned rig so we can guarantee cleanup in the finally block below.
        cloned_rig = None

        try:
            # If ARP rig, prepare it for export (creates duplicate with baked Morrowind rig)
            if is_arp_rig:
                cloned_rig = prepare_arp_rig_for_export(obj, self.report)
                if not cloned_rig:
                    return {'CANCELLED'}
                
                # Switch to the prepared Morrowind rig for transfer
                obj = cloned_rig
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
            
            # Verify the armature is a Morrowind rig (starts with Bip01)
            if not (obj.name.startswith('Bip01') or obj.name.startswith('Bip01.')):
                self.report({'ERROR'}, "Selected armature must be a Morrowind rig (name starting with 'Bip01') or an ARP rig controlling one.")
                return {'CANCELLED'}
            
            temp_action, frame_range, baked = prepare_action_for_export(obj, self.report)
            if not temp_action:
                return {'CANCELLED'}

            start_frame, end_frame = frame_range
            cloned_action = temp_action

            
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

        finally:
            # Always clean up the cloned Morrowind rig regardless of success or failure.
            # Skipped entirely when transferring directly from a Morrowind rig (cloned_rig stays None).
            remove_object_safe(cloned_rig)

        self.report({'INFO'}, "Transfer to Beasts completed successfully.")
        return {'FINISHED'}