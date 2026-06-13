"""Headless QA test for the Split3r Blender add-on.

It imports the requested model, runs Smart Shell, creates plug/socket, exports artifacts,
saves a .blend, renders PNG views, and writes a JSON report so the agent can inspect the
actual result instead of only handing work back to the user.
"""

from __future__ import annotations

import json
import math
import sys
import traceback
from datetime import datetime
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_addon():
    addon_root = _repo_root() / "blender_split3r_addon"
    sys.path.insert(0, str(addon_root.parent))
    import blender_split3r_addon as addon

    try:
        addon.unregister()
    except Exception:
        pass
    addon.register()
    return addon


def _create_obj_from_3mf(addon, filepath: str):
    meshes = addon._load_3mf_meshes(filepath)  # internal test hook
    if not meshes:
        raise RuntimeError("3MF has no compatible meshes")

    model_name, vertices, faces = max(meshes, key=lambda item: len(item[2]))
    mesh = bpy.data.meshes.new(Path(filepath).stem + "_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(Path(filepath).stem, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj, {"source_model": model_name, "mesh_count": len(meshes)}


def _import_mesh(addon, filepath: str):
    suffix = Path(filepath).suffix.lower()
    if suffix == ".3mf":
        return _create_obj_from_3mf(addon, filepath)
    if suffix == ".stl":
        if hasattr(bpy.ops.wm, "stl_import"):
            bpy.ops.wm.stl_import(filepath=filepath)
        else:
            bpy.ops.import_mesh.stl(filepath=filepath)
        obj = bpy.context.object
        if obj is None:
            raise RuntimeError("STL import produced no active object")
        return obj, {"source_model": Path(filepath).name, "mesh_count": 1}
    raise RuntimeError(f"Unsupported test file: {filepath}")


def _object_bounds(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    mn = Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners)))
    mx = Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners)))
    return mn, mx, mx - mn


def _pick_seed_face(bm, strategy: str, request: dict):
    bm.faces.ensure_lookup_table()
    if not bm.faces:
        raise RuntimeError("Mesh has no faces")
    if "seed_face_index" in request:
        index = int(request["seed_face_index"])
        if 0 <= index < len(bm.faces):
            return bm.faces[index]
        raise RuntimeError(f"seed_face_index out of range: {index}")

    if "seed_point" in request:
        p = Vector(tuple(float(v) for v in request["seed_point"]))
        return min(bm.faces, key=lambda face: (face.calc_center_median() - p).length_squared)

    if strategy == "front_low":
        return min(bm.faces, key=lambda face: (face.calc_center_median().y, -face.calc_center_median().z))
    if strategy == "front_mid":
        return min(bm.faces, key=lambda face: (face.calc_center_median().y, abs(face.calc_center_median().z)))
    if strategy == "top":
        return max(bm.faces, key=lambda face: (face.calc_center_median().z, face.calc_center_median().y))
    if strategy == "right":
        return max(bm.faces, key=lambda face: face.calc_center_median().x)
    if strategy == "left":
        return min(bm.faces, key=lambda face: face.calc_center_median().x)
    return max(bm.faces, key=lambda face: (face.calc_center_median().z, face.calc_center_median().y))


