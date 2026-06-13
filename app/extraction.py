from __future__ import annotations

import numpy as np
import pyvista as pv

from .mesh_io import validate_polydata


def _empty_polydata() -> pv.PolyData:
    return pv.PolyData(np.empty((0, 3)), np.array([], dtype=np.int64))


def _build_walls(part_surface: pv.PolyData, top_surface: pv.PolyData, bottom_surface: pv.PolyData) -> pv.PolyData:
    boundary = part_surface.extract_feature_edges(
        boundary_edges=True,
        non_manifold_edges=False,
        feature_edges=False,
        manifold_edges=False,
    )

    if boundary.n_cells == 0:
        raise ValueError("La selección no tiene borde abierto; no se puede construir socket.")
    if "vtkOriginalPointIds" not in boundary.point_data:
        raise ValueError("PyVista no devolvió vtkOriginalPointIds para el borde de la selección.")

    orig_ids = boundary.point_data["vtkOriginalPointIds"]
    wall_pts: list[np.ndarray] = []
    wall_faces: list[int] = []

    for i in range(boundary.n_cells):
        cell = boundary.get_cell(i)
        if len(cell.point_ids) < 2:
            continue
        p1_local, p2_local = int(cell.point_ids[0]), int(cell.point_ids[1])
        id1, id2 = int(orig_ids[p1_local]), int(orig_ids[p2_local])

        v1_t, v2_t = top_surface.points[id1], top_surface.points[id2]
        v1_b, v2_b = bottom_surface.points[id1], bottom_surface.points[id2]

        base_idx = len(wall_pts)
        wall_pts.extend([v1_t, v2_t, v1_b, v2_b])
        wall_faces.extend([3, base_idx, base_idx + 1, base_idx + 2])
        wall_faces.extend([3, base_idx + 1, base_idx + 3, base_idx + 2])

    if not wall_pts:
        return _empty_polydata()
    return pv.PolyData(np.asarray(wall_pts), np.asarray(wall_faces)).triangulate()


def _solid_from_offsets(part_surface: pv.PolyData, outward_offset: float, inward_offset: float) -> pv.PolyData:
    """Create a closed solid from a selected surface using point-normal offsets."""
    top_surface = part_surface.copy()
    bottom_surface = part_surface.copy()
    normals = part_surface.point_data["Normals"]
    top_surface.points += normals * float(outward_offset)
    bottom_surface.points -= normals * float(inward_offset)
    walls_mesh = _build_walls(part_surface, top_surface, bottom_surface)
    return top_surface.append_polydata(bottom_surface).append_polydata(walls_mesh).clean().triangulate()


def _fallback_socket_body(current_mesh: pv.PolyData, valid_selection: set[int], socket_cutter: pv.PolyData) -> pv.PolyData:
    """Fallback socket construction when a VTK boolean cannot be computed."""
    remaining_ids = sorted(set(range(current_mesh.n_cells)) - valid_selection)
    remaining_surface = current_mesh.extract_cells(remaining_ids).extract_surface(algorithm="dataset_surface").triangulate()
    socket_surface = socket_cutter.extract_surface(algorithm="dataset_surface").triangulate()
    return remaining_surface.append_polydata(socket_surface).clean().triangulate()


def extract_plug_socket(
    current_mesh: pv.PolyData,
    selected_cells: set[int],
    extrude_depth: float,
    socket_clearance: float = 0.2,
) -> tuple[pv.PolyData, pv.PolyData]:
    """Compatibility wrapper for the interlocking insert workflow."""
    from .interlocking import create_interlocking_insert

    result = create_interlocking_insert(
        current_mesh,
        selected_cells,
        depth=extrude_depth,
        clearance=socket_clearance,
        backend="auto",
        allow_surface_fallback=True,
    )
    return result.insert_mesh, result.body_mesh
