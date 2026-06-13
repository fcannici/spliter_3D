import pyvista as pv
import pytest

from app.extraction import extract_plug_socket


def _cube_top_face_selection():
    mesh = pv.Cube().triangulate()
    centers = mesh.cell_centers().points
    max_z = centers[:, 2].max()
    selected = {idx for idx, point in enumerate(centers) if point[2] == max_z}
    return mesh, selected


def test_extract_plug_socket_builds_buffered_socket_body():
    mesh, selected = _cube_top_face_selection()

    plug, body = extract_plug_socket(mesh, selected, extrude_depth=0.25, socket_clearance=0.2)

    assert plug.n_cells > 0
    assert body.n_cells > 0
    assert plug.bounds[5] == pytest.approx(mesh.bounds[5])
    assert body.volume < mesh.volume


def test_extract_plug_socket_rejects_negative_clearance():
    mesh, selected = _cube_top_face_selection()

    with pytest.raises(ValueError, match="buffer"):
        extract_plug_socket(mesh, selected, extrude_depth=0.25, socket_clearance=-0.1)
