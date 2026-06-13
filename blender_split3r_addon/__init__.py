bl_info = {
    "name": "Split3r Blender Prototype",
    "author": "Split3r / Threadwell",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Split3r",
    "description": "Prototype face-selection and plug/socket extraction using Blender's mesh and boolean tools.",
    "category": "Mesh",
}

import json
import math
import os
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from zipfile import ZipFile

import bpy
import bmesh
from bpy.props import BoolProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
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
    apply_output_modifiers: BoolProperty(
        name="Apply plug/cutter solidify",
        description="Apply Solidify on generated plug/cutter so the result is real mesh geometry for inspection/export",
        default=True,
    )
    repair_outputs: BoolProperty(
        name="Repair generated meshes",
        description="Fill remaining boundary holes and recalculate normals on generated plug/cutter meshes",
        default=True,
    )
    grow_steps: IntProperty(
        name="Grow steps",
        description="How many edge rings to add/remove with Grow/Shrink",
        default=1,
        min=1,
        max=50,
    )
    grow_use_angle_limits: BoolProperty(
        name="Angle-limited grow",
        description="When enabled, Grow uses strict Smart/Step angle limits. Keep disabled for normal Ctrl+Wheel wrapping",
        default=False,
    )
    grow_boundary_angle: FloatProperty(
        name="Grow boundary",
        description="Maximum local angle Ctrl+Wheel can cross when Angle-limited grow is disabled. Higher wraps more; lower prevents spillover",
        default=18.0,
        min=5.0,
        max=90.0,
    )
    save_imported_stl: BoolProperty(
        name="Save STL copy",
        description="After importing a 3MF, also save an STL copy next to the source file",
        default=False,
    )
    ai_test_file: StringProperty(
        name="Test file",
        description="3MF/STL file path that Threadwell should test",
        default="",
        subtype="FILE_PATH",
    )
    ai_prompt: StringProperty(
        name="Prompt",
        description="Instructions for Threadwell about what to test or fix in the add-on",
        default="Probá este archivo con el add-on Split3r en Blender y revisá importación, Smart Shell, plug/socket y export STL.",
    )
    ai_request_path: StringProperty(
        name="Request path",
        description="Where the Blender-to-Threadwell request JSON is written",
        default=str(Path.home() / "split3r_blender_request.json"),
        subtype="FILE_PATH",
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


def _repair_mesh_object(obj):
    previous_active = bpy.context.view_layer.objects.active
    previous_mode = previous_active.mode if previous_active is not None else "OBJECT"
    if previous_active is not None and previous_mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    if bm.verts:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    boundary_edges = [edge for edge in bm.edges if edge.is_boundary]
    filled = 0
    if boundary_edges:
        try:
            result = bmesh.ops.holes_fill(bm, edges=boundary_edges, sides=0)
            filled = len(result.get("faces", []))
        except Exception:
            filled = 0
    if bm.faces:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update(calc_edges=True)

    if previous_active is not None:
        bpy.context.view_layer.objects.active = previous_active
        if previous_mode != "OBJECT":
            bpy.ops.object.mode_set(mode=previous_mode)
    return {"boundary_edges_before": len(boundary_edges), "filled_faces": filled}


def _apply_modifier(obj, modifier_name):
    previous_active = bpy.context.view_layer.objects.active
    previous_mode = previous_active.mode if previous_active is not None else "OBJECT"
    if previous_active is not None and previous_mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=modifier_name)
    if previous_active is not None:
        bpy.context.view_layer.objects.active = previous_active
        if previous_mode != "OBJECT":
            bpy.ops.object.mode_set(mode=previous_mode)


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
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for item in bpy.context.scene.objects:
        item.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if hasattr(bpy.ops.wm, "stl_export"):
        bpy.ops.wm.stl_export(filepath=filepath, export_selected_objects=True)
    else:
        bpy.ops.export_mesh.stl(filepath=filepath, use_selection=True)


def _select_created_objects(context, created):
    for obj in context.scene.objects:
        obj.select_set(False)
    for obj in created:
        obj.select_set(True)
    if created:
        context.view_layer.objects.active = created[0]


