from app_ui.codesee.canvas.scene import _edge_progress


def test_edge_progress_clamp_and_reverse() -> None:
    assert _edge_progress(-0.5, False) == 0.0
    assert _edge_progress(1.5, False) == 1.0
    assert _edge_progress(0.25, False) == 0.25
    assert _edge_progress(0.25, True) == 0.75
    assert _edge_progress(-0.1, True) == 1.0
    assert _edge_progress(1.0, True) == 0.0
