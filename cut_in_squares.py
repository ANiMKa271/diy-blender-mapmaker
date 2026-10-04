bl_info = {
    "name": "World Grid Cutter & UV Projector",
    "author": "Gemini",
    "version": (1, 3),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar (N) > Tool > Grid Cutter",
    "description": "Cuts mesh into world-grid squares and projects UVs to 0-1 bounds.",
    "category": "Mesh",
}

import bpy
import bmesh
import math
from mathutils import Vector

# ------------------------------------------------------------------------
#    Operator 1: Cut ALL (Object Mode or Edit Mode)
# ------------------------------------------------------------------------
class MESH_OT_GridCut(bpy.types.Operator):
    """Cut entire mesh into grid squares and project UVs"""
    bl_idname = "mesh.world_grid_cut"
    bl_label = "Cut & UV All"
    bl_options = {'REGISTER', 'UNDO'}

    grid_size: bpy.props.FloatProperty(name="Grid Size", default=1.0, min=0.01)
    cut_x: bpy.props.BoolProperty(name="Cut X Axis", default=True)
    cut_y: bpy.props.BoolProperty(name="Cut Y Axis", default=True)
    cut_z: bpy.props.BoolProperty(name="Cut Z Axis", default=True)
    project_uvs: bpy.props.BoolProperty(name="Project UVs to 0-1", default=True)

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        
        mode_orig = obj.mode
        if mode_orig != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
            
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.transform(obj.matrix_world)
        
        if not bm.verts:
            bm.free()
            return {'CANCELLED'}
            
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zs = [v.co.z for v in bm.verts]
        
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)
        
        def bisect_axis(min_val, max_val, axis_vector, size):
            start = math.floor(min_val / size) * size
            end = math.ceil(max_val / size) * size
            steps = int(round((end - start) / size))
            
            for i in range(1, steps):
                current_pos = start + (i * size)
                geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
                co = Vector((0, 0, 0))
                
                if axis_vector.x: co.x = current_pos
                if axis_vector.y: co.y = current_pos
                if axis_vector.z: co.z = current_pos
                
                bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=axis_vector, clear_inner=False, clear_outer=False)

        if self.cut_x: bisect_axis(min_x, max_x, Vector((1, 0, 0)), self.grid_size)
        if self.cut_y: bisect_axis(min_y, max_y, Vector((0, 1, 0)), self.grid_size)
        if self.cut_z: bisect_axis(min_z, max_z, Vector((0, 0, 1)), self.grid_size)

        if self.project_uvs:
            uv_layer = bm.loops.layers.uv.verify()
            for face in bm.faces:
                nx, ny, nz = face.normal
                ax, ay, az = abs(nx), abs(ny), abs(nz)
                loop_uvs = []
                for loop in face.loops:
                    co = loop.vert.co
                    if az >= ax and az >= ay:
                        u, v = co.x, (co.y if nz > 0 else -co.y)
                    elif ay >= ax and ay >= az:
                        u, v = (co.x if ny > 0 else -co.x), co.z
                    else:
                        u, v = (-co.y if nx > 0 else co.y), co.z
                    u /= self.grid_size
                    v /= self.grid_size
                    loop_uvs.append((loop, u, v))
                    
                min_u = min([item[1] for item in loop_uvs])
                min_v = min([item[2] for item in loop_uvs])
                offset_u = math.floor(round(min_u, 5))
                offset_v = math.floor(round(min_v, 5))
                
                for loop, u, v in loop_uvs:
                    loop[uv_layer].uv = (u - offset_u, v - offset_v)
            
        bm.transform(obj.matrix_world.inverted())
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        
        if mode_orig != 'OBJECT':
            bpy.ops.object.mode_set(mode=mode_orig)
            
        self.report({'INFO'}, f"Cut and projected all to {self.grid_size}m bounds.")
        return {'FINISHED'}

