"""Headless smoke test for the Split3r Blender add-on.

Usage from repo root:

    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" --background --factory-startup \
      --python scripts/blender_split3r_smoke_test.py -- C:/Users/you/split3r_blender_request.json

The request JSON is produced by the add-on panel: N Panel > Split3r > Threadwell Test Request.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import bpy
import bmesh


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

    # Use the largest mesh if a project contains several objects.
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


def _select_seed_and_run_smart_shell(obj, smart_angle: float, smart_step_angle: float):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="FACE")
    bpy.ops.mesh.select_all(action="DESELECT")

    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    if not bm.faces:
        raise RuntimeError("Mesh has no faces")

    # Deterministic visible-ish seed: face with highest center Z, then highest Y.
    seed = max(bm.faces, key=lambda face: (face.calc_center_median().z, face.calc_center_median().y))
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
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"operator_result": list(result), "selected_faces": selected_count, "total_faces": total_count}


def _run_plug_socket(obj, plug_depth: float, socket_clearance: float):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    settings = bpy.context.scene.split3r_settings
    settings.plug_depth = plug_depth
    settings.socket_clearance = socket_clearance
    settings.apply_boolean = False
    result = bpy.ops.split3r.create_plug_socket()
    plug_count = len([item for item in bpy.data.objects if item.name.endswith("_Split3r_Plug") or "Split3r_Plug" in item.name])
    cutter_count = len([item for item in bpy.data.objects if "Split3r_Socket_Cutter" in item.name])
    boolean_count = len([mod for mod in obj.modifiers if mod.type == "BOOLEAN" and "Split3r" in mod.name])
    return {"operator_result": list(result), "plug_objects": plug_count, "cutter_objects": cutter_count, "boolean_modifiers": boolean_count}


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
    report = {"request_path": str(request_path), "test_file": test_file, "ok": False}

    try:
        obj, import_info = _import_mesh(addon, test_file)
        report.update(import_info)
        report["import"] = {
            "object": obj.name,
            "vertices": len(obj.data.vertices),
            "faces": len(obj.data.polygons),
            "edges": len(obj.data.edges),
        }
        report["smart_shell"] = _select_seed_and_run_smart_shell(
            obj,
            float(request.get("smart_angle", 18.0)),
            float(request.get("smart_step_angle", 10.0)),
        )
        report["plug_socket"] = _run_plug_socket(
            obj,
            float(request.get("plug_depth", 2.0)),
            float(request.get("socket_clearance", 0.15)),
        )
        report["ok"] = True
    except Exception as exc:
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()

    out_path = request_path.with_suffix(".report.json")
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("SPLIT3R_BLENDER_REPORT=" + str(out_path))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
