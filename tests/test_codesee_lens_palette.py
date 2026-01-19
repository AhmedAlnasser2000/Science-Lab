from app_ui.codesee.screen import _lens_palette_lens_ids


def test_lens_palette_ids_unique_and_ordered() -> None:
    ids = _lens_palette_lens_ids()
    assert ids, "lens palette ids should not be empty"
    assert len(ids) == len(set(ids)), "lens palette ids must be unique"
    assert ids[0] != ids[-1], "palette order should be stable and non-degenerate"
