from app_ui.codesee.screen import _filter_lens_tiles, _lens_palette_lens_ids


def test_lens_palette_ids_unique_and_ordered() -> None:
    ids = _lens_palette_lens_ids()
    assert ids, "lens palette ids should not be empty"
    assert len(ids) == len(set(ids)), "lens palette ids must be unique"
    assert ids[0] != ids[-1], "palette order should be stable and non-degenerate"


def test_filter_lens_tiles_case_insensitive() -> None:
    tiles = [
        {"id": "atlas", "title": "Atlas"},
        {"id": "content", "title": "Content"},
        {"id": "bus", "title": "Bus"},
    ]
    filtered = _filter_lens_tiles("at", tiles)
    assert [tile["id"] for tile in filtered] == ["atlas"]