def _select_seed_and_run_smart_shell(obj, smart_angle: float, smart_step_angle: float, request: dict):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="FACE")
    bpy.ops.mesh.select_all(action="DESELECT")

    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    provided_indices = [int(i) for i in request.get("selected_face_indices", [])]
    if provided_indices:
        valid = 0
        for index in provided_indices:
            if 0 <= index < len(bm.faces):
                bm.faces[index].select_set(True)
                valid += 1
        bmesh.update_edit_mesh(obj.data)
        selected_centers = [face.calc_center_median() for face in bm.faces if face.select]
        if selected_centers:
            mn = Vector((min(v.x for v in selected_centers), min(v.y for v in selected_centers), min(v.z for v in selected_centers)))
            mx = Vector((max(v.x for v in selected_centers), max(v.y for v in selected_centers), max(v.z for v in selected_centers)))
            selected_bounds = {"min": list(mn), "max": list(mx), "size": list(mx - mn)}
        else:
            selected_bounds = None
        total_count = len(bm.faces)
        bpy.ops.object.mode_set(mode="OBJECT")
        return {
            "operator_result": ["PROVIDED_SELECTION"],
            "selection_source": "request.selected_face_indices",
            "selected_faces": valid,
            "total_faces": total_count,
            "selected_ratio": valid / max(total_count, 1),
            "selected_bounds": selected_bounds,
        }

    strategy = str(request.get("seed_strategy", "top"))
    seed = _pick_seed_face(bm, strategy, request)
    seed_index = seed.index
    seed_center = seed.calc_center_median().copy()
    seed_normal = seed.normal.copy()
    seed.select_set(True)
    bm.select_history.clear()
    bm.select_history.add(seed)
    bmesh.update_edit_mesh(obj.data)

    settings = bpy.context.scene.split3r_settings
    settings.smart_angle = smart_angle
    settings.smart_step_angle = smart_step_angle
    result = bpy.ops.split3r.smart_shell_select()

    selected_count = sum(1 for face in bm.faces if face.select)
    total_count = len(bm.faces)
    selected_centers = [face.calc_center_median() for face in bm.faces if face.select]
    if selected_centers:
        mn = Vector((min(v.x for v in selected_centers), min(v.y for v in selected_centers), min(v.z for v in selected_centers)))
        mx = Vector((max(v.x for v in selected_centers), max(v.y for v in selected_centers), max(v.z for v in selected_centers)))
        selected_bounds = {"min": list(mn), "max": list(mx), "size": list(mx - mn)}
    else:
        selected_bounds = None
    bpy.ops.object.mode_set(mode="OBJECT")
    return {
        "operator_result": list(result),
        "seed_strategy": strategy,
        "seed_face_index": seed_index,
        "seed_center": list(seed_center),
        "seed_normal": list(seed_normal),
        "selected_faces": selected_count,
        "total_faces": total_count,
        "selected_ratio": selected_count / max(total_count, 1),
        "selected_bounds": selected_bounds,
    }


