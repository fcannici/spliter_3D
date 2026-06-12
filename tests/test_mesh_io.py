import numpy as np
import pyvista as pv

from app.mesh_io import polydata_to_trimesh, trimesh_to_polydata, validate_polydata


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
