from __future__ import annotations

from collections import defaultdict, deque

import numpy as np
import pyvista as pv
from scipy.spatial import Delaunay

from .mesh_io import polydata_to_trimesh, remove_triangle_artifacts, trimesh_to_polydata, validate_polydata

_ORIGINAL_CELL_ID = "_split3r_original_cell_id"
_SELECTION_CLOSING_STEPS = 5
_SELECTION_OPENING_STEPS = 5
_MIN_OPENED_SELECTION_RATIO = 0.12


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


def _cell_edge_adjacency(mesh: pv.PolyData) -> list[set[int]]:
    """Return cell neighbors that share a full polygon edge.

    Point-only adjacency is too permissive for scanned meshes: teeth/noise can touch the
    selected patch at one vertex and then survive as long black/cyan hairs. Edge adjacency
    lets us run a small morphological opening that removes those thin appendages while
    preserving the main selected island.
    """
    adjacency = [set() for _ in range(mesh.n_cells)]
    edge_to_cells: dict[tuple[int, int], list[int]] = defaultdict(list)

    faces = np.asarray(mesh.faces, dtype=np.int64)
    cursor = 0
    for cell_id in range(mesh.n_cells):
        n_points = int(faces[cursor])
        point_ids = faces[cursor + 1 : cursor + 1 + n_points]
        cursor += n_points + 1
        if n_points < 2:
            continue
        for i in range(n_points):
            a = int(point_ids[i])
            b = int(point_ids[(i + 1) % n_points])
            if a == b:
                continue
            edge_to_cells[tuple(sorted((a, b)))].append(cell_id)

    for cells in edge_to_cells.values():
        if len(cells) < 2:
            continue
        for i, cell_a in enumerate(cells):
            for cell_b in cells[i + 1 :]:
                adjacency[cell_a].add(cell_b)
                adjacency[cell_b].add(cell_a)
    return adjacency


def _largest_cell_component(cells: set[int], adjacency: list[set[int]]) -> set[int]:
    if not cells:
        return set()

    remaining = set(cells)
    largest: set[int] = set()
    while remaining:
        start = remaining.pop()
        component = {start}
        queue: deque[int] = deque([start])
        while queue:
            cell = queue.popleft()
            for neighbor in adjacency[cell]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        if len(component) > len(largest):
            largest = component
    return largest


def _close_selection_holes(cells: set[int], adjacency: list[set[int]], steps: int = _SELECTION_CLOSING_STEPS) -> set[int]:
    """Fill small fully enclosed misses inside the brush selection.

    In the captures, many curtains come from inner boundary loops: the brush selected a broad
    patch but skipped tiny strips/triangles inside it, so the extractor built vertical walls
    around those misses. We fill only small complement components; the large outside component
    remains untouched, so the selected silhouette does not grow uncontrollably.
    """
    closed = set(cells)
    if not closed:
        return closed

    all_cells = set(range(len(adjacency)))
    max_hole_size = max(24, min(600, int(len(closed) * 0.18)))

    for _ in range(steps):
        unselected = all_cells - closed
        seen: set[int] = set()
        additions: set[int] = set()

        for start in list(unselected):
            if start in seen:
                continue
            component = {start}
            seen.add(start)
            queue: deque[int] = deque([start])
            touches_selection = False
            too_large = False

            while queue:
                cell = queue.popleft()
                for neighbor in adjacency[cell]:
                    if neighbor in closed:
                        touches_selection = True
                    elif neighbor not in seen:
                        seen.add(neighbor)
                        component.add(neighbor)
                        if len(component) > max_hole_size:
                            too_large = True
                        queue.append(neighbor)

            if touches_selection and not too_large:
                additions.update(component)

        if not additions:
            break
        closed.update(additions)
    return closed


