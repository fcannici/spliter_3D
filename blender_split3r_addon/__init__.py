bl_info = {
    "name": "Split3r Blender Prototype",
    "author": "Split3r / Threadwell",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Split3r",
    "description": "Prototype face-selection and plug/socket extraction using Blender's mesh and boolean tools.",
    "category": "Mesh",
}

import math
from collections import deque

import bpy
import bmesh
from bpy.props import BoolProperty, FloatProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector


class Split3rSettings(PropertyGroup):
    smart_angle: FloatProperty(
        name="Smart angle",
        description="Maximum angle in degrees between neighboring face normals for shell selection",
        default=30.0,
        min=1.0,
        max=90.0,
    )
    plug_depth: FloatProperty(
        name="Plug thickness",
        description="Solidify thickness for the extracted plug/cutter in Blender units",
        default=2.0,
        min=0.05,
        max=100.0,
        unit="LENGTH",
    )
    socket_clearance: FloatProperty(
        name="Socket clearance",
        description="Extra cutter thickness for the socket boolean",
        default=0.15,
        min=0.0,
        max=10.0,
        unit="LENGTH",
    )
    apply_boolean: BoolProperty(
        name="Apply boolean",
        description="Apply the boolean modifier immediately. Disable to inspect the cutter/modifier first",
        default=False,
    )
    keep_cutter: BoolProperty(
        name="Keep cutter",
        description="Keep the hidden cutter object after socket generation",
        default=True,
    )


def _ensure_mesh_object(context):
    obj = context.object
    if obj is None or obj.type != "MESH":
        raise RuntimeError("Seleccioná un objeto de malla.")
    return obj


def _selected_face_indices(obj):
    mode = obj.mode
    if mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    indices = [poly.index for poly in obj.data.polygons if poly.select]
    if mode != "OBJECT":
        bpy.ops.object.mode_set(mode=mode)
    return indices


def _mesh_from_faces(source_obj, face_indices, name):
    src = source_obj.data
    face_set = set(face_indices)
    vertex_map = {}
    vertices = []
    faces = []

    for poly in src.polygons:
        if poly.index not in face_set:
            continue
        face = []
        for vid in poly.vertices:
            if vid not in vertex_map:
                vertex_map[vid] = len(vertices)
                vertices.append(src.vertices[vid].co.copy())
            face.append(vertex_map[vid])
        if len(face) >= 3:
            faces.append(face)

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    obj.matrix_world = source_obj.matrix_world.copy()
    bpy.context.collection.objects.link(obj)
    return obj


def _add_solidify(obj, thickness, name="Split3r Solidify"):
    mod = obj.modifiers.new(name, "SOLIDIFY")
    mod.thickness = thickness
    mod.offset = 0.0
    mod.use_quality_normals = True
    mod.use_even_offset = True
    mod.use_rim_only = False
    mod.show_on_cage = True
    return mod


class SPLIT3R_OT_smart_shell_select(Operator):
    bl_idname = "split3r.smart_shell_select"
    bl_label = "Smart Shell Select"
    bl_description = "Flood-select neighboring faces by normal-angle tolerance from the active face"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = _ensure_mesh_object(context)
        settings = context.scene.split3r_settings
        if obj.mode != "EDIT":
            bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")

        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        active = bm.select_history.active
        if not isinstance(active, bmesh.types.BMFace):
            selected = [face for face in bm.faces if face.select]
            if not selected:
                self.report({"ERROR"}, "Seleccioná una cara semilla en Edit Mode.")
                return {"CANCELLED"}
            active = selected[-1]

        max_angle = math.radians(settings.smart_angle)
        visited = {active}
        queue = deque([active])
        active.select_set(True)

        while queue:
            face = queue.popleft()
            for edge in face.edges:
                for neighbor in edge.link_faces:
                    if neighbor is face or neighbor in visited:
                        continue
                    if face.normal.angle(neighbor.normal, 0.0) <= max_angle:
                        neighbor.select_set(True)
                        visited.add(neighbor)
                        queue.append(neighbor)

        bmesh.update_edit_mesh(obj.data)
        self.report({"INFO"}, f"Smart Shell: {len(visited)} caras seleccionadas.")
        return {"FINISHED"}


