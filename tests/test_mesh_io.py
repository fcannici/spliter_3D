import numpy as np
import pyvista as pv

import trimesh

from app.mesh_io import polydata_to_trimesh, remove_open_sheet_artifacts, remove_triangle_artifacts, trimesh_to_polydata, validate_polydata


def test_polydata_trimesh_roundtrip_triangle():
    mesh = pv.PolyData(
        np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float),
        np.array([3, 0, 1, 2]),
    )

    tm = polydata_to_trimesh(mesh)
    assert tm.faces.shape == (1, 3)

    pv_mesh = trimesh_to_polydata(tm)
    validate_polydata(pv_mesh)
    assert pv_mesh.n_cells == 1


def test_remove_triangle_artifacts_drops_needles_but_keeps_normal_faces():
    vertices = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
            [25, 0, 0],
            [0.01, 0.0, 0.0],
        ],
        dtype=float,
    )
    faces = np.array(
        [
            [0, 1, 2],  # normal triangle
            [0, 4, 5],  # extreme long/skinny needle
            [0, 2, 3],  # normal triangle
        ]
    )
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

    cleaned = remove_triangle_artifacts(mesh)

    assert len(cleaned.faces) == 2


def test_remove_open_sheet_artifacts_peels_small_non_bottom_sheet():
    vertices = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 1],
            [1, 1, 1],
            [0, 1, 1],
            [2, 0, 1],
            [2, 1, 1],
        ],
        dtype=float,
    )
    faces = np.array(
        [
            [0, 1, 2],
            [0, 2, 3],  # bottom open component, preserved
            [4, 5, 6],
            [4, 6, 7],  # small non-bottom open sheet, removed
            [5, 8, 9],
            [5, 9, 6],  # same small sheet extension, removed
        ]
    )
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

    cleaned = remove_open_sheet_artifacts(mesh)

    assert len(cleaned.faces) == 2
