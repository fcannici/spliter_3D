from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pyvista as pv

from .boolean_backend import BooleanBackendName, boolean_difference
from .mesh_io import validate_polydata
from .selection_boundary import BoundaryData, boundary_from_selection, triangular_faces, valid_selected_faces


@dataclass(frozen=True)
class InterlockingInsertResult:
    """Result meshes for the interlocking insert workflow."""

    insert_mesh: pv.PolyData
    body_mesh: pv.PolyData
    slot_cutter: pv.PolyData
    boundary: BoundaryData
    boolean_backend: str
    warnings: tuple[str, ...] = ()


def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    lengths = np.linalg.norm(vectors, axis=1)
    out = np.zeros_like(vectors, dtype=float)
    valid = lengths > 1e-12
    out[valid] = vectors[valid] / lengths[valid, None]
    return out


def _face_normals(points: np.ndarray, faces: np.ndarray) -> np.ndarray:
    tris = points[faces]
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    return _normalize_vectors(normals)


def _selected_vertex_normals(points: np.ndarray, faces: np.ndarray, selected_faces: Iterable[int]) -> np.ndarray:
    """Average selected-face normals per original vertex."""
    face_normals = _face_normals(points, faces)
    vertex_normals = np.zeros((len(points), 3), dtype=float)
    for face_id in selected_faces:
        normal = face_normals[int(face_id)]
        for vertex_id in faces[int(face_id)]:
            vertex_normals[int(vertex_id)] += normal

    normalized = _normalize_vectors(vertex_normals)
    missing = np.linalg.norm(normalized, axis=1) <= 1e-12
    if np.any(missing):
        # Stable fallback for unused vertices; selected vertices should normally
        # be covered by the accumulation above.
        normalized[missing] = np.array([0.0, 0.0, 1.0])
    return normalized


def _boundary_vertex_lateral_dirs(points: np.ndarray, vertex_normals: np.ndarray, boundary: BoundaryData) -> dict[int, np.ndarray]:
    """Approximate outward-in-surface expansion directions for boundary vertices.

    This is intentionally conservative: it projects the vector from the selected
    patch centroid to each boundary vertex onto the local tangent plane. For
    eye/patch inserts this expands the slot opening laterally to create FDM
    clearance while preserving the selected exterior surface for the insert.
    """
    selected_points = points[list(boundary.selected_vertices)]
    centroid = selected_points.mean(axis=0)
    lateral_dirs: dict[int, np.ndarray] = {}

    boundary_vertices = sorted({vertex for edge in boundary.boundary_edges for vertex in edge})
    for vertex_id in boundary_vertices:
        raw = points[vertex_id] - centroid
        normal = vertex_normals[vertex_id]
        tangent = raw - normal * float(np.dot(raw, normal))
        length = float(np.linalg.norm(tangent))
        if length <= 1e-12:
            tangent = raw
            length = float(np.linalg.norm(tangent))
        if length <= 1e-12:
            tangent = np.zeros(3)
        else:
            tangent = tangent / length
        lateral_dirs[int(vertex_id)] = tangent

    return lateral_dirs


def _build_surface_solid(
    mesh: pv.PolyData,
    boundary: BoundaryData,
    depth: float,
    *,
    outward_offset: float = 0.0,
    bottom_extra_depth: float = 0.0,
    lateral_clearance: float = 0.0,
) -> pv.PolyData:
    """Build a closed printable solid from the selected surface.

    The top preserves the original selected surface (plus optional tiny outward
    offset for cutters), the bottom is pushed inward by vertex normals, and side
    walls are built directly from robust topological boundary edges.
    """
    points = np.asarray(mesh.points, dtype=float)
    faces = triangular_faces(mesh)
    vertex_normals = _selected_vertex_normals(points, faces, boundary.selected_faces)
    lateral_dirs = _boundary_vertex_lateral_dirs(points, vertex_normals, boundary) if lateral_clearance > 0 else {}

    selected_vertices = list(boundary.selected_vertices)
    top_index = {vertex_id: idx for idx, vertex_id in enumerate(selected_vertices)}
    bottom_index = {vertex_id: idx + len(selected_vertices) for idx, vertex_id in enumerate(selected_vertices)}

    top_points = points[selected_vertices].copy()
    bottom_points = points[selected_vertices].copy()

    for local_idx, vertex_id in enumerate(selected_vertices):
        normal = vertex_normals[vertex_id]
        lateral = lateral_dirs.get(vertex_id, np.zeros(3)) * float(lateral_clearance)
        top_points[local_idx] = top_points[local_idx] + normal * float(outward_offset) + lateral
        bottom_points[local_idx] = bottom_points[local_idx] - normal * (float(depth) + float(bottom_extra_depth)) + lateral

    out_points = np.vstack([top_points, bottom_points])
    out_faces: list[int] = []

    # Top selected surface. Preserve original triangle winding.
    for face_id in boundary.selected_faces:
        face = faces[int(face_id)]
        out_faces.extend([3, top_index[int(face[0])], top_index[int(face[1])], top_index[int(face[2])]])

    # Bottom cap. Reverse winding to make the solid outward-oriented.
    for face_id in boundary.selected_faces:
        face = faces[int(face_id)]
        out_faces.extend([3, bottom_index[int(face[2])], bottom_index[int(face[1])], bottom_index[int(face[0])]])

    # Side walls from topological boundary edges.
    for a, b in boundary.boundary_edges:
        ta, tb = top_index[int(a)], top_index[int(b)]
        ba, bb = bottom_index[int(a)], bottom_index[int(b)]
        out_faces.extend([3, ta, ba, tb])
        out_faces.extend([3, tb, ba, bb])

    solid = pv.PolyData(out_points, np.asarray(out_faces, dtype=np.int64)).clean().triangulate()
    solid = solid.compute_normals(auto_orient_normals=True, consistent_normals=True, point_normals=True, cell_normals=True)
    validate_polydata(solid)
    return solid


