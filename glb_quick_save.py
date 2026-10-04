# vibecoded
# saves selected object as .glb at the directory of the current .blend file
# so if you have "props" folder with "space.blend" in it and you select an object "SpaceChair" in blender, 
# then "SpaceChair.glb" will be save in "props" folder.

bl_info = {
    "name": "Godot Modular Hierarchy Export",
    "blender": (4, 0, 0),
    "category": "Import-Export",
    "author": "Gemini",
    "version": (1, 0),
}

import bpy
import os
import re

class GLBGodotHierarchyExport(bpy.types.Operator):
    bl_idname = "export.godot_hierarchy_glb"
    bl_label = "Export Hall + Children"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        parent_obj = context.active_object
        if not parent_obj:
            self.report({'WARNING'}, "Select the main Hall object")
            return {'CANCELLED'}

        # 1. Path & Naming
        base_dir = os.path.dirname(bpy.data.filepath)
        if not base_dir:
            self.report({'ERROR'}, "Save your .blend file first!")
            return {'CANCELLED'}

        # Clean the name (remove .001 or Godot suffixes from the filename only)
        clean_name = re.sub(r"(-col|-convcol|-navmesh|\.\d{3})", "", parent_obj.name, flags=re.IGNORECASE).strip()
        filepath = os.path.join(base_dir, f"{clean_name}.glb")

        # 2. Selection Logic (Select Parent + All Children)
        # We deselect everything first, then select the hierarchy
        bpy.ops.object.select_all(action='DESELECT')
        parent_obj.select_set(True)
        for child in parent_obj.children_recursive:
            child.select_set(True)
        
        # 3. Position Zeroing (Move Parent, Children follow)
        original_location = parent_obj.location.copy()
        parent_obj.location = (0, 0, 0)
        context.view_layer.update()

        # 4. Export
        try:
            bpy.ops.export_scene.gltf(
                filepath=filepath,
                export_format='GLB',
                use_selection=True,
                export_apply=True,
                export_materials='EXPORT',
                export_image_format='NONE',
                export_attributes=False
            )
            self.report({'INFO'}, f"Exported {clean_name}.glb with children")
        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
        finally:
            # 5. Restore Position
            parent_obj.location = original_location
            context.view_layer.update()

        return {'FINISHED'}

class VIEW3D_PT_GodotHierarchy(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Godot'
    bl_label = 'Godot Modular Tools'

    def draw(self, context):
        layout = self.layout
        layout.operator("export.godot_hierarchy_glb", icon='OUTLINER_OB_GROUP_INSTANCE')

def register():
    bpy.utils.register_class(GLBGodotHierarchyExport)
    bpy.utils.register_class(VIEW3D_PT_GodotHierarchy)

def unregister():
    bpy.utils.unregister_class(GLBGodotHierarchyExport)
    bpy.utils.unregister_class(VIEW3D_PT_GodotHierarchy)

if __name__ == "__main__":
    register()
