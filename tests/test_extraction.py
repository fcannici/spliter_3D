import numpy as np
import pyvista as pv

from app.extraction import extract_plug_socket


def _cells_using_point(mesh: pv.PolyData, point_id: int) -> int:
    cells = mesh.faces.reshape((-1, 4))[:, 1:]
    return int(np.any(cells == point_id, axis=1).sum())


def test_extraction_repair_does_not_delete_unselected_thin_source_faces():
    """Bambu 3MF meshes can contain valid very thin faces.

    A previous repair pass reused the import artifact filter on the whole extracted body. That
    deleted unselected source triangles after extraction and made the model look broken globally.
    """
    angles = np.linspace(0, 2 * np.pi, 8, endpoint=False)
    selected_ring = np.column_stack((np.cos(angles), np.sin(angles), np.zeros(8)))
    points = np.vstack(
        [
            [[0.0, 0.0, 0.0]],
            selected_ring,
            [
                [3.0, 0.0, 0.0],
                [28.0, 0.0, 0.0],
                [3.01, 0.0, 0.0],
                [3.0, 1.0, 0.0],
                [4.0, 1.0, 0.0],
                [4.0, 0.0, 0.0],
            ],
        ]
    ).astype(float)

    faces: list[int] = []
    for i in range(8):
        faces.extend([3, 0, 1 + i, 1 + ((i + 1) % 8)])
    faces.extend([3, 9, 10, 11])  # valid but very thin unselected source face
    faces.extend([3, 9, 12, 13, 3, 9, 13, 14])  # normal unselected faces
    mesh = pv.PolyData(points, np.asarray(faces, dtype=np.int64)).triangulate()

    _plug, body = extract_plug_socket(mesh, set(range(8)), 1.0)

    far_point_id = int(np.argmax(body.points[:, 0]))
    assert body.points[far_point_id, 0] == 28.0
    assert _cells_using_point(body, far_point_id) >= 1
