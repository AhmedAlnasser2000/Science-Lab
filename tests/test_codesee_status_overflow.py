from app_ui.codesee.canvas.items import format_overflow


def test_format_overflow_caps() -> None:
    assert format_overflow(5) == "5+"
    assert format_overflow(17) == "17+"
    assert format_overflow(99) == "99+"
    assert format_overflow(140) == "99+"


def test_format_overflow_small_values() -> None:
    assert format_overflow(0) == ""
    assert format_overflow(1) == ""
    assert format_overflow(4) == ""


def test_format_overflow_thresholds() -> None:
    assert format_overflow(5) == "5+"
    assert format_overflow(8) == "8+"