def fallback_body_with_slot_surface(current_mesh: pv.PolyData, selected_cells: Iterable[int], slot_cutter: pv.PolyData) -> pv.PolyData:
    """Non-boolean fallback preview: remove selected faces and append slot walls.

    This is not as robust as a true boolean, but it gives the UI a meaningful
    preview if all boolean backends fail. Callers should surface the warning to
    users and prefer boolean output for production exports.
    """
    selected = set(valid_selected_faces(current_mesh, selected_cells))
    remaining_ids = sorted(set(range(current_mesh.n_cells)) - selected)
    remaining = current_mesh.extract_cells(remaining_ids).extract_surface(algorithm="dataset_surface").triangulate()
    slot_surface = slot_cutter.extract_surface(algorithm="dataset_surface").triangulate()
    body = remaining.append_polydata(slot_surface).clean().triangulate()
    validate_polydata(body)
    return body


def create_interlocking_insert(
    current_mesh: pv.PolyData,
    selected_cells: Iterable[int],
    depth: float,
    clearance: float = 0.2,
    *,
    backend: BooleanBackendName = "auto",
    allow_surface_fallback: bool = True,
) -> InterlockingInsertResult:
    """Create a printable insert and matching negative slot in the original body.

    This is the main Split3r workflow:

    ``selected visible surface -> solid insert -> larger slot cutter -> original - slot``.
    """
    validate_polydata(current_mesh)
    if depth <= 0:
        raise ValueError("El depth del insert debe ser mayor a cero.")
    if clearance < 0:
        raise ValueError("El clearance/buffer no puede ser negativo.")

    working_mesh = current_mesh.triangulate().clean()
    # Selection ids are expected to refer to the current triangulated mesh. The
    # app keeps meshes triangulated, so this preserves ids in normal operation.
    boundary = boundary_from_selection(working_mesh, selected_cells)

    insert_mesh = _build_surface_solid(working_mesh, boundary, float(depth))
    slot_cutter = _build_surface_solid(
        working_mesh,
        boundary,
        float(depth),
        outward_offset=float(clearance) * 0.5,
        bottom_extra_depth=float(clearance),
        lateral_clearance=float(clearance),
    )

    warnings: list[str] = []
    try:
        boolean = boolean_difference(working_mesh, slot_cutter, backend=backend)
        body_mesh = boolean.mesh
        boolean_backend = boolean.backend
        warnings.extend(boolean.warnings)
    except Exception as exc:
        if not allow_surface_fallback:
            raise
        body_mesh = fallback_body_with_slot_surface(working_mesh, boundary.selected_faces, slot_cutter)
        boolean_backend = "surface-fallback"
        warnings.append(f"Boolean real falló; se generó fallback de superficie: {exc}")

    validate_polydata(insert_mesh)
    validate_polydata(slot_cutter)
    validate_polydata(body_mesh)
    return InterlockingInsertResult(
        insert_mesh=insert_mesh,
        body_mesh=body_mesh,
        slot_cutter=slot_cutter,
        boundary=boundary,
        boolean_backend=boolean_backend,
        warnings=tuple(warnings),
    )
