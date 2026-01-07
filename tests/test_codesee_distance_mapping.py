from app_ui.codesee.canvas.scene import _build_cumdist, _distance_to_percent


def test_distance_mapping_polyline() -> None:
    points = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    cumdist, total = _build_cumdist(points)
    assert total == 20.0
    assert cumdist == [0.0, 10.0, 20.0]
    assert _distance_to_percent(cumdist, total, 0.0) == 0.0
    assert _distance_to_percent(cumdist, total, total) == 1.0
    mid = _distance_to_percent(cumdist, total, 10.0)
    assert abs(mid - 0.5) < 1e-6
    quarter = _distance_to_percent(cumdist, total, 5.0)
    assert abs(quarter - 0.25) < 1e-6
    three_quarter = _distance_to_percent(cumdist, total, 15.0)
    assert abs(three_quarter - 0.75) < 1e-6
