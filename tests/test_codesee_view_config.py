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
