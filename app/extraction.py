from __future__ import annotations

from collections import defaultdict

import numpy as np
import pyvista as pv

from .mesh_io import validate_polydata

_ORIGINAL_CELL_ID = "_split3r_original_cell_id"


def _empty_polydata() -> pv.PolyData:
    return pv.PolyData(np.empty((0, 3)), np.array([], dtype=np.int64))


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-9:
        raise ValueError("No se pudo calcular una dirección normal estable para la selección.")
    return vector / norm


def _main_connected_surface(mesh: pv.PolyData) -> pv.PolyData:
    """Keep the largest connected selected island to avoid noisy floating shards."""
    if mesh.n_cells <= 1:
        return mesh
    try:
        return mesh.connectivity(extraction_mode="largest").extract_surface().triangulate()
    except TypeError:
        return mesh.connectivity("largest").extract_surface().triangulate()


def _average_surface_normal(surface: pv.PolyData) -> np.ndarray:
    normals = surface.point_data.get("Normals")
    if normals is None or len(normals) == 0:
        surface = surface.compute_normals(auto_orient_normals=True, point_normals=True, cell_normals=True)
        normals = surface.point_data.get("Normals")
    return _normalize(np.asarray(normals, dtype=float).mean(axis=0))


def _boundary_loops(part_surface: pv.PolyData) -> list[list[int]]:
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

    orig_ids = np.asarray(boundary.point_data["vtkOriginalPointIds"], dtype=int)
    adjacency: dict[int, list[int]] = defaultdict(list)

    for i in range(boundary.n_cells):
        cell = boundary.get_cell(i)
        if len(cell.point_ids) < 2:
            continue
        a = int(orig_ids[int(cell.point_ids[0])])
        b = int(orig_ids[int(cell.point_ids[1])])
        if a == b:
            continue
        adjacency[a].append(b)
        adjacency[b].append(a)

    loops: list[list[int]] = []
    visited_edges: set[tuple[int, int]] = set()

    for start, neighbors in adjacency.items():
        for first_next in neighbors:
            edge_key = tuple(sorted((start, first_next)))
            if edge_key in visited_edges:
                continue

            loop = [start]
            prev = start
            current = first_next
            visited_edges.add(edge_key)

            while True:
                loop.append(current)
                candidates = [n for n in adjacency[current] if n != prev]
                if not candidates:
                    break

                # Prefer an unvisited edge; this handles occasional branchy boundaries better.
                next_point = None
                for candidate in candidates:
                    candidate_key = tuple(sorted((current, candidate)))
                    if candidate_key not in visited_edges:
                        next_point = candidate
                        break
                if next_point is None:
                    break

                if next_point == start:
                    visited_edges.add(tuple(sorted((current, next_point))))
                    break

                prev, current = current, next_point
                visited_edges.add(tuple(sorted((prev, current))))

            if len(loop) >= 3:
                # Remove duplicate closing vertex if present.
                if loop[0] == loop[-1]:
                    loop = loop[:-1]
                loops.append(loop)

    if not loops:
        raise ValueError("No se pudo ordenar el borde de la selección.")
    return loops