def _create_mesh_objects_from_3mf(context, filepath):
    meshes = _load_3mf_meshes(filepath)
    if not meshes:
        raise RuntimeError("El 3MF no contiene mallas compatibles.")

    created = []
    base = Path(filepath).stem
    for index, (_model_name, vertices, faces) in enumerate(meshes, start=1):
        name = base if len(meshes) == 1 else f"{base}_{index}"
        mesh = bpy.data.meshes.new(f"{name}_mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update(calc_edges=True)
        obj = bpy.data.objects.new(name, mesh)
        context.collection.objects.link(obj)
        created.append(obj)
    _select_created_objects(context, created)
    return created


def _import_file_to_viewport(context, filepath, save_stl_copy=False):
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    before = set(context.scene.objects)
    ext = Path(filepath).suffix.lower()
    if ext == ".3mf":
        created = _create_mesh_objects_from_3mf(context, filepath)
        if save_stl_copy and created:
            _export_object_stl(created[0], os.path.splitext(filepath)[0] + ".stl")
        return created
    if ext == ".stl":
        if hasattr(bpy.ops.wm, "stl_import"):
            bpy.ops.wm.stl_import(filepath=filepath)
        else:
            bpy.ops.import_mesh.stl(filepath=filepath)
    elif ext == ".obj":
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=filepath)
        else:
            bpy.ops.import_scene.obj(filepath=filepath)
    else:
        raise RuntimeError(f"Formato no soportado: {ext}")
    created = [obj for obj in context.scene.objects if obj not in before]
    if not created and context.object is not None:
        created = [context.object]
    _select_created_objects(context, created)
    return created


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
            created = _import_file_to_viewport(context, self.filepath, settings.save_imported_stl)
        except Exception as exc:
            self.report({"ERROR"}, f"No se pudo importar el 3MF: {exc}")
            return {"CANCELLED"}

        if settings.save_imported_stl and created:
            stl_path = os.path.splitext(self.filepath)[0] + ".stl"
            self.report({"INFO"}, f"3MF importado y STL guardado: {stl_path}")
        else:
            self.report({"INFO"}, f"3MF importado al viewport: {sum(len(obj.data.polygons) for obj in created if obj.type == 'MESH')} caras.")
        return {"FINISHED"}


class SPLIT3R_OT_pick_ai_test_file(Operator, ImportHelper):
    bl_idname = "split3r.pick_ai_test_file"
    bl_label = "Pick + Import Test File"
    bl_description = "Choose the file path for Threadwell and import it into the Blender viewport"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".3mf"
    filter_glob: StringProperty(default="*.3mf;*.stl;*.obj", options={"HIDDEN"})

    def execute(self, context):
        settings = context.scene.split3r_settings
        settings.ai_test_file = self.filepath
        try:
            created = _import_file_to_viewport(context, self.filepath, settings.save_imported_stl)
        except Exception as exc:
            self.report({"ERROR"}, f"Ruta seleccionada, pero no se pudo importar: {exc}")
            return {"CANCELLED"}
        faces = sum(len(obj.data.polygons) for obj in created if obj.type == "MESH")
        self.report({"INFO"}, f"Archivo importado al viewport y listo para Threadwell: {faces} caras.")
        return {"FINISHED"}


