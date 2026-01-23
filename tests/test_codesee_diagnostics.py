from app_ui.codesee import diagnostics


def test_format_codesee_diagnostics_includes_keys() -> None:
    snapshot = {
        "lens": "Atlas",
        "lens_id": "atlas",
        "source": "Demo",
        "build_version": "V0",
        "build_id": "deadbeef",
    }
    text = diagnostics.format_codesee_diagnostics(snapshot, ["log line"])
    assert "CodeSee Diagnostics" in text
    assert "Lens:" in text
    assert "Source:" in text
