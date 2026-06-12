from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista as pv
import trimesh


def _scene_to_mesh(scene: trimesh.Scene) -> trimesh.Trimesh:
    """Convert a trimesh Scene into a single mesh, preserving node transforms."""
    meshes: list[trimesh.Trimesh] = []
    for node_name in scene.graph.nodes_geometry:
        transform, geometry_name = scene.graph[node_name]
        geom = scene.geometry.get(geometry_name)
        if geom is None or not isinstance(geom, trimesh.Trimesh):
            continue
        mesh = geom.copy()
        mesh.apply_transform(transform)
        meshes.append(mesh)

    if not meshes:
        raise ValueError("La escena no contiene geometrías de malla compatibles.")

    return trimesh.util.concatenate(meshes)


def load_trimesh(filepath: str | Path) -> trimesh.Trimesh:
    """Load STL/OBJ/3MF as a validated, triangular trimesh."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(path)

    loaded = trimesh.load(path, force=None)
    mesh = _scene_to_mesh(loaded) if isinstance(loaded, trimesh.Scene) else loaded

    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"Formato no soportado o no es una malla: {type(mesh).__name__}")
    if mesh.vertices.size == 0 or mesh.faces.size == 0:
        raise ValueError("La malla está vacía.")

    # Trimesh faces are triangles, but process=False sources can leave bad data.
    mesh.remove_unreferenced_vertices()
    if mesh.faces.shape[1] != 3:
        raise ValueError("Solo se soportan mallas trianguladas.")
    return mesh


def trimesh_to_polydata(mesh: trimesh.Trimesh) -> pv.PolyData:
    """Convert a triangular trimesh mesh to PyVista PolyData."""
    faces = np.column_stack((np.full(len(mesh.faces), 3), mesh.faces)).ravel()
    return pv.PolyData(mesh.vertices, faces)


def polydata_to_trimesh(mesh: pv.PolyData) -> trimesh.Trimesh:
    """Convert triangular PyVista PolyData to trimesh."""
    tri = mesh.triangulate()
    faces = tri.faces.reshape((-1, 4))[:, 1:]
    return trimesh.Trimesh(vertices=tri.points, faces=faces, process=False)


def validate_polydata(mesh: pv.PolyData | None, *, require_cells: bool = True) -> None:
    if mesh is None:
        raise ValueError("No hay una malla cargada.")
    if mesh.n_points == 0 or (require_cells and mesh.n_cells == 0):
        raise ValueError("La malla está vacía.")
    faces = mesh.faces
    idx = 0
    while idx < len(faces):
        n = int(faces[idx])
        if n != 3:
            raise ValueError("La operación requiere una malla triangulada.")
        idx += n + 1
