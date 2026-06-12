from app.selection import build_adjacency_dict, compute_smart_shell_region


def test_compute_smart_shell_region_respects_angle_threshold():
    adj = build_adjacency_dict([(0, 1), (1, 2)], [0.1, 1.2])

    assert set(compute_smart_shell_region(0, adj, smart_angle_degrees=30)) == {0, 1}


def test_compute_smart_shell_region_handles_invalid_seed():
    assert compute_smart_shell_region(-1, {}, smart_angle_degrees=30) == []