class SPLIT3R_OT_write_threadwell_request(Operator):
    bl_idname = "split3r.write_threadwell_request"
    bl_label = "Send Request to Threadwell"
    bl_description = "Write a JSON request that Threadwell can read to run Blender/add-on tests"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.split3r_settings
        test_file = bpy.path.abspath(settings.ai_test_file).strip()
        if not test_file:
            self.report({"ERROR"}, "Indicá primero la ruta del archivo a probar.")
            return {"CANCELLED"}

        request_path = bpy.path.abspath(settings.ai_request_path).strip()
        if not request_path:
            request_path = str(Path.home() / "split3r_blender_request.json")

        selected_face_indices = []
        active = context.object
        if (active is None or active.type != "MESH") and Path(test_file).exists():
            try:
                created = _import_file_to_viewport(context, test_file, settings.save_imported_stl)
                active = created[0] if created else context.object
            except Exception as exc:
                self.report({"WARNING"}, f"Request guardado, pero no se pudo importar al viewport: {exc}")
                active = context.object
        if active is not None and active.type == "MESH":
            try:
                selected_face_indices = _selected_face_indices(active)
            except Exception:
                selected_face_indices = []

        request = {
            "kind": "split3r_blender_test_request",
            "version": 1,
            "test_file": test_file,
            "prompt": settings.ai_prompt,
            "smart_angle": settings.smart_angle,
            "smart_step_angle": settings.smart_step_angle,
            "plug_depth": settings.plug_depth,
            "socket_clearance": settings.socket_clearance,
            "save_imported_stl": settings.save_imported_stl,
            "blend_file": bpy.data.filepath,
            "active_object": active.name if active is not None else "",
            "selected_face_count": len(selected_face_indices),
            "selected_face_indices": selected_face_indices,
            "addon_module": "blender_split3r_addon",
        }

        try:
            Path(request_path).parent.mkdir(parents=True, exist_ok=True)
            Path(request_path).write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            self.report({"ERROR"}, f"No se pudo guardar el request: {exc}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Request para Threadwell guardado: {request_path}")
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
        active_index = active.index

        # Smart Shell is a replacement selection from the active seed face.
        # If an old overgrown selection remains selected, leaving it active makes it look
        # like the settings/script did not change because the old faces stay selected.
        grow_lock_layer = bm.faces.layers.int.get("split3r_grow_locked")
        if grow_lock_layer is None:
            grow_lock_layer = bm.faces.layers.int.new("split3r_grow_locked")
            # Adding a custom data layer can invalidate existing BMFace references.
            bm.faces.ensure_lookup_table()
            active = bm.faces[active_index]
        for face in bm.faces:
            face[grow_lock_layer] = 0
            if face is not active:
                face.select_set(False)
        active.select_set(True)

        seed_normal = active.normal.copy()
        max_seed_angle = math.radians(settings.smart_angle)
        max_step_angle = math.radians(settings.smart_step_angle)
        visited = {active}
        queue = deque([active])

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


class SPLIT3R_OT_reset_selection_settings(Operator):
    bl_idname = "split3r.reset_selection_settings"
    bl_label = "Reset Selection Settings"
    bl_description = "Restore the approved selection parameters without changing the selection algorithm"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.split3r_settings
        settings.smart_angle = 18.0
        settings.smart_step_angle = 10.0
        settings.grow_steps = 1
        settings.grow_use_angle_limits = False
        settings.grow_boundary_angle = 18.0
        obj = context.object
        if obj is not None and obj.type == "MESH" and obj.mode == "EDIT":
            bm = bmesh.from_edit_mesh(obj.data)
            layer = bm.faces.layers.int.get("split3r_grow_locked")
            if layer is not None:
                for face in bm.faces:
                    face[layer] = 0
                bmesh.update_edit_mesh(obj.data)
        self.report({"INFO"}, "Selection settings restaurados: Smart 18, Step 10, Grow 1, Boundary 18, Angle-limited OFF. Grow locks limpiados.")
        return {"FINISHED"}


