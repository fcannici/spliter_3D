from __future__ import annotations

from collections import defaultdict, deque

import numpy as np
import pyvista as pv
from scipy.spatial import Delaunay

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
    adjacency: dict[int, set[int]] = defaultdict(set)

    for i in range(boundary.n_cells):
        cell = boundary.get_cell(i)
        if len(cell.point_ids) < 2:
            continue
        a = int(orig_ids[int(cell.point_ids[0])])
        b = int(orig_ids[int(cell.point_ids[1])])
        if a == b:
            continue
        adjacency[a].add(b)
        adjacency[b].add(a)

    # Only closed, non-branching boundary components are safe to cap. Open or branched
    # components are the source of the long fins/hairs visible after extraction.
    loops: list[list[int]] = []
    seen_nodes: set[int] = set()
    for start in list(adjacency):
        if start in seen_nodes:
            continue

        component: set[int] = set()
        queue: deque[int] = deque([start])
        seen_nodes.add(start)
        while queue:
            node = queue.popleft()
            component.add(node)
            for neighbor in adjacency[node]:
                if neighbor not in seen_nodes:
                    seen_nodes.add(neighbor)
                    queue.append(neighbor)

        if len(component) < 4:
            continue
        if any(len(adjacency[node]) != 2 for node in component):
            # Discard malformed/open/branched loops instead of creating visual artifacts.
            continue

        ordered = [start]
        prev = None
        current = start
        while True:
            neighbors = list(adjacency[current])
            next_node = neighbors[0] if neighbors[0] != prev else neighbors[1]
            if next_node == start:
                break
            if next_node in ordered:
                ordered = []
                break
            ordered.append(next_node)
            prev, current = current, next_node

        if len(ordered) >= 4:
            loops.append(ordered)

    if not loops:
        raise ValueError("No se pudo encontrar un borde cerrado limpio. Ajustá la selección para evitar bordes abiertos o ramificados.")
    return loops


