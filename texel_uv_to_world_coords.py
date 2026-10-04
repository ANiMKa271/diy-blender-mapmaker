import bpy
import bmesh
from mathutils import Vector

bl_info = {
    "name": "Texel's UV to World Coordinate",
    "author": "Vibecoded",
    "version": (1, 3, 0),
    "blender": (3, 0, 0),
    "location": "3D View Sidebar > 'Texel's UV to World Coordinate' Tab",
    "description": "Aligns selected face UVs to world coordinates and target meter scale with Triplanar projection.",
    "category": "UV",
}

def calc_face_tangents(face, uv_layer, matrix_world):
    """
    Computes world-space tangent (U) and bitangent (V) vectors for a face.
    Returns (length_T, length_B, 3d_area).
    """
    loops = face.loops
    if len(loops) < 3:
        return 0.0, 0.0, 0.0

    verts_world = [matrix_world @ v.co for v in face.verts]
    area_3d = 0.0
    v0 = verts_world[0]
    for i in range(1, len(verts_world) - 1):
        v1 = verts_world[i]
        v2 = verts_world[i + 1]
        area_3d += (v1 - v0).cross(v2 - v0).length * 0.5

    if area_3d <= 1e-8:
        return 0.0, 0.0, 0.0

    p0 = matrix_world @ loops[0].vert.co
    p1 = matrix_world @ loops[1].vert.co
    p2 = matrix_world @ loops[2].vert.co

    uv0 = loops[0][uv_layer].uv
    uv1 = loops[1][uv_layer].uv
    uv2 = loops[2][uv_layer].uv

    e1 = p1 - p0
    e2 = p2 - p0

    du1 = uv1.x - uv0.x
    dv1 = uv1.y - uv0.y
    du2 = uv2.x - uv0.x
    dv2 = uv2.y - uv0.y

    det = (du1 * dv2) - (du2 * dv1)
    if abs(det) <= 1e-8:
        return 0.0, 0.0, area_3d

    inv_det = 1.0 / det
    tangent = (e1 * dv2 - e2 * dv1) * inv_det
    bitangent = (e2 * du1 - e1 * du2) * inv_det

    return tangent.length, bitangent.length, area_3d


def apply_triplanar_projection(selected_faces, uv_layer, matrix_world, target_scale):
    """Projects world X, Y, Z coordinates onto UV space based on face normals."""
    rotation_matrix = matrix_world.to_3x3()

    for face in selected_faces:
        normal_world = (rotation_matrix @ face.normal).normalized()
        nx, ny, nz = abs(normal_world.x), abs(normal_world.y), abs(normal_world.z)

        for loop in face.loops:
            v_world = matrix_world @ loop.vert.co

            # Dominant X-axis (Sides / YZ Plane)
            if nx >= ny and nx >= nz:
                u = v_world.y / target_scale
                v = v_world.z / target_scale
                if normal_world.x < 0:
                    u = -u

            # Dominant Y-axis (Front/Back / XZ Plane)
            elif ny >= nx and ny >= nz:
                u = v_world.x / target_scale
                v = v_world.z / target_scale
                if normal_world.y < 0:
                    u = -u

            # Dominant Z-axis (Top/Bottom / XY Plane)
            else:
                u = v_world.x / target_scale
                v = v_world.y / target_scale
                if normal_world.z < 0:
                    v = -v

            loop[uv_layer].uv = Vector((u, v))