class SPLIT3R_OT_create_plug_socket(Operator):
    bl_idname = "split3r.create_plug_socket"
    bl_label = "Create Plug + Socket"
    bl_description = "Create a solidified plug from selected faces and a Blender Boolean socket on the original object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        source = _ensure_mesh_object(context)
        settings = context.scene.split3r_settings
        face_indices = _selected_face_indices(source)
        if not face_indices:
            self.report({"ERROR"}, "No hay caras seleccionadas.")
            return {"CANCELLED"}

        bpy.ops.object.mode_set(mode="OBJECT")
        source.select_set(True)
        context.view_layer.objects.active = source

        plug = _mesh_from_faces(source, face_indices, f"{source.name}_Split3r_Plug")
        _add_solidify(plug, settings.plug_depth, "Split3r Plug Thickness")

        # Cutter is a separate solidified copy. Slightly thicker than plug for socket clearance.
        cutter = plug.copy()
        cutter.data = plug.data.copy()
        cutter.name = f"{source.name}_Split3r_Socket_Cutter"
        cutter.data.name = f"{source.data.name}_Split3r_Socket_CutterMesh"
        context.collection.objects.link(cutter)
        cutter.modifiers.clear()
        _add_solidify(cutter, settings.plug_depth + settings.socket_clearance, "Split3r Socket Cutter Thickness")
        cutter.display_type = "WIRE"
        cutter.hide_render = True
        cutter.hide_viewport = False

        bool_mod = source.modifiers.new("Split3r Socket Boolean", "BOOLEAN")
        bool_mod.operation = "DIFFERENCE"
        bool_mod.object = cutter
        bool_mod.solver = "EXACT"

        if settings.apply_boolean:
            context.view_layer.objects.active = source
            try:
                bpy.ops.object.modifier_apply(modifier=bool_mod.name)
                if not settings.keep_cutter:
                    bpy.data.objects.remove(cutter, do_unlink=True)
            except Exception as exc:
                self.report({"WARNING"}, f"Boolean creado pero no se pudo aplicar: {exc}")

        plug.select_set(True)
        source.select_set(True)
        context.view_layer.objects.active = plug
        self.report({"INFO"}, "Plug/socket creado con Solidify + Boolean EXACT. Revisá el cutter antes de aplicar si hace falta.")
        return {"FINISHED"}


class SPLIT3R_OT_export_selected_stl(Operator):
    bl_idname = "split3r.export_selected_stl"
    bl_label = "Export Selected STL"
    bl_description = "Export selected Blender objects to STL"
    bl_options = {"REGISTER"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH", default="split3r_export.stl")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        selected = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if not selected:
            self.report({"ERROR"}, "Seleccioná al menos una malla para exportar.")
            return {"CANCELLED"}
        if hasattr(bpy.ops.wm, "stl_export"):
            bpy.ops.wm.stl_export(filepath=self.filepath, export_selected_objects=True)
        else:
            bpy.ops.export_mesh.stl(filepath=self.filepath, use_selection=True)
        return {"FINISHED"}


class SPLIT3R_PT_panel(Panel):
    bl_label = "Split3r"
    bl_idname = "SPLIT3R_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Split3r"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.split3r_settings

        layout.label(text="1) Selección")
        layout.prop(settings, "smart_angle")
        layout.operator("split3r.smart_shell_select", icon="RESTRICT_SELECT_OFF")

        layout.separator()
        layout.label(text="2) Plug / Socket")
        layout.prop(settings, "plug_depth")
        layout.prop(settings, "socket_clearance")
        layout.prop(settings, "apply_boolean")
        layout.prop(settings, "keep_cutter")
        layout.operator("split3r.create_plug_socket", icon="MOD_BOOLEAN")

        layout.separator()
        layout.label(text="3) Export")
        layout.operator("split3r.export_selected_stl", icon="EXPORT")


_CLASSES = (
    Split3rSettings,
    SPLIT3R_OT_smart_shell_select,
    SPLIT3R_OT_create_plug_socket,
    SPLIT3R_OT_export_selected_stl,
    SPLIT3R_PT_panel,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.split3r_settings = PointerProperty(type=Split3rSettings)


def unregister():
    if hasattr(bpy.types.Scene, "split3r_settings"):
        del bpy.types.Scene.split3r_settings
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