def _basis_from_normal(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    helper = np.array([1.0, 0.0, 0.0]) if abs(float(normal[0])) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = _normalize(np.cross(normal, helper))
    v = _normalize(np.cross(normal, u))
    return u, v


def _polygon_area(points_2d: np.ndarray) -> float:
    x = points_2d[:, 0]
    y = points_2d[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _points_in_polygon(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    x = points[:, 0]
    y = points[:, 1]
    poly_x = polygon[:, 0]
    poly_y = polygon[:, 1]
    inside = np.zeros(len(points), dtype=bool)
    j = len(polygon) - 1
    for i in range(len(polygon)):
        intersects = ((poly_y[i] > y) != (poly_y[j] > y)) & (
            x < (poly_x[j] - poly_x[i]) * (y - poly_y[i]) / (poly_y[j] - poly_y[i] + 1e-12) + poly_x[i]
        )
        inside ^= intersects
        j = i
    return inside


def _triangulate_cap(bottom_points: np.ndarray, normal: np.ndarray) -> pv.PolyData:
    if len(bottom_points) < 3:
        return _empty_polydata()

    center = bottom_points.mean(axis=0)
    u, v = _basis_from_normal(normal)
    rel = bottom_points - center
    points_2d = np.column_stack((rel @ u, rel @ v))

    # Drop near-duplicate boundary vertices before triangulation.
    _, unique_indices = np.unique(np.round(points_2d, decimals=6), axis=0, return_index=True)
    unique_indices = np.sort(unique_indices)
    bottom_points = bottom_points[unique_indices]
    points_2d = points_2d[unique_indices]
    if len(bottom_points) < 3 or _polygon_area(points_2d) <= 1e-8:
        return _empty_polydata()

    try:
        simplices = Delaunay(points_2d).simplices
    except Exception:
        # Safe fallback: no cap is better than a huge crossing fin.
        return _empty_polydata()

    centroids = points_2d[simplices].mean(axis=1)
    inside = _points_in_polygon(centroids, points_2d)

    edge_lengths = np.linalg.norm(np.diff(np.vstack([points_2d, points_2d[0]]), axis=0), axis=1)
    max_reasonable_edge = max(float(np.percentile(edge_lengths, 90) * 3.0), float(edge_lengths.mean() * 4.0), 1e-6)

    faces: list[int] = []
    for tri in simplices[inside]:
        tri_pts = points_2d[tri]
        tri_edges = [
            np.linalg.norm(tri_pts[0] - tri_pts[1]),
            np.linalg.norm(tri_pts[1] - tri_pts[2]),
            np.linalg.norm(tri_pts[2] - tri_pts[0]),
        ]
        if max(tri_edges) > max_reasonable_edge:
            continue
        faces.extend([3, int(tri[0]), int(tri[1]), int(tri[2])])

    if not faces:
        return _empty_polydata()
    return pv.PolyData(bottom_points, np.asarray(faces)).clean().triangulate()


def _make_clean_cut_geometry(part_surface: pv.PolyData, extrude_depth: float) -> tuple[pv.PolyData, pv.PolyData]:
    """Create stable side walls plus a clean cap from ordered boundary loops.

    The old algorithm offset every selected vertex along its local normal. On rough scans this creates
    self-intersecting, spiky internal triangles. This version keeps the selected top surface intact,
    but makes the socket floor from the ordered border projected onto one stable cut plane.
    """
    normal = _average_surface_normal(part_surface)
    loops = _boundary_loops(part_surface)

    loop_data = []
    u, v = _basis_from_normal(normal)
    for loop in loops:
        top_points = np.asarray([part_surface.points[pid] for pid in loop], dtype=float)
        center = top_points.mean(axis=0)
        points_2d = np.column_stack(((top_points - center) @ u, (top_points - center) @ v))
        area = _polygon_area(points_2d)
        if area > 1e-8:
            loop_data.append((area, top_points))

    if not loop_data:
        raise ValueError("El borde de la selección no tiene área suficiente para generar una tapa limpia.")

    # Keep the real cut loops and discard tiny noisy loops from scan artifacts/teeth.
    max_area = max(area for area, _ in loop_data)
    loop_data = [(area, pts) for area, pts in loop_data if area >= max_area * 0.08 and len(pts) >= 8]
    if not loop_data:
        raise ValueError("Solo se encontraron loops de borde pequeños o ruidosos.")

    wall_pts: list[np.ndarray] = []
    wall_faces: list[int] = []
    cap_meshes: list[pv.PolyData] = []

    for _area, top_points in loop_data:
        center = top_points.mean(axis=0)

        # Project the boundary to a single plane, then push it inward. This gives a much cleaner
        # visible separation than offsetting a noisy selected patch vertex-by-vertex.
        projected = top_points - np.outer((top_points - center) @ normal, normal)
        bottom_points = projected - normal * float(extrude_depth)

        wall_base = len(wall_pts)
        wall_pts.extend(top_points)
        wall_pts.extend(bottom_points)
        n = len(top_points)

        for i in range(n):
            j = (i + 1) % n
            top_i = wall_base + i
            top_j = wall_base + j
            bot_i = wall_base + n + i
            bot_j = wall_base + n + j
            wall_faces.extend([3, top_i, top_j, bot_i])
            wall_faces.extend([3, top_j, bot_j, bot_i])

        cap = _triangulate_cap(bottom_points, normal)
        if cap.n_cells > 0:
            cap_meshes.append(cap)

    walls_mesh = pv.PolyData(np.asarray(wall_pts), np.asarray(wall_faces)).clean().triangulate() if wall_pts else _empty_polydata()
    cap_mesh = cap_meshes[0]
    for extra_cap in cap_meshes[1:]:
        cap_mesh = cap_mesh.append_polydata(extra_cap)
    cap_mesh = cap_mesh.clean().triangulate() if cap_meshes else _empty_polydata()
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
