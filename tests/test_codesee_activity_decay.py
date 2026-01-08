from app_ui.codesee.canvas.scene import activity_alpha


def test_activity_alpha_linear() -> None:
    assert activity_alpha(0.0, fade_s=2.0, reduced_motion=False) == 1.0
    assert activity_alpha(2.0, fade_s=2.0, reduced_motion=False) == 0.0
    mid = activity_alpha(1.0, fade_s=2.0, reduced_motion=False)
    assert 0.49 <= mid <= 0.51
    earlier = activity_alpha(0.5, fade_s=2.0, reduced_motion=False)
    later = activity_alpha(1.5, fade_s=2.0, reduced_motion=False)
    assert earlier > later


def test_activity_alpha_reduced_motion() -> None:
    assert activity_alpha(0.5, fade_s=2.0, reduced_motion=True) == 1.0
    assert activity_alpha(1.1, fade_s=2.0, reduced_motion=True) == 0.0