# ------------------------------------------------------------------------
#    Operator 2: Cut SELECTED (Edit Mode Only)
# ------------------------------------------------------------------------
class MESH_OT_GridCutSelected(bpy.types.Operator):
    """Cut ONLY selected faces into grid squares and project UVs"""
    bl_idname = "mesh.world_grid_cut_selected"
    bl_label = "Cut & UV Selected"
    bl_options = {'REGISTER', 'UNDO'}

    grid_size: bpy.props.FloatProperty(name="Grid Size", default=1.0, min=0.01)
    cut_x: bpy.props.BoolProperty(name="Cut X Axis", default=True)
    cut_y: bpy.props.BoolProperty(name="Cut Y Axis", default=True)
    cut_z: bpy.props.BoolProperty(name="Cut Z Axis", default=True)
    project_uvs: bpy.props.BoolProperty(name="Project UVs to 0-1", default=True)

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH' and context.active_object.mode == 'EDIT'

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        
        # Safely get or create a custom data layer to tag selected faces
        tag_layer = bm.faces.layers.int.get("grid_cut_tag")
        if tag_layer is None:
            tag_layer = bm.faces.layers.int.new("grid_cut_tag")
            
        selected_count = 0
        
        for f in bm.faces:
            if f.select:
                f[tag_layer] = 1
                selected_count += 1
            else:
                f[tag_layer] = 0
                
        if selected_count == 0:
            self.report({'WARNING'}, "No faces selected.")
            return {'CANCELLED'}
            
        bm.transform(obj.matrix_world)
        
        # Get bounding box of ONLY the tagged faces
        tagged_verts = [v for f in bm.faces if f[tag_layer] == 1 for v in f.verts]
        xs = [v.co.x for v in tagged_verts]
        ys = [v.co.y for v in tagged_verts]
        zs = [v.co.z for v in tagged_verts]
        
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)
        
        def bisect_axis_selected(min_val, max_val, axis_vector, size):
            start = math.floor(min_val / size) * size
            end = math.ceil(max_val / size) * size
            steps = int(round((end - start) / size))
            
            for i in range(1, steps):
                current_pos = start + (i * size)
                
                # Gather only geometry that stems from tagged faces
                geom_set = set()
                for f in bm.faces:
                    if f[tag_layer] == 1:
                        geom_set.add(f)
                        geom_set.update(f.edges)
                        geom_set.update(f.verts)
                
                if not geom_set:
                    continue
                    
                co = Vector((0, 0, 0))
                if axis_vector.x: co.x = current_pos
                if axis_vector.y: co.y = current_pos
                if axis_vector.z: co.z = current_pos
                
                # Bisect plane copies custom layer tags to the newly created split faces
                bmesh.ops.bisect_plane(bm, geom=list(geom_set), plane_co=co, plane_no=axis_vector, clear_inner=False, clear_outer=False)

        if self.cut_x: bisect_axis_selected(min_x, max_x, Vector((1, 0, 0)), self.grid_size)
        if self.cut_y: bisect_axis_selected(min_y, max_y, Vector((0, 1, 0)), self.grid_size)
        if self.cut_z: bisect_axis_selected(min_z, max_z, Vector((0, 0, 1)), self.grid_size)

        if self.project_uvs:
            uv_layer = bm.loops.layers.uv.verify()
            for face in bm.faces:
                if face[tag_layer] != 1: 
                    continue # Skip unselected faces
                    
                nx, ny, nz = face.normal
                ax, ay, az = abs(nx), abs(ny), abs(nz)
                loop_uvs = []
                for loop in face.loops:
                    co = loop.vert.co
                    if az >= ax and az >= ay:
                        u, v = co.x, (co.y if nz > 0 else -co.y)
                    elif ay >= ax and ay >= az:
                        u, v = (co.x if ny > 0 else -co.x), co.z
                    else:
                        u, v = (-co.y if nx > 0 else co.y), co.z
                    u /= self.grid_size
                    v /= self.grid_size
                    loop_uvs.append((loop, u, v))
                    
                min_u = min([item[1] for item in loop_uvs])
                min_v = min([item[2] for item in loop_uvs])
                offset_u = math.floor(round(min_u, 5))
                offset_v = math.floor(round(min_v, 5))
                
                for loop, u, v in loop_uvs:
                    loop[uv_layer].uv = (u - offset_u, v - offset_v)
            
        bm.transform(obj.matrix_world.inverted())
        
        # Ensure all newly split geometry remains selected in the viewport
        for f in bm.faces:
            f.select = (f[tag_layer] == 1)
        for e in bm.edges:
            e.select = any(f.select for f in e.link_faces)
        for v in bm.verts:
            v.select = any(f.select for f in v.link_faces)
            
        bmesh.update_edit_mesh(obj.data)
        
        self.report({'INFO'}, f"Cut and projected selected to {self.grid_size}m bounds.")
        return {'FINISHED'}

# ------------------------------------------------------------------------
#    UI Panel
# ------------------------------------------------------------------------
class VIEW3D_PT_GridCutPanel(bpy.types.Panel):
    bl_label = "Grid Cutter"
    bl_idname = "VIEW3D_PT_grid_cut"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        
        # Object Mode / All button
        col.operator(MESH_OT_GridCut.bl_idname, text="Cut & UV All", icon='UV_DATA')
        
        # Edit Mode / Selected button
        col.operator(MESH_OT_GridCutSelected.bl_idname, text="Cut & UV Selected", icon='RESTRICT_SELECT_OFF')


def register():
    bpy.utils.register_class(MESH_OT_GridCut)
    bpy.utils.register_class(MESH_OT_GridCutSelected)
    bpy.utils.register_class(VIEW3D_PT_GridCutPanel)

def unregister():
    bpy.utils.unregister_class(MESH_OT_GridCut)
    bpy.utils.unregister_class(MESH_OT_GridCutSelected)
    bpy.utils.unregister_class(VIEW3D_PT_GridCutPanel)

if __name__ == "__main__":
    register()