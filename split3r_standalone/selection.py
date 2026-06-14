from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np


@dataclass
class PaintSelectionState:
    """Face-mark state for Split3r Smart Paint.

    include_faces are positive seeds/selected faces. exclude_faces are protected body faces
    that the automatic expansion must not enter. The split between both sets mirrors the
    workflow observed in Split3r/Bambu-style painting: paint what belongs, protect what does
    not, then expand between those constraints.
    """

    include_faces: set[int] = field(default_factory=set)
    exclude_faces: set[int] = field(default_factory=set)

    def clear(self) -> None:
        self.include_faces.clear()
        self.exclude_faces.clear()

    def mark_include(self, faces: set[int]) -> None:
        self.exclude_faces.difference_update(faces)
        self.include_faces.update(faces)

    def mark_exclude(self, faces: set[int]) -> None:
        self.include_faces.difference_update(faces)
        self.exclude_faces.update(faces)

    def erase(self, faces: set[int]) -> None:
        self.include_faces.difference_update(faces)
        self.exclude_faces.difference_update(faces)


@dataclass(frozen=True)
class SmartPaintParams:
    max_angle_degrees: float = 22.0
    max_faces: int = 25000
    exclude_buffer_rings: int = 1


def _exclude_buffer(exclude_faces: set[int], adjacency: dict[int, list[tuple[int, float]]], rings: int) -> set[int]:
    if rings <= 0 or not exclude_faces:
        return set(exclude_faces)
    blocked = set(exclude_faces)
    frontier = set(exclude_faces)
    for _ in range(rings):
        next_frontier: set[int] = set()
        for face in frontier:
            for neighbor, _angle in adjacency.get(face, []):
                if neighbor not in blocked:
                    blocked.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = next_frontier
        if not frontier:
            break
    return blocked


def smart_paint_expand(
    state: PaintSelectionState,
    adjacency: dict[int, list[tuple[int, float]]],
    params: SmartPaintParams | None = None,
) -> set[int]:
    """Expand positive seeds while respecting negative/protected marks.

    This is intentionally conservative for the first standalone MVP. It uses a queue-based
    region grow constrained by local dihedral angle and an exclusion buffer. That gives us a
    Bambu/Split3r-like interaction model now, while leaving room to replace the internals
    with Dijkstra/graph-cut costs later without changing the UI state model.
    """
    params = params or SmartPaintParams()
    if not state.include_faces:
        return set()

    threshold = np.radians(params.max_angle_degrees)
    blocked = _exclude_buffer(state.exclude_faces, adjacency, params.exclude_buffer_rings)
    selected = set(state.include_faces) - blocked
    queue: deque[int] = deque(selected)

    while queue and len(selected) < params.max_faces:
        current = queue.popleft()
        for neighbor, angle in adjacency.get(current, []):
            if neighbor in selected or neighbor in blocked:
                continue
            if angle > threshold:
                continue
            selected.add(neighbor)
            queue.append(neighbor)
            if len(selected) >= params.max_faces:
                break

    state.include_faces = selected
    return selected
