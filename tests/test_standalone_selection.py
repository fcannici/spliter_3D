from split3r_standalone.selection import PaintSelectionState, SmartPaintParams, smart_paint_expand


def line_adjacency(n: int, angle: float = 0.01):
    adj = {i: [] for i in range(n)}
    for i in range(n - 1):
        adj[i].append((i + 1, angle))
        adj[i + 1].append((i, angle))
    return adj


def test_include_exclude_marks_are_exclusive():
    state = PaintSelectionState()
    state.mark_include({1, 2})
    state.mark_exclude({2, 3})
    assert state.include_faces == {1}
    assert state.exclude_faces == {2, 3}


def test_smart_expand_respects_exclude_buffer():
    state = PaintSelectionState(include_faces={0}, exclude_faces={4})
    selected = smart_paint_expand(
        state,
        line_adjacency(7),
        SmartPaintParams(max_angle_degrees=30, exclude_buffer_rings=1),
    )
    assert selected == {0, 1, 2}
    assert 3 not in selected  # one-ring buffer around excluded face 4
    assert 4 not in selected


def test_smart_expand_stops_at_angle_boundary():
    adj = {
        0: [(1, 0.01)],
        1: [(0, 0.01), (2, 1.0)],
        2: [(1, 1.0)],
    }
    state = PaintSelectionState(include_faces={0})
    selected = smart_paint_expand(state, adj, SmartPaintParams(max_angle_degrees=20, exclude_buffer_rings=0))
    assert selected == {0, 1}