def _make_clean_cut_geometry(part_surface: pv.PolyData, extrude_depth: float) -> tuple[pv.PolyData, pv.PolyData]:
    """Create stable side walls plus a clean cap from ordered boundary loops.

    The old algorithm offset every selected vertex along its local normal. On rough scans this creates
    self-intersecting, spiky internal triangles. This version keeps the selected top surface intact,
    but makes the socket floor from the ordered border projected onto one stable cut plane.
    """
    normal = _average_surface_normal(part_surface)
    loops = _boundary_loops(part_surface)

    wall_pts: list[np.ndarray] = []
    wall_faces: list[int] = []
    cap_pts: list[np.ndarray] = []
    cap_faces: list[int] = []

    for loop in loops:
        top_points = np.asarray([part_surface.points[pid] for pid in loop], dtype=float)
        center = top_points.mean(axis=0)

        # Project the boundary to a single plane, then push it inward. This gives a much cleaner
        # visible separation than offsetting a noisy selected patch vertex-by-vertex.
        projected = top_points - np.outer((top_points - center) @ normal, normal)
        bottom_points = projected - normal * float(extrude_depth)

        wall_base = len(wall_pts)
        wall_pts.extend(top_points)
        wall_pts.extend(bottom_points)
        n = len(loop)

        for i in range(n):
            j = (i + 1) % n
            top_i = wall_base + i
            top_j = wall_base + j
            bot_i = wall_base + n + i
            bot_j = wall_base + n + j
            wall_faces.extend([3, top_i, top_j, bot_i])
            wall_faces.extend([3, top_j, bot_j, bot_i])

        cap_base = len(cap_pts)
        cap_pts.extend(bottom_points)
        cap_center_idx = len(cap_pts)
        cap_pts.append(bottom_points.mean(axis=0))
        for i in range(n):
            j = (i + 1) % n
            # Fan cap. Orientation is less important than avoiding the previous crumpled cap.
            cap_faces.extend([3, cap_center_idx, cap_base + j, cap_base + i])

    walls_mesh = pv.PolyData(np.asarray(wall_pts), np.asarray(wall_faces)).clean().triangulate() if wall_pts else _empty_polydata()
    cap_mesh = pv.PolyData(np.asarray(cap_pts), np.asarray(cap_faces)).clean().triangulate() if cap_pts else _empty_polydata()
    return walls_mesh, cap_mesh


def extract_plug_socket(current_mesh: pv.PolyData, selected_cells: set[int], extrude_depth: float) -> tuple[pv.PolyData, pv.PolyData]:
    """Return (plug_mesh, body_with_socket_mesh) for the selected cell region."""
    validate_polydata(current_mesh)
    if not selected_cells:
        raise ValueError("No hay caras seleccionadas para extraer.")
    if extrude_depth <= 0:
        raise ValueError("El grosor de extrusión debe ser mayor a cero.")

    valid_selection = {int(c) for c in selected_cells if 0 <= int(c) < current_mesh.n_cells}
    if not valid_selection:
        raise ValueError("La selección no contiene caras válidas.")
    if len(valid_selection) >= current_mesh.n_cells:
        raise ValueError("No se puede extraer el 100% de la malla como socket.")

    # Preserve original cell IDs so cleaning disconnected islands also updates the removed cells.
    current_mesh.cell_data[_ORIGINAL_CELL_ID] = np.arange(current_mesh.n_cells)
    part_surface = current_mesh.extract_cells(sorted(valid_selection)).extract_surface().triangulate()
    if part_surface.n_cells == 0:
        raise ValueError("La superficie seleccionada está vacía.")

    part_surface = _main_connected_surface(part_surface)
    if _ORIGINAL_CELL_ID in part_surface.cell_data:
        valid_selection = {int(cell_id) for cell_id in np.asarray(part_surface.cell_data[_ORIGINAL_CELL_ID]).ravel()}

    part_surface = part_surface.compute_normals(auto_orient_normals=True, point_normals=True, cell_normals=True)
    if "Normals" not in part_surface.point_data:
        raise ValueError("No se pudieron calcular normales para la selección.")

    top_surface = part_surface.copy()
    walls_mesh, socket_floor = _make_clean_cut_geometry(part_surface, extrude_depth)

    plug_mesh = top_surface.append_polydata(walls_mesh).append_polydata(socket_floor.copy()).clean().triangulate()

    remaining_ids = sorted(set(range(current_mesh.n_cells)) - valid_selection)
    remaining_surface = current_mesh.extract_cells(remaining_ids).extract_surface().triangulate()
    body_mesh = remaining_surface.append_polydata(walls_mesh.copy()).append_polydata(socket_floor.copy()).clean().triangulate()

    for mesh in (plug_mesh, body_mesh):
        if _ORIGINAL_CELL_ID in mesh.cell_data:
            del mesh.cell_data[_ORIGINAL_CELL_ID]

    validate_polydata(plug_mesh)
    validate_polydata(body_mesh)
    return plug_mesh, body_mesh