class SPLIT3R_OT_grow_smart_selection(Operator):
    bl_idname = "split3r.grow_smart_selection"
    bl_label = "Grow Surface Selection"
    bl_description = "Expand the current face selection by edge rings over the connected surface"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = _ensure_mesh_object(context)
        settings = context.scene.split3r_settings
        if obj.mode != "EDIT":
            bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        grow_lock_layer = bm.faces.layers.int.get("split3r_grow_locked")
        if grow_lock_layer is None:
            grow_lock_layer = bm.faces.layers.int.new("split3r_grow_locked")
            # Adding a custom data layer can invalidate existing BMFace references.
            bm.faces.ensure_lookup_table()
        selected = {face for face in bm.faces if face.select}
        if not selected:
            self.report({"ERROR"}, "Seleccioná al menos una cara antes de ampliar.")
            return {"CANCELLED"}

        max_step_angle = math.radians(settings.smart_step_angle)
        max_seed_angle = math.radians(settings.smart_angle)
        # Hard cap for normal Ctrl+Wheel grow. Organic meshes often have smooth-looking
        # bridges where a high UI value lets selection leak into the base/body.
        effective_boundary = min(settings.grow_boundary_angle, 18.0)
        max_boundary_angle = math.radians(effective_boundary)
        avg = Vector((0.0, 0.0, 0.0))
        if settings.grow_use_angle_limits:
            for face in selected:
                avg += face.normal
            if avg.length > 0:
                avg.normalize()
            else:
                avg = next(iter(selected)).normal.copy()

        added_total = 0
        for _ in range(settings.grow_steps):
            to_add = set()
            # Performance: only boundary faces can grow. Iterating every selected face on
            # dense 3MF meshes becomes slow and feels like Ctrl+Wheel is stuck.
            boundary_faces = []
            for face in selected:
                for edge in face.edges:
                    if len(edge.link_faces) == 2 and any(neighbor not in selected for neighbor in edge.link_faces):
                        boundary_faces.append(face)
                        break
            for face in boundary_faces:
                if face[grow_lock_layer]:
                    continue
                face_reached_boundary = False
                if not settings.grow_use_angle_limits:
                    for edge in face.edges:
                        if len(edge.link_faces) != 2:
                            face_reached_boundary = True
                            break
                        for neighbor in edge.link_faces:
                            if neighbor is face or neighbor in selected:
                                continue
                            if face.normal.angle(neighbor.normal, 0.0) > max_boundary_angle:
                                face_reached_boundary = True
                                break
                        if face_reached_boundary:
                            break
                if face_reached_boundary:
                    # Persist the reached limit between Ctrl+Wheel events. Without this,
                    # the next wheel tick can continue growing around the same boundary.
                    face[grow_lock_layer] = 1
                    continue
                for edge in face.edges:
                    # Ctrl+Wheel should wrap along the same connected surface, but it must
                    # not leak through boundary/non-manifold edges or across sharp folds.
                    if len(edge.link_faces) != 2:
                        continue
                    for neighbor in edge.link_faces:
                        if neighbor is face or neighbor in selected:
                            continue
                        if any(
                            adjacent is not neighbor and adjacent in selected and adjacent[grow_lock_layer]
                            for neighbor_edge in neighbor.edges
                            for adjacent in neighbor_edge.link_faces
                        ):
                            continue
                        local_angle = face.normal.angle(neighbor.normal, 0.0)
                        if settings.grow_use_angle_limits:
                            if local_angle > max_step_angle:
                                continue
                            if neighbor.normal.angle(avg, 0.0) > max_seed_angle:
                                continue
                        elif local_angle > max_boundary_angle:
                            face[grow_lock_layer] = 1
                            continue
                        to_add.add(neighbor)
            if not to_add:
                break
            for face in to_add:
                face.select_set(True)
            selected.update(to_add)
            added_total += len(to_add)

        bmesh.update_edit_mesh(obj.data)
        mode = "angle-limited" if settings.grow_use_angle_limits else "surface"
        self.report({"INFO"}, f"Grow {mode}: +{added_total} caras.")
        return {"FINISHED"}