def _open_selection(cells: set[int], adjacency: list[set[int]], steps: int = _SELECTION_OPENING_STEPS) -> set[int]:
    """Remove narrow selected tendrils before building plug/socket geometry.

    The visual artifacts in the screenshots are caused less by the floor triangulation now and
    more by brush selections that include very thin connected strips. A morphology-style opening
    erodes the selection by a few edge-neighbor layers, keeps the largest stable core, and dilates
    it back inside the original selection. Thin hairs disappear because they have no surviving core.
    """
    original = set(cells)
    if len(original) < 20:
        return original

    opened = set(original)
    for _ in range(steps):
        eroded = {
            cell
            for cell in opened
            if sum((neighbor in opened) for neighbor in adjacency[cell]) >= max(2, min(3, len(adjacency[cell])))
        }
        if len(eroded) < max(8, int(len(original) * _MIN_OPENED_SELECTION_RATIO)):
            return original
        opened = eroded

    opened = _largest_cell_component(opened, adjacency)
    if len(opened) < max(8, int(len(original) * _MIN_OPENED_SELECTION_RATIO)):
        return original

    for _ in range(steps):
        expanded = set(opened)
        for cell in opened:
            expanded.update(neighbor for neighbor in adjacency[cell] if neighbor in original)
        opened = expanded

    return opened if len(opened) >= max(8, int(len(original) * _MIN_OPENED_SELECTION_RATIO)) else original


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

    # Keep only the dominant outer cut loop. Secondary loops are usually holes left by
    # imperfect brush selection on teeth/scan noise; creating walls around them produces the
    # visible curtains/fins shown in the QA captures.
    loop_data = [max(loop_data, key=lambda item: item[0])]
    if loop_data[0][1].shape[0] < 8:
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


def _boundary_edge_count(mesh: pv.PolyData) -> int:
    if mesh.n_cells == 0:
        return 0
    edges = mesh.extract_feature_edges(
        boundary_edges=True,
        non_manifold_edges=False,
        feature_edges=False,
        manifold_edges=False,
    )
    return int(edges.n_cells)


def _repair_extracted_mesh(mesh: pv.PolyData, extrude_depth: float) -> pv.PolyData:
    """Final pass to remove source/output needles and cap small extraction cracks.

    Earlier versions skipped suspicious wall edges, which reduced needles but left visible open
    holes. This pass keeps the full wall loop, then removes only extreme sliver triangles and
    fills small boundary cracks left by imperfect scan topology. Large model openings are not
    targeted; the hole size is tied to extraction thickness.
    """
    if mesh.n_cells == 0:
        return mesh

    repaired = mesh.clean().triangulate()
    try:
        repaired = trimesh_to_polydata(remove_triangle_artifacts(polydata_to_trimesh(repaired))).clean().triangulate()
    except Exception:
        repaired = repaired.clean().triangulate()

    hole_size = max(2.5, float(extrude_depth) * 4.0)
    try:
        filled = repaired.fill_holes(hole_size=hole_size).clean().triangulate()
        if filled.n_cells > 0 and _boundary_edge_count(filled) <= _boundary_edge_count(repaired):
            repaired = filled
    except Exception:
        pass

    return repaired.clean().triangulate()


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

    # Remove narrow brush tendrils before extracting. This prevents vertical hairs/fins in both
    # the grey socket and the cyan plug while keeping the dominant selected patch.
    adjacency = _cell_edge_adjacency(current_mesh)
    valid_selection = _largest_cell_component(valid_selection, adjacency)
    valid_selection = _close_selection_holes(valid_selection, adjacency)
    opened_selection = _open_selection(valid_selection, adjacency)
    if opened_selection:
        valid_selection = _close_selection_holes(opened_selection, adjacency)

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

    plug_mesh = _repair_extracted_mesh(plug_mesh, extrude_depth)
    body_mesh = _repair_extracted_mesh(body_mesh, extrude_depth)

    for mesh in (plug_mesh, body_mesh):
        if _ORIGINAL_CELL_ID in mesh.cell_data:
            del mesh.cell_data[_ORIGINAL_CELL_ID]

    validate_polydata(plug_mesh)
    validate_polydata(body_mesh)
    return plug_mesh, body_mesh
