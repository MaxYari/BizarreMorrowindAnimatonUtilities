bl_info = {
    "name": "Bizarre Morrowind Anim Utils",
    "description": "Animation retargeting and export utilities for Morrowind",
    "author": "Maksim Eremenko",
    "version": (1, 6, 4),
    "blender": (4, 4, 0),
    "location": "View3D > UI > Bizarre Anim",
    "category": "Animation",
}

import bpy
from . import operators, panels, utils, keymaps, exporter

class BizarreAnimUtils(bpy.types.AddonPreferences):
    bl_idname = __package__

    export_folder: bpy.props.StringProperty(
        name="Export Folder",
        description="Folder where exported animations will be saved",
        default="//",
        subtype='DIR_PATH'
    )

    retained_extra_bones: bpy.props.StringProperty(
        name="Retained Extra Bones",
        description="Comma-separated list of extra bones to retain during export",
        default=""
    )

    enable_root_motion_arp: bpy.props.BoolProperty(
        name="Root Motion (ARP)",
        description=(
            "Bake root motion from the c_traj bone into the exported animation. "
            "Only works with AutoRig Pro rigs. "
            "If you have not animated c_traj manually, use AutoRig Pro's built-in "
            "'Extract Root Motion' button first to transfer hip translation onto c_traj, "
            "then export with this option enabled."
        ),
        default=False
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

    verbose_logging: bpy.props.BoolProperty(
        name="Verbose Logging",
        description="Print detailed diagnostics to the system console. Turn on when reporting a bug",
        default=False
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "export_folder")
        layout.prop(self, "retained_extra_bones")
        layout.prop(self, "export_as")
        layout.prop(self, "enable_root_motion_arp")
        layout.prop(self, "verbose_logging")

def register():
    # Preferences must exist before any panel or operator reads them.
    bpy.utils.register_class(BizarreAnimUtils)
    operators.register()
    panels.register()
    keymaps.register()


def unregister():
    # Unregister panels, operators, and keymaps first
    keymaps.unregister()
    panels.unregister()
    operators.unregister()
    bpy.utils.unregister_class(BizarreAnimUtils)

if __name__ == "__main__":
    register()