class SPLIT3R_OT_shrink_smart_selection(Operator):
    bl_idname = "split3r.shrink_smart_selection"
    bl_label = "Shrink Smart Selection"
    bl_description = "Remove one boundary ring from the current face selection"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = _ensure_mesh_object(context)
        settings = context.scene.split3r_settings
        if obj.mode != "EDIT":
            bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        selected = {face for face in bm.faces if face.select}
        if not selected:
            self.report({"ERROR"}, "No hay selección para reducir.")
            return {"CANCELLED"}

        removed_total = 0
        for _ in range(settings.grow_steps):
            boundary = set()
            for face in selected:
                for edge in face.edges:
                    if len(edge.link_faces) != 2 or any(neighbor not in selected for neighbor in edge.link_faces):
                        boundary.add(face)
                        break
            if not boundary or boundary == selected:
                break
            for face in boundary:
                face.select_set(False)
            selected.difference_update(boundary)
            removed_total += len(boundary)

        bmesh.update_edit_mesh(obj.data)
        self.report({"INFO"}, f"Shrink Smart: -{removed_total} caras.")
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

        short_name = source.name[:40]
        plug = _mesh_from_faces(source, face_indices, f"Split3r_Plug_{short_name}")
        plug_mod = _add_solidify(plug, settings.plug_depth, "Split3r Plug Thickness")

        # Cutter is a separate solidified copy. Slightly thicker than plug for socket clearance.
        cutter = plug.copy()
        cutter.data = plug.data.copy()
        cutter.name = f"Split3r_Socket_Cutter_{short_name}"
        cutter.data.name = f"Split3r_Socket_CutterMesh_{source.data.name[:40]}"
        context.collection.objects.link(cutter)
        cutter.modifiers.clear()
        cutter_mod = _add_solidify(cutter, settings.plug_depth + settings.socket_clearance, "Split3r Socket Cutter Thickness")

        repair_notes = []
        if settings.apply_output_modifiers:
            _apply_modifier(plug, plug_mod.name)
            _apply_modifier(cutter, cutter_mod.name)
        if settings.repair_outputs:
            repair_notes.append((plug.name, _repair_mesh_object(plug)))
            repair_notes.append((cutter.name, _repair_mesh_object(cutter)))

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
        note = "Plug/socket creado con Solidify + Boolean EXACT."
        if repair_notes:
            filled = sum(item[1].get("filled_faces", 0) for item in repair_notes)
            note += f" Repair: {filled} caras de cierre agregadas."
        self.report({"INFO"}, note)
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
        layout.prop(settings, "grow_steps")
        layout.prop(settings, "grow_use_angle_limits")
        layout.prop(settings, "grow_boundary_angle")
        layout.operator("split3r.reset_selection_settings", icon="LOOP_BACK")
        layout.operator("split3r.smart_shell_select", icon="RESTRICT_SELECT_OFF")
        row = layout.row(align=True)
        row.operator("split3r.grow_smart_selection", text="Grow", icon="ADD")
        row.operator("split3r.shrink_smart_selection", text="Shrink", icon="REMOVE")
        layout.label(text="Shortcuts: Ctrl+Wheel Up/Down", icon="INFO")

        layout.separator()
        layout.label(text="3) Plug / Socket")
        layout.prop(settings, "plug_depth")
        layout.prop(settings, "socket_clearance")
        layout.prop(settings, "apply_boolean")
        layout.prop(settings, "keep_cutter")
        layout.prop(settings, "apply_output_modifiers")
        layout.prop(settings, "repair_outputs")
        layout.operator("split3r.create_plug_socket", icon="MOD_BOOLEAN")

        layout.separator()
        layout.label(text="4) Export")
        layout.operator("split3r.export_selected_stl", icon="EXPORT")

        layout.separator()
        box = layout.box()
        box.label(text="5) Threadwell Test Request")
        box.prop(settings, "ai_test_file")
        box.operator("split3r.pick_ai_test_file", icon="FILE_FOLDER")
        box.prop(settings, "ai_prompt")
        box.prop(settings, "ai_request_path")
        box.operator("split3r.write_threadwell_request", icon="TEXT")


_KEYMAPS = []


_CLASSES = (
    Split3rSettings,
    SPLIT3R_OT_import_3mf,
    SPLIT3R_OT_pick_ai_test_file,
    SPLIT3R_OT_write_threadwell_request,
    SPLIT3R_OT_smart_shell_select,
    SPLIT3R_OT_reset_selection_settings,
    SPLIT3R_OT_grow_smart_selection,
    SPLIT3R_OT_shrink_smart_selection,
    SPLIT3R_OT_create_plug_socket,
    SPLIT3R_OT_export_selected_stl,
    SPLIT3R_PT_panel,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.split3r_settings = PointerProperty(type=Split3rSettings)

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is not None:
        km = kc.keymaps.new(name="Mesh", space_type="EMPTY")
        kmi = km.keymap_items.new("split3r.grow_smart_selection", type="WHEELUPMOUSE", value="PRESS", ctrl=True)
        _KEYMAPS.append((km, kmi))
        kmi = km.keymap_items.new("split3r.shrink_smart_selection", type="WHEELDOWNMOUSE", value="PRESS", ctrl=True)
        _KEYMAPS.append((km, kmi))


def unregister():
    for km, kmi in _KEYMAPS:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _KEYMAPS.clear()
    if hasattr(bpy.types.Scene, "split3r_settings"):
        del bpy.types.Scene.split3r_settings
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
