from pathlib import Path

from app_ui.codesee import icon_pack


class _BadStr:
    def __str__(self) -> str:  # pragma: no cover - intentional
        raise RuntimeError("boom")


def test_normalize_style_handles_invalid_types() -> None:
    assert icon_pack._normalize_style(None) == icon_pack.ICON_STYLE_COLOR
    assert icon_pack._normalize_style(" MONO ") == icon_pack.ICON_STYLE_MONO
    assert icon_pack._normalize_style("weird") == icon_pack.ICON_STYLE_COLOR
    assert icon_pack._normalize_style(_BadStr()) == icon_pack.ICON_STYLE_COLOR
    assert icon_pack._normalize_style(Path("mono")) == icon_pack.ICON_STYLE_MONO
