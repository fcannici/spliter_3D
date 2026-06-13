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
import os
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from zipfile import ZipFile

import bpy
import bmesh
from bpy.props import BoolProperty, FloatProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector


class Split3rSettings(PropertyGroup):
    smart_angle: FloatProperty(
        name="Smart angle",
        description="Maximum angle in degrees against the seed face normal",
        default=18.0,
        min=1.0,
        max=90.0,
    )
    smart_step_angle: FloatProperty(
        name="Step angle",
        description="Maximum angle in degrees between each face and its direct neighbor",
        default=10.0,
        min=1.0,
        max=60.0,
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
    save_imported_stl: BoolProperty(
        name="Save STL copy",
        description="After importing a 3MF, also save an STL copy next to the source file",
        default=False,
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


def _parse_3mf_transform(value: str | None):
    if not value:
        return None
    try:
        nums = [float(item) for item in value.split()]
    except ValueError:
        return None
    if len(nums) != 12:
        return None
    # 3MF stores a 3x4 row-major matrix. The last three values are translation in most
    # Bambu/Prusa project files. We apply full affine transform to be safe.
    return nums


def _apply_3mf_transform(point, transform):
    if transform is None:
        return point
    x, y, z = point
    return (
        x * transform[0] + y * transform[3] + z * transform[6] + transform[9],
        x * transform[1] + y * transform[4] + z * transform[7] + transform[10],
        x * transform[2] + y * transform[5] + z * transform[8] + transform[11],
    )


def _load_3mf_meshes(filepath):
    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    meshes = []
    with ZipFile(filepath) as archive:
        names = archive.namelist()
        root_transform = None
        if "3D/3dmodel.model" in names:
            root = ET.fromstring(archive.read("3D/3dmodel.model"))
            build_item = root.find(".//m:build/m:item", ns)
            if build_item is not None:
                root_transform = _parse_3mf_transform(build_item.attrib.get("transform"))

        model_names = [name for name in names if name.lower().endswith(".model") and name.startswith("3D/Objects/")]
        if not model_names and "3D/3dmodel.model" in names:
            model_names = ["3D/3dmodel.model"]

        for model_name in model_names:
            root = ET.fromstring(archive.read(model_name))
            for obj in root.findall(".//m:object", ns):
                mesh_node = obj.find("m:mesh", ns)
                if mesh_node is None:
                    continue
                verts_node = mesh_node.find("m:vertices", ns)
                tris_node = mesh_node.find("m:triangles", ns)
                if verts_node is None or tris_node is None:
                    continue
                vertices = []
                for vertex in verts_node.findall("m:vertex", ns):
                    point = (
                        float(vertex.attrib.get("x", "0")),
                        float(vertex.attrib.get("y", "0")),
                        float(vertex.attrib.get("z", "0")),
                    )
                    vertices.append(_apply_3mf_transform(point, root_transform))
                faces = []
                for tri in tris_node.findall("m:triangle", ns):
                    try:
                        faces.append([int(tri.attrib["v1"]), int(tri.attrib["v2"]), int(tri.attrib["v3"])])
                    except (KeyError, ValueError):
                        continue
                if vertices and faces:
                    meshes.append((model_name, vertices, faces))
    return meshes


def _export_object_stl(obj, filepath):
    bpy.ops.object.mode_set(mode="OBJECT")
    for item in bpy.context.scene.objects:
        item.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if hasattr(bpy.ops.wm, "stl_export"):
        bpy.ops.wm.stl_export(filepath=filepath, export_selected_objects=True)
    else:
        bpy.ops.export_mesh.stl(filepath=filepath, use_selection=True)


class SPLIT3R_OT_import_3mf(Operator, ImportHelper):
    bl_idname = "split3r.import_3mf"
    bl_label = "Import 3MF"
    bl_description = "Import a 3MF/Bambu project directly as Blender mesh and optionally save an STL copy"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".3mf"
    filter_glob: StringProperty(default="*.3mf", options={"HIDDEN"})

    def execute(self, context):
        settings = context.scene.split3r_settings
        try:
            meshes = _load_3mf_meshes(self.filepath)
        except Exception as exc:
            self.report({"ERROR"}, f"No se pudo leer el 3MF: {exc}")
            return {"CANCELLED"}
        if not meshes:
            self.report({"ERROR"}, "El 3MF no contiene mallas compatibles.")
            return {"CANCELLED"}

        created = []
        base = Path(self.filepath).stem
        for index, (_model_name, vertices, faces) in enumerate(meshes, start=1):
            name = base if len(meshes) == 1 else f"{base}_{index}"
            mesh = bpy.data.meshes.new(f"{name}_mesh")
            mesh.from_pydata(vertices, [], faces)
            mesh.update(calc_edges=True)
            obj = bpy.data.objects.new(name, mesh)
            context.collection.objects.link(obj)
            created.append(obj)

        for obj in context.scene.objects:
            obj.select_set(False)
        for obj in created:
            obj.select_set(True)
        context.view_layer.objects.active = created[0]

        if settings.save_imported_stl:
            stl_path = os.path.splitext(self.filepath)[0] + ".stl"
            _export_object_stl(created[0], stl_path)
            self.report({"INFO"}, f"3MF importado y STL guardado: {stl_path}")
        else:
            self.report({"INFO"}, f"3MF importado: {sum(len(obj.data.polygons) for obj in created)} caras.")
        return {"FINISHED"}


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

        seed_normal = active.normal.copy()
        max_seed_angle = math.radians(settings.smart_angle)
        max_step_angle = math.radians(settings.smart_step_angle)
        visited = {active}
        queue = deque([active])
        active.select_set(True)

        while queue:
            face = queue.popleft()
            for edge in face.edges:
                # Only cross real manifold edges. This avoids jumping across non-manifold/internal
                # Bambu surfaces that touch at a boundary or duplicated shell.
                if len(edge.link_faces) != 2:
                    continue
                for neighbor in edge.link_faces:
                    if neighbor is face or neighbor in visited:
                        continue
                    if neighbor.normal.angle(seed_normal, 0.0) > max_seed_angle:
                        continue
                    if face.normal.angle(neighbor.normal, 0.0) > max_step_angle:
                        continue
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

        layout.label(text="1) Import")
        layout.prop(settings, "save_imported_stl")
        layout.operator("split3r.import_3mf", icon="IMPORT")

        layout.separator()
        layout.label(text="2) Selección")
        layout.prop(settings, "smart_angle")
        layout.prop(settings, "smart_step_angle")
        layout.operator("split3r.smart_shell_select", icon="RESTRICT_SELECT_OFF")

        layout.separator()
        layout.label(text="3) Plug / Socket")
        layout.prop(settings, "plug_depth")
        layout.prop(settings, "socket_clearance")
        layout.prop(settings, "apply_boolean")
        layout.prop(settings, "keep_cutter")
        layout.operator("split3r.create_plug_socket", icon="MOD_BOOLEAN")

        layout.separator()
        layout.label(text="4) Export")
        layout.operator("split3r.export_selected_stl", icon="EXPORT")


_CLASSES = (
    Split3rSettings,
    SPLIT3R_OT_import_3mf,
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
