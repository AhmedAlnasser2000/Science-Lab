from PyQt6 import QtCore

from app_ui.codesee.screen import (
    _filter_lens_tiles,
    _lens_palette_lens_ids,
    lens_palette_dock_orientation,
)


def test_lens_palette_ids_unique_and_ordered() -> None:
    ids = _lens_palette_lens_ids()
    assert ids, "lens palette ids should not be empty"
    assert len(ids) == len(set(ids)), "lens palette ids must be unique"
    assert ids[0] != ids[-1], "palette order should be stable and non-degenerate"


def test_filter_lens_tiles_case_insensitive() -> None:
    tiles = [
        {"id": "atlas", "title": "Atlas"},
        {"id": "platform", "title": "Platform"},
        {"id": "content", "title": "Content"},
        {"id": "bus", "title": "Bus"},
        {"id": "extensibility", "title": "Extensibility/Dependencies"},
    ]
    filtered = _filter_lens_tiles("pla", tiles)
    assert [tile["id"] for tile in filtered] == ["platform"]
    assert _filter_lens_tiles("", tiles) == tiles
    assert _filter_lens_tiles("zz", tiles) == []


def test_lens_palette_dock_orientation() -> None:
    assert (
        lens_palette_dock_orientation(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        == QtCore.Qt.Orientation.Horizontal
    )
    assert (
        lens_palette_dock_orientation(QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        == QtCore.Qt.Orientation.Horizontal
    )
    assert (
        lens_palette_dock_orientation(QtCore.Qt.DockWidgetArea.TopDockWidgetArea)
        == QtCore.Qt.Orientation.Vertical
    )
    assert (
        lens_palette_dock_orientation(QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        == QtCore.Qt.Orientation.Vertical
    )
    assert lens_palette_dock_orientation(QtCore.Qt.DockWidgetArea.NoDockWidgetArea) is None
