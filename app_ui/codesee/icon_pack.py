from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

ICON_STYLE_AUTO = "auto"
ICON_STYLE_COLOR = "color"
ICON_STYLE_MONO = "mono"


def resolve_icon_path(key: str, style: str) -> Optional[Path]:
    base = Path(__file__).resolve().parent / "assets" / "icons" / style
    path = base / f"{key}.svg"
    if path.exists():
        return path
    return None


def resolve_style(style: str, reduced_motion: bool) -> str:
    if style == ICON_STYLE_AUTO:
        return ICON_STYLE_MONO if reduced_motion else ICON_STYLE_COLOR
    if style in (ICON_STYLE_COLOR, ICON_STYLE_MONO):
        return style
    return ICON_STYLE_COLOR


def load_style(workspace_id: str) -> str:
    settings = _load_settings(workspace_id)
    style = settings.get("icon_style")
    if style in (ICON_STYLE_AUTO, ICON_STYLE_COLOR, ICON_STYLE_MONO):
        return style
    return ICON_STYLE_AUTO


def save_style(workspace_id: str, style: str) -> None:
    if style not in (ICON_STYLE_AUTO, ICON_STYLE_COLOR, ICON_STYLE_MONO):
        return
    settings = _load_settings(workspace_id)
    settings["icon_style"] = style
    _save_settings(workspace_id, settings)


def _settings_path(workspace_id: str) -> Path:
    safe_id = str(workspace_id or "default").strip() or "default"
    return Path("data") / "workspaces" / safe_id / "codesee" / "settings.json"


def _load_settings(workspace_id: str) -> dict:
    path = _settings_path(workspace_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_settings(workspace_id: str, settings: dict) -> None:
    path = _settings_path(workspace_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        return
