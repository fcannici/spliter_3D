from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pyvista as pv

from .mesh_io import validate_polydata


@dataclass(frozen=True)
class BoundaryData:
    """Topological boundary information for a selected face set."""

    faces: np.ndarray
    selected_faces: tuple[int, ...]
    selected_vertices: tuple[int, ...]
    boundary_edges: tuple[tuple[int, int], ...]
    boundary_loops: tuple[tuple[int, ...], ...]


def triangular_faces(mesh: pv.PolyData) -> np.ndarray:
    """Return an ``(n, 3)`` int array for a triangular PyVista PolyData."""
    validate_polydata(mesh)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if len(faces) % 4 != 0:
        raise ValueError("La malla tiene una tabla de caras inválida.")
    reshaped = faces.reshape((-1, 4))
    if np.any(reshaped[:, 0] != 3):
        raise ValueError("La operación requiere una malla triangulada.")
    return reshaped[:, 1:]


def valid_selected_faces(mesh: pv.PolyData, selected_cells: Iterable[int]) -> tuple[int, ...]:
    """Normalize and validate selected face ids."""
    validate_polydata(mesh)
    selected = tuple(sorted({int(cell) for cell in selected_cells if 0 <= int(cell) < mesh.n_cells}))
    if not selected:
        raise ValueError("La selección no contiene caras válidas.")
    if len(selected) >= mesh.n_cells:
        raise ValueError("No se puede extraer el 100% de la malla como insert.")
    return selected


def _face_edges(face: np.ndarray) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    a, b, c = (int(face[0]), int(face[1]), int(face[2]))
    return tuple(tuple(sorted(edge)) for edge in ((a, b), (b, c), (c, a)))  # type: ignore[return-value]


def chain_boundary_loops(boundary_edges: Iterable[tuple[int, int]]) -> tuple[tuple[int, ...], ...]:
    """Chain unoriented boundary edges into closed vertex loops.

    Raises when the boundary is open or branches. Multiple closed loops are
    allowed because selected regions can have holes, but downstream operations
    may decide to reject them.
    """
    edges = {tuple(sorted((int(a), int(b)))) for a, b in boundary_edges}
    if not edges:
        raise ValueError("La selección no tiene boundary; no se puede crear un insert.")

    adjacency: dict[int, list[int]] = defaultdict(list)
    for a, b in edges:
        adjacency[a].append(b)
        adjacency[b].append(a)

    bad_vertices = [vertex for vertex, neighbors in adjacency.items() if len(neighbors) != 2]
    if bad_vertices:
        raise ValueError("El boundary de la selección está abierto o tiene ramificaciones.")

    loops: list[tuple[int, ...]] = []
    remaining = set(edges)

    while remaining:
        start_edge = next(iter(remaining))
        start, current = start_edge
        loop = [start]
        previous = start

        while True:
            loop.append(current)
            edge = tuple(sorted((previous, current)))
            remaining.discard(edge)

            neighbors = adjacency[current]
            next_vertex = neighbors[0] if neighbors[1] == previous else neighbors[1]
            previous, current = current, next_vertex

            if current == start:
                remaining.discard(tuple(sorted((previous, current))))
                break
            if len(loop) > len(edges) + 1:
                raise ValueError("No se pudo cerrar el boundary de la selección.")

        if len(loop) < 3:
            raise ValueError("El boundary de la selección es demasiado pequeño.")
        loops.append(tuple(loop))

    return tuple(loops)


def boundary_from_selection(mesh: pv.PolyData, selected_cells: Iterable[int]) -> BoundaryData:
    """Compute selected vertices, boundary edges and closed boundary loops."""
    faces = triangular_faces(mesh)
    selected = valid_selected_faces(mesh, selected_cells)
    selected_set = set(selected)

    edge_counts: Counter[tuple[int, int]] = Counter()
    selected_vertices: set[int] = set()

    for face_id in selected:
        face = faces[face_id]
        selected_vertices.update(int(v) for v in face)
        edge_counts.update(_face_edges(face))

    boundary_edges = tuple(sorted(edge for edge, count in edge_counts.items() if count == 1))
    boundary_loops = chain_boundary_loops(boundary_edges)

    return BoundaryData(
        faces=faces,
        selected_faces=selected,
        selected_vertices=tuple(sorted(selected_vertices)),
        boundary_edges=boundary_edges,
        boundary_loops=boundary_loops,
    )
