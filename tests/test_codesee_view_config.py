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
        facet_scope="peek_graph",
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
    assert loaded.facet_settings.facet_scope == "peek_graph"


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
            "facet_scope": "invalid_scope",
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
    assert loaded.facet_settings.facet_scope == "selected"


def test_facet_settings_missing_scope_defaults_selected(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(view_config, "_settings_path", lambda _wid: settings_path)
    payload = {
        "pulse_settings": view_config._pulse_settings_to_dict(view_config.default_pulse_settings()),
        "facet_settings": {
            "density": "standard",
            "enabled": {"deps": True},
            "show_in_normal_view": True,
            "show_in_peek_view": True,
        },
    }
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = view_config.load_view_config("ws", "atlas")
    assert loaded.facet_settings.facet_scope == "selected"


def test_monitor_settings_round_trip_and_defaults(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(view_config, "_settings_path", lambda _wid: settings_path)

    config = view_config.default_view_config("atlas")
    config.monitor_enabled = True
    config.monitor_follow_last_trace = False
    config.monitor_show_edge_path = False
    config.trail_focus_enabled = True
    config.inactive_node_opacity = 0.33
    config.inactive_edge_opacity = 0.15
    config.monitor_border_px = 4
    view_config.save_view_config("ws", config, last_lens_id="atlas")

    loaded = view_config.load_view_config("ws", "atlas")
    assert loaded.monitor_enabled is True
    assert loaded.monitor_follow_last_trace is False
    assert loaded.monitor_show_edge_path is False
    assert loaded.trail_focus_enabled is True
    assert loaded.inactive_node_opacity == 0.33
    assert loaded.inactive_edge_opacity == 0.15
    assert loaded.monitor_border_px == 4

    # Backward-compatible defaults when monitor keys are missing from settings.
    raw = json.loads(settings_path.read_text(encoding="utf-8"))
    raw.pop("monitor_enabled", None)
    raw.pop("monitor_follow_last_trace", None)
    raw.pop("monitor_show_edge_path", None)
    raw.pop("trail_focus_enabled", None)
    raw.pop("inactive_node_opacity", None)
    raw.pop("inactive_edge_opacity", None)
    raw.pop("monitor_border_px", None)
    settings_path.write_text(json.dumps(raw), encoding="utf-8")
    loaded_defaults = view_config.load_view_config("ws", "atlas")
    assert loaded_defaults.monitor_enabled is False
    assert loaded_defaults.monitor_follow_last_trace is True
    assert loaded_defaults.monitor_show_edge_path is True
    assert loaded_defaults.trail_focus_enabled is False
    assert loaded_defaults.inactive_node_opacity == 0.40
    assert loaded_defaults.inactive_edge_opacity == 0.20
    assert loaded_defaults.monitor_border_px == 2


def test_monitor_settings_apply_via_preset() -> None:
    config = view_config.default_view_config("atlas")
    preset = {
        "monitor_enabled": True,
        "monitor_follow_last_trace": False,
        "monitor_show_edge_path": False,
        "trail_focus_enabled": True,
        "inactive_node_opacity": 0.28,
        "inactive_edge_opacity": 0.12,
        "monitor_border_px": 5,
    }
    updated = view_config.apply_view_preset(config, preset)
    assert updated.monitor_enabled is True
    assert updated.monitor_follow_last_trace is False
    assert updated.monitor_show_edge_path is False
    assert updated.trail_focus_enabled is True
    assert updated.inactive_node_opacity == 0.28
    assert updated.inactive_edge_opacity == 0.12
    assert updated.monitor_border_px == 5


def test_trail_focus_settings_clamp(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(view_config, "_settings_path", lambda _wid: settings_path)
    payload = {
        "trail_focus_enabled": True,
        "inactive_node_opacity": -3.0,
        "inactive_edge_opacity": 99.0,
        "monitor_border_px": 100,
    }
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = view_config.load_view_config("ws", "atlas")
    assert loaded.trail_focus_enabled is True
    assert loaded.inactive_node_opacity == 0.10
    assert loaded.inactive_edge_opacity == 1.00
    assert loaded.monitor_border_px == 6
