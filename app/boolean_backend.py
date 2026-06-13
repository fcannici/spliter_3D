from __future__ import annotations

import shutil
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pyvista as pv

from .mesh_io import validate_polydata

BooleanBackendName = Literal["auto", "blender", "vtk"]


@dataclass(frozen=True)
class BooleanResult:
    mesh: pv.PolyData
    backend: str
    warnings: tuple[str, ...] = ()


def _prepared(mesh: pv.PolyData) -> pv.PolyData:
    validate_polydata(mesh)
    return mesh.extract_surface(algorithm="dataset_surface").triangulate().clean()


def _boolean_difference_vtk(base: pv.PolyData, cutter: pv.PolyData) -> BooleanResult:
    base_prepared = _prepared(base)
    cutter_prepared = _prepared(cutter)
    result = base_prepared.boolean_difference(cutter_prepared, progress_bar=False).clean().triangulate()
    validate_polydata(result)
    if result.n_cells == 0:
        raise ValueError("El boolean VTK devolvió una malla vacía.")
    return BooleanResult(result, backend="vtk")


def _boolean_difference_blender(base: pv.PolyData, cutter: pv.PolyData, blender_path: str) -> BooleanResult:
    """Run a robust Blender boolean in background when Blender is installed."""
    base_prepared = _prepared(base)
    cutter_prepared = _prepared(cutter)

    with tempfile.TemporaryDirectory(prefix="split3r_boolean_") as tmp:
        tmp_path = Path(tmp)
        base_path = tmp_path / "base.stl"
        cutter_path = tmp_path / "cutter.stl"
        out_path = tmp_path / "result.stl"
        script_path = tmp_path / "boolean_difference.py"

        base_prepared.save(base_path)
        cutter_prepared.save(cutter_path)

        script_path.write_text(
            textwrap.dedent(
                f"""
                import bpy
                from pathlib import Path

                for obj in list(bpy.context.scene.objects):
                    obj.select_set(True)
                bpy.ops.object.delete()

                bpy.ops.wm.stl_import(filepath={str(base_path)!r})
                base = bpy.context.object
                base.name = "split3r_base"

                bpy.ops.wm.stl_import(filepath={str(cutter_path)!r})
                cutter = bpy.context.object
                cutter.name = "split3r_cutter"

                bpy.context.view_layer.objects.active = base
                base.select_set(True)
                cutter.select_set(False)
                modifier = base.modifiers.new(name="split3r_difference", type="BOOLEAN")
                modifier.operation = "DIFFERENCE"
                modifier.object = cutter
                modifier.solver = "EXACT"
                bpy.ops.object.modifier_apply(modifier=modifier.name)

                cutter.select_set(True)
                bpy.ops.object.delete()

                bpy.context.view_layer.objects.active = base
                base.select_set(True)
                bpy.ops.wm.stl_export(filepath={str(out_path)!r}, export_selected_objects=True)
                """
            ),
            encoding="utf-8",
        )

        proc = subprocess.run(
            [blender_path, "--background", "--factory-startup", "--python", str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Blender boolean failed: {proc.stderr[-2000:] or proc.stdout[-2000:]}")
        if not out_path.exists():
            raise RuntimeError("Blender no generó la malla resultante.")

        result = pv.read(out_path).extract_surface(algorithm="dataset_surface").triangulate().clean()
        validate_polydata(result)
        if result.n_cells == 0:
            raise ValueError("El boolean Blender devolvió una malla vacía.")
        return BooleanResult(result, backend="blender")


def boolean_difference(base: pv.PolyData, cutter: pv.PolyData, backend: BooleanBackendName = "auto") -> BooleanResult:
    """Subtract ``cutter`` from ``base`` using the best available backend."""
    warnings: list[str] = []

    if backend in ("auto", "blender"):
        blender_path = shutil.which("blender")
        if blender_path:
            try:
                return _boolean_difference_blender(base, cutter, blender_path)
            except Exception as exc:
                if backend == "blender":
                    raise
                warnings.append(f"Blender boolean falló; usando VTK: {exc}")
        elif backend == "blender":
            raise RuntimeError("No se encontró Blender en PATH.")

    try:
        result = _boolean_difference_vtk(base, cutter)
        return BooleanResult(result.mesh, backend=result.backend, warnings=tuple(warnings + list(result.warnings)))
    except Exception as exc:
        if warnings:
            raise RuntimeError("; ".join(warnings + [f"VTK boolean falló: {exc}"])) from exc
        raise