class UV_OT_AlignOneMeter(bpy.types.Operator):
    """Scale or project selected face UVs based on target meter scale settings"""
    bl_idname = "uv.align_one_meter"
    bl_label = "Align UVs to Target Scale"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        target_scale = scene.texel_target_scale
        preserve_aspect = scene.texel_preserve_aspect
        mode = scene.texel_mode
        pivot = scene.texel_pivot

        obj = context.active_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        uv_layer = bm.loops.layers.uv.verify()

        selected_faces = [f for f in bm.faces if f.select]
        if not selected_faces:
            self.report({'WARNING'}, "No faces selected!")
            return {'CANCELLED'}

        matrix_world = obj.matrix_world

        # Triplanar Projection Mode
        if mode == 'TRIPLANAR':
            apply_triplanar_projection(selected_faces, uv_layer, matrix_world, target_scale)
            bmesh.update_edit_mesh(me)
            self.report({'INFO'}, f"Applied Triplanar Mapping ({target_scale}m world scale)")
            return {'FINISHED'}

        # Fit Square per Face Mode
        if mode == 'FIT_SQUARE_PER_FACE':
            corners = [Vector((0.0, 0.0)), Vector((1.0, 0.0)), Vector((1.0, 1.0)), Vector((0.0, 1.0))]
            for face in selected_faces:
                loops = face.loops
                if len(loops) == 4:
                    for i, loop in enumerate(loops):
                        loop[uv_layer].uv = corners[i]
                else:
                    for i, loop in enumerate(loops):
                        loop[uv_layer].uv = Vector(((i % 2), ((i // 2) % 2)))
            bmesh.update_edit_mesh(me)
            self.report({'INFO'}, f"Fit {len(selected_faces)} faces to full [0,1] UV square.")
            return {'FINISHED'}

        # Mode: SCALE_LAYOUT
        total_weight = 0.0
        weighted_len_u = 0.0
        weighted_len_v = 0.0

        for f in selected_faces:
            len_u, len_v, area = calc_face_tangents(f, uv_layer, matrix_world)
            if area > 1e-8 and len_u > 1e-8 and len_v > 1e-8:
                weighted_len_u += len_u * area
                weighted_len_v += len_v * area
                total_weight += area

        if total_weight <= 1e-8 or weighted_len_u <= 1e-8 or weighted_len_v <= 1e-8:
            self.report({'WARNING'}, "Selected faces have zero UV or 3D area. Please Unwrap faces first (press U > Unwrap).")
            return {'CANCELLED'}

        avg_len_u = weighted_len_u / total_weight
        avg_len_v = weighted_len_v / total_weight

        scale_u = avg_len_u / target_scale
        scale_v = avg_len_v / target_scale

        if preserve_aspect:
            avg_scale = (scale_u + scale_v) * 0.5
            scale_u = avg_scale
            scale_v = avg_scale

        # Pivot Calculation
        if pivot == 'SELECTION_CENTER':
            pivot_point = Vector((0.0, 0.0))
            count = 0
            for f in selected_faces:
                for loop in f.loops:
                    pivot_point += loop[uv_layer].uv
                    count += 1
            if count > 0:
                pivot_point /= count
        else:
            pivot_point = Vector((0.0, 0.0))

        # Apply Scaling
        for f in selected_faces:
            for loop in f.loops:
                uv = loop[uv_layer].uv
                uv.x = pivot_point.x + (uv.x - pivot_point.x) * scale_u
                uv.y = pivot_point.y + (uv.y - pivot_point.y) * scale_v

        bmesh.update_edit_mesh(me)
        self.report({'INFO'}, f"Aligned UVs ({target_scale}m = 1.0 UV space | U scale: {scale_u:.3f}, V scale: {scale_v:.3f})")
        return {'FINISHED'}


class VIEW3D_PT_TexelsUVWorld(bpy.types.Panel):
    bl_label = "Texel's World UV Settings"
    bl_idname = "VIEW3D_PT_texels_uv_world"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Texel's UV to World Coordinate"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        box = layout.box()
        box.label(text="Parameters", icon='PROPERTIES')
        box.prop(scene, "texel_target_scale")
        box.prop(scene, "texel_mode")

        if scene.texel_mode == 'SCALE_LAYOUT':
            box.prop(scene, "texel_preserve_aspect")
            box.prop(scene, "texel_pivot")

        layout.separator()
        layout.operator("uv.align_one_meter", text="Align / Project Selected UVs", icon='UV')


def menu_func(self, context):
    self.layout.operator("uv.align_one_meter", text="Texel's UV to World Coordinate")


classes = (
    UV_OT_AlignOneMeter,
    VIEW3D_PT_TexelsUVWorld,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.texel_target_scale = bpy.props.FloatProperty(
        name="Target Scale",
        description="Target size in meters that maps to 1.0 UV space (1.0 = 1m x 1m)",
        default=1.0,
        min=0.001,
        soft_max=100.0,
        unit='LENGTH'
    )

    bpy.types.Scene.texel_preserve_aspect = bpy.props.BoolProperty(
        name="Preserve Aspect Ratio",
        description="When disabled, scales U and V independently based on face width & height",
        default=False
    )

    bpy.types.Scene.texel_mode = bpy.props.EnumProperty(
        name="Mode",
        description="Method to align or project UVs",
        items=[
            ('SCALE_LAYOUT', "Scale Existing Layout", "Scales current UV layout so target meters map to 1 UV unit"),
            ('TRIPLANAR', "Triplanar Projection", "Projects world X, Y, Z coordinates directly onto UVs seamlessly"),
            ('FIT_SQUARE_PER_FACE', "Fit Square per Face", "Stretches each individual face to fill the full [0,1] UV bounds"),
        ],
        default='SCALE_LAYOUT'
    )

    bpy.types.Scene.texel_pivot = bpy.props.EnumProperty(
        name="Pivot Point",
        description="Center point for UV scaling",
        items=[
            ('SELECTION_CENTER', "Selection Center", "Scale outward from selection center"),
            ('ORIGIN', "UV Origin (0,0)", "Scale outward from lower-left UV origin"),
        ],
        default='SELECTION_CENTER'
    )

    bpy.types.VIEW3D_MT_uv_map.append(menu_func)
    bpy.types.IMAGE_MT_uvs.append(menu_func)


def unregister():
    bpy.types.IMAGE_MT_uvs.remove(menu_func)
    bpy.types.VIEW3D_MT_uv_map.remove(menu_func)

    del bpy.types.Scene.texel_target_scale
    del bpy.types.Scene.texel_preserve_aspect
    del bpy.types.Scene.texel_mode
    del bpy.types.Scene.texel_pivot

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()