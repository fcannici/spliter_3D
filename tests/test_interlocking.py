import pyvista as pv
import pytest

from app.interlocking import create_interlocking_insert
from app.selection_boundary import boundary_from_selection, chain_boundary_loops


def _cube_top_face_selection():
    mesh = pv.Cube().triangulate().clean()
    centers = mesh.cell_centers().points
    max_z = centers[:, 2].max()
    selected = {idx for idx, point in enumerate(centers) if point[2] == max_z}
    return mesh, selected


def test_boundary_from_selection_detects_closed_cube_top_loop():
    mesh, selected = _cube_top_face_selection()

    boundary = boundary_from_selection(mesh, selected)

    assert len(boundary.boundary_edges) == 4
    assert len(boundary.boundary_loops) == 1
    assert len(boundary.boundary_loops[0]) == 4


def test_chain_boundary_loops_rejects_open_boundary():
    with pytest.raises(ValueError, match="abierto|ramificaciones"):
        chain_boundary_loops([(0, 1), (1, 2), (2, 3)])


def test_create_interlocking_insert_builds_insert_slot_and_body():
    mesh, selected = _cube_top_face_selection()

    result = create_interlocking_insert(mesh, selected, depth=0.25, clearance=0.05, backend="vtk")

    assert result.insert_mesh.n_cells > 0
    assert result.slot_cutter.n_cells > 0
    assert result.body_mesh.n_cells > 0
    assert result.insert_mesh.volume > 0
    assert result.slot_cutter.volume > result.insert_mesh.volume
    assert result.boolean_backend in {"vtk", "surface-fallback"}


def test_create_interlocking_insert_rejects_invalid_depth_and_clearance():
    mesh, selected = _cube_top_face_selection()

    with pytest.raises(ValueError, match="depth"):
        create_interlocking_insert(mesh, selected, depth=0, clearance=0.2)

    with pytest.raises(ValueError, match="clearance|buffer"):
        create_interlocking_insert(mesh, selected, depth=1, clearance=-0.1)
