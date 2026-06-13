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


def remove_triangle_artifacts(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Remove extreme long/skinny triangles produced by some 3MF slicer/project files.

    The Aztec whistle test file contains thousands of needle triangles (often 10-25 mm long
    but only hundredths of a millimeter wide). They are already present in the source mesh and
    later appear as black/cyan hairs after extraction. This filter is conservative: it only
    removes triangles that are both unusually long for the mesh and extremely skinny, leaving
    normal rectangular/large faces intact.
    """
    if mesh.faces.size == 0:
        return mesh

    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    triangles = vertices[faces]
    edge_lengths = np.stack(
        [
            np.linalg.norm(triangles[:, 0] - triangles[:, 1], axis=1),
            np.linalg.norm(triangles[:, 1] - triangles[:, 2], axis=1),
            np.linalg.norm(triangles[:, 2] - triangles[:, 0], axis=1),
        ],
        axis=1,
    )

    max_edge = edge_lengths.max(axis=1)
    min_edge = np.maximum(edge_lengths.min(axis=1), 1e-9)
    aspect_ratio = max_edge / min_edge

    if len(max_edge) >= 100:
        long_edge_threshold = max(
            4.0,
            float(np.median(max_edge) * 12.0),
            float(np.percentile(max_edge, 90) * 6.0),
        )
    else:
        long_edge_threshold = 4.0
    artifact_faces = (max_edge > long_edge_threshold) & (aspect_ratio > 20.0)
    if not np.any(artifact_faces):
        return mesh

    cleaned = mesh.copy()
    cleaned.update_faces(~artifact_faces)
    cleaned.remove_unreferenced_vertices()
    return cleaned


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
    # Do not remove triangles during import. Bambu 3MF files can be watertight only with
    # very thin triangles that look like artifacts numerically; removing them here makes the
    # model appear broken before any extraction. Artifact cleanup is applied later to extracted
    # pieces, where it is safer.
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
