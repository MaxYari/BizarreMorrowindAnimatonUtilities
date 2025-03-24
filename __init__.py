bl_info = {
    "name": "Bizarre Morrowind Anim Utils",
    "description": "Hybrid IK/FK manipulations and constrained assist for Blender",
    "author": "Maksim Eremenko",
    "version": (1, 1, 0),
    "blender": (4, 3, 0),
    "location": "View3D > UI > Bizarre Anim",
    "category": "Animation",
}

import bpy
from . import operators, panels, utils, keymaps, handlers, exporter

class BizarreAnimUtils(bpy.types.AddonPreferences):
    bl_idname = __package__

    export_folder: bpy.props.StringProperty(
        name="Export Folder",
        description="Folder where exported animations will be saved",
        default="C:/Modding/MO2/DATA/mods/Experiments/Animations/xbase_anim.1st/",
        subtype='DIR_PATH'
    )

    retained_extra_bones: bpy.props.StringProperty(
        name="Retained Extra Bones",
        description="Comma-separated list of extra bones to retain during export",
        default=""
    )

    export_as: bpy.props.EnumProperty(
        name="Export as",
        description="Select the export type",
        items=[
            ('1ST_PERSON', "1st-person", ""),
            ('3RD_PERSON', "3rd-person", "")
        ],
        default='1ST_PERSON'
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "export_folder")
        layout.prop(self, "retained_extra_bones")
        layout.prop(self, "export_as")  # Add the dropdown to the preferences UI

def register():
    operators.register()
    panels.register()
    keymaps.register()
    handlers.register()
    bpy.utils.register_class(BizarreAnimUtils)


def unregister():
    # Unregister handlers, panels, operators, and keymaps first
    keymaps.unregister()
    panels.unregister()
    operators.unregister()
    handlers.unregister()
    bpy.utils.unregister_class(BizarreAnimUtils)

    # Safely remove the "This Rig is Bizarre" property from armature objects
    if hasattr(bpy.types.Object, "bizarre_rig"):
        del bpy.types.Object.bizarre_rig

if __name__ == "__main__":
    register()
