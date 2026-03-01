from __future__ import annotations

from PyQt6 import QtWidgets

from app_ui import ui_scale


_APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_clamp_scale_percent_accepts_and_bounds_values() -> None:
    assert ui_scale.clamp_scale_percent("125%") == 125
    assert ui_scale.clamp_scale_percent("40") == 50
    assert ui_scale.clamp_scale_percent("1000") == 250
    assert ui_scale.clamp_scale_percent("bad") == 100


def test_apply_to_app_rescales_top_level_window_geometry() -> None:
    window = QtWidgets.QMainWindow()
    window.resize(400, 300)
    window.setMinimumSize(200, 150)
    window.show()
    _APP.processEvents()
    try:
        ui_scale.apply_to_app(_APP, ui_scale.UiScaleConfig(scale_percent=100, density="comfortable"))
        before = window.size()
        ui_scale.apply_to_app(_APP, ui_scale.UiScaleConfig(scale_percent=150, density="comfortable"))
        grown = window.size()
        assert grown.width() >= int(round(before.width() * 1.4))
        assert grown.height() >= int(round(before.height() * 1.4))

        ui_scale.apply_to_app(_APP, ui_scale.UiScaleConfig(scale_percent=80, density="comfortable"))
        shrunk = window.size()
        assert shrunk.width() <= int(round(grown.width() * 0.8)) + 2
        assert shrunk.height() <= int(round(grown.height() * 0.8)) + 2
    finally:
        window.close()
        _APP.processEvents()
