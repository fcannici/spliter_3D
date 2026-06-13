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
    """Return (plug_mesh, body_with_socket_mesh) for the selected cell region.

    The plug keeps the requested extrusion depth. The body/socket is produced by
    subtracting a slightly larger cutter from the original mesh, giving the
    negative cavity a configurable FDM clearance/buffer.
    """
    validate_polydata(current_mesh)
    if not selected_cells:
        raise ValueError("No hay caras seleccionadas para extraer.")
    if extrude_depth <= 0:
        raise ValueError("El grosor de extrusión debe ser mayor a cero.")
    if socket_clearance < 0:
        raise ValueError("El buffer del socket no puede ser negativo.")

    valid_selection = {int(c) for c in selected_cells if 0 <= int(c) < current_mesh.n_cells}
    if not valid_selection:
        raise ValueError("La selección no contiene caras válidas.")
    if len(valid_selection) >= current_mesh.n_cells:
        raise ValueError("No se puede extraer el 100% de la malla como socket.")

    part_surface = current_mesh.extract_cells(sorted(valid_selection)).extract_surface(algorithm="dataset_surface").triangulate()
    if part_surface.n_cells == 0:
        raise ValueError("La superficie seleccionada está vacía.")

    part_surface = part_surface.compute_normals(auto_orient_normals=True, point_normals=True, cell_normals=True)
    if "Normals" not in part_surface.point_data:
        raise ValueError("No se pudieron calcular normales para la selección.")

    plug_mesh = _solid_from_offsets(part_surface, outward_offset=0.0, inward_offset=extrude_depth)

    # The cutter extends slightly outward to avoid coplanar boolean surfaces and
    # inward by depth + clearance, creating the requested negative buffer.
    socket_cutter = _solid_from_offsets(
        part_surface,
        outward_offset=socket_clearance,
        inward_offset=float(extrude_depth) + float(socket_clearance),
    )

    try:
        body_mesh = current_mesh.triangulate().boolean_difference(socket_cutter, progress_bar=False).clean().triangulate()
    except Exception:
        body_mesh = _fallback_socket_body(current_mesh, valid_selection, socket_cutter)

    validate_polydata(plug_mesh)
    validate_polydata(body_mesh)
    return plug_mesh, body_mesh
