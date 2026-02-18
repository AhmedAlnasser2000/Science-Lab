import json
import os
from pathlib import Path

from app_ui.codesee import view_config


def test_settings_path_safe_exists() -> None:
    path = view_config._settings_path("default")
    os.fspath(path)
    assert view_config._safe_exists(path) in (True, False)


def test_safe_workspace_id_non_str_defaults() -> None:
    assert view_config._safe_workspace_id(123) == "default"
    assert view_config._safe_workspace_id(b"") == "default"


def test_save_settings_sanitizes(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(view_config, "_settings_path", lambda _wid: settings_path)
    view_config._save_settings("ws", {"weird": Path("mono"), "ok": "yes"})
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert isinstance(data.get("weird"), (str, type(None)))
    assert data.get("ok") == "yes"


def test_facet_settings_round_trip(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(view_config, "_settings_path", lambda _wid: settings_path)

    config = view_config.default_view_config("atlas")
    config.facet_settings = view_config.FacetSettings(
        density="expanded",
        enabled={
            "deps": True,
            "packs": True,
            "entry_points": False,
            "logs": True,
            "activity": True,
            "spans": True,
            "runs": True,
            "errors": True,
            "signals": True,
        },
        show_in_normal_view=False,
        show_in_peek_view=True,
    )
    view_config.save_view_config("ws", config, last_lens_id="atlas")
    loaded = view_config.load_view_config("ws", "atlas")

    assert loaded.facet_settings.density == "expanded"
    assert loaded.facet_settings.show_in_normal_view is False
    assert loaded.facet_settings.show_in_peek_view is True
    assert loaded.facet_settings.enabled["logs"] is True
    assert loaded.facet_settings.enabled["entry_points"] is False


def test_facet_settings_unknown_density_and_keys_are_ignored(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(view_config, "_settings_path", lambda _wid: settings_path)
    payload = {
        "pulse_settings": view_config._pulse_settings_to_dict(view_config.default_pulse_settings()),
        "facet_settings": {
            "density": "strange",
            "enabled": {
                "deps": False,
                "unknown_facet": True,
            },
            "show_in_normal_view": True,
            "show_in_peek_view": False,
        },
    }
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = view_config.load_view_config("ws", "atlas")
    assert loaded.facet_settings.density == "minimal"
    assert "unknown_facet" not in loaded.facet_settings.enabled
    assert set(loaded.facet_settings.enabled.keys()) == set(view_config.FACET_KEYS)
    assert loaded.facet_settings.show_in_normal_view is True
    assert loaded.facet_settings.show_in_peek_view is False
