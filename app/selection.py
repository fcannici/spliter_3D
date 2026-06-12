from __future__ import annotations

from collections import deque
from typing import Iterable

import numpy as np


def build_adjacency_dict(face_adjacency: Iterable[tuple[int, int]], face_adjacency_angles: Iterable[float]) -> dict[int, list[tuple[int, float]]]:
    """Build a per-face adjacency map with edge angle metadata."""
    adj: dict[int, list[tuple[int, float]]] = {}
    for edge, angle in zip(face_adjacency, face_adjacency_angles):
        f1, f2 = int(edge[0]), int(edge[1])
        adj.setdefault(f1, []).append((f2, float(angle)))
        adj.setdefault(f2, []).append((f1, float(angle)))
    return adj


def compute_smart_shell_region(seed_face: int, adj_dict: dict[int, list[tuple[int, float]]], smart_angle_degrees: float) -> list[int]:
    """Flood-fill adjacent faces while the adjacency angle is below the tolerance."""
    if seed_face < 0:
        return []

    threshold_rad = np.radians(smart_angle_degrees)
    visited = {int(seed_face)}
    queue: deque[int] = deque([int(seed_face)])

    while queue:
        current = queue.popleft()
        for neighbor, angle in adj_dict.get(current, []):
            if neighbor not in visited and angle <= threshold_rad:
                visited.add(neighbor)
                queue.append(neighbor)

    return list(visited)