def _evaluated_mesh_stats(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(eval_obj, depsgraph=depsgraph)
    try:
        boundary_edges = 0
        nonmanifold_edges = 0
        for edge in mesh.edges:
            linked = 0
            verts = set(edge.vertices)
            for poly in mesh.polygons:
                pv = poly.vertices[:]
                if any({pv[i], pv[(i + 1) % len(pv)]} == verts for i in range(len(pv))):
                    linked += 1
            if linked == 1:
                boundary_edges += 1
            if linked != 2:
                nonmanifold_edges += 1
        return {
            "vertices": len(mesh.vertices),
            "faces": len(mesh.polygons),
            "edges": len(mesh.edges),
            "boundary_edges": boundary_edges,
            "nonmanifold_edges": nonmanifold_edges,
        }
    finally:
        bpy.data.meshes.remove(mesh)


def _make_material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    return mat


def _run_plug_socket(obj, plug_depth: float, socket_clearance: float):
    before = set(bpy.data.objects)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    settings = bpy.context.scene.split3r_settings
    settings.plug_depth = plug_depth
    settings.socket_clearance = socket_clearance
    settings.apply_boolean = False
    result = bpy.ops.split3r.create_plug_socket()
    created = [item for item in bpy.data.objects if item not in before]
    plug_objects = [item for item in created if "Plug" in item.name or any("Plug" in mod.name for mod in item.modifiers)]
    cutter_objects = [item for item in created if "Cutter" in item.name or any("Cutter" in mod.name for mod in item.modifiers)]
    boolean_mods = [mod.name for mod in obj.modifiers if mod.type == "BOOLEAN" and "Split3r" in mod.name]
    return {
        "operator_result": list(result),
        "created_objects": [item.name for item in created],
        "plug_objects": [item.name for item in plug_objects],
        "cutter_objects": [item.name for item in cutter_objects],
        "boolean_modifiers": boolean_mods,
    }, plug_objects, cutter_objects


def _export_stl(addon, obj, filepath: Path):
    addon._export_object_stl(obj, str(filepath))
    return {"path": str(filepath), "exists": filepath.exists(), "bytes": filepath.stat().st_size if filepath.exists() else 0}


def _setup_camera(target_obj, out_dir: Path):
    mn, mx, size = _object_bounds(target_obj)
    center = (mn + mx) * 0.5
    radius = max(size.length, 1.0)
    bpy.ops.object.light_add(type="AREA", location=(center.x, center.y - radius, center.z + radius))
    light = bpy.context.object
    light.name = "Split3r_QA_Light"
    light.data.energy = 600
    light.data.size = radius
    bpy.ops.object.camera_add(location=(center.x, center.y - radius * 1.8, center.z + radius * 0.55), rotation=(math.radians(72), 0, 0))
    cam = bpy.context.object
    bpy.context.scene.camera = cam
    cam.data.lens = 55
    bpy.context.scene.render.resolution_x = 1400
    bpy.context.scene.render.resolution_y = 1000
    bpy.context.scene.eevee.taa_render_samples = 32 if hasattr(bpy.context.scene, "eevee") else 16
    return cam


def _render_view(path: Path):
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return {"path": str(path), "exists": path.exists(), "bytes": path.stat().st_size if path.exists() else 0}


def main() -> int:
    argv = sys.argv
    request_path = None
    if "--" in argv:
        rest = argv[argv.index("--") + 1 :]
        if rest:
            request_path = Path(rest[0])
    if request_path is None:
        request_path = Path.home() / "split3r_blender_request.json"

    addon = _load_addon()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    test_file = request["test_file"]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    requested_out = Path(request.get("output_dir") or (_repo_root() / "blender_test_outputs" / stamp))
    out_dir = requested_out if requested_out.is_absolute() else (_repo_root() / requested_out)
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {"request_path": str(request_path), "test_file": test_file, "output_dir": str(out_dir), "ok": False}

    try:
        body_mat = _make_material("Split3r Body Cyan", (0.0, 0.65, 0.9, 1.0))
        plug_mat = _make_material("Split3r Plug Orange", (1.0, 0.45, 0.05, 1.0))
        cutter_mat = _make_material("Split3r Cutter Transparent", (0.2, 1.0, 0.2, 0.35))

        obj, import_info = _import_mesh(addon, test_file)
        obj.data.materials.append(body_mat)
        report.update(import_info)
        mn, mx, size = _object_bounds(obj)
        report["import"] = {
            "object": obj.name,
            "vertices": len(obj.data.vertices),
            "faces": len(obj.data.polygons),
            "edges": len(obj.data.edges),
            "bounds_min": list(mn),
            "bounds_max": list(mx),
            "bounds_size": list(size),
        }
        report["smart_shell"] = _select_seed_and_run_smart_shell(
            obj,
            float(request.get("smart_angle", 18.0)),
            float(request.get("smart_step_angle", 10.0)),
            request,
        )
        report["plug_socket"], plug_objects, cutter_objects = _run_plug_socket(
            obj,
            float(request.get("plug_depth", 2.0)),
            float(request.get("socket_clearance", 0.15)),
        )
        for plug in plug_objects:
            plug.data.materials.append(plug_mat)
        for cutter in cutter_objects:
            cutter.data.materials.append(cutter_mat)
            cutter.show_transparent = True

        report["mesh_stats"] = {"body_source": {"vertices": len(obj.data.vertices), "faces": len(obj.data.polygons), "edges": len(obj.data.edges)}}
        if plug_objects:
            report["mesh_stats"]["plug_evaluated"] = _evaluated_mesh_stats(plug_objects[0])
        if cutter_objects:
            report["mesh_stats"]["cutter_evaluated"] = _evaluated_mesh_stats(cutter_objects[0])

        exports = {}
        if plug_objects:
            exports["plug_stl"] = _export_stl(addon, plug_objects[0], out_dir / "split3r_plug.stl")
        exports["body_preview_stl"] = _export_stl(addon, obj, out_dir / "split3r_body_preview.stl")
        report["exports"] = exports

        _setup_camera(obj, out_dir)
        report["renders"] = {"front": _render_view(out_dir / "split3r_front.png")}
        bpy.ops.wm.save_as_mainfile(filepath=str(out_dir / "split3r_result.blend"))
        report["blend_file"] = str(out_dir / "split3r_result.blend")
        report["ok"] = True
    except Exception as exc:
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()

    out_path = request_path.with_suffix(".report.json")
    report["report_path"] = str(out_path)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("SPLIT3R_BLENDER_REPORT=" + str(out_path))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
