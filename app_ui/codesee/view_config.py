from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .icon_pack import ICON_STYLE_AUTO
from .lenses import LENS_ATLAS


@dataclass
class ViewConfig:
    lens_id: str
    show_categories: Dict[str, bool] = field(default_factory=dict)
    show_badge_layers: Dict[str, bool] = field(default_factory=dict)
    quick_filters: Dict[str, bool] = field(default_factory=dict)
    icon_style: str = ICON_STYLE_AUTO
    node_theme: str = "neutral"
    pulse_settings: "PulseSettings" = field(default_factory=lambda: default_pulse_settings())
    span_stuck_seconds: int = 10
    live_enabled: bool = False


@dataclass
class PulseSettings:
    travel_speed_px_per_s: int = 900
    travel_duration_ms: int = 0
    arrive_linger_ms: int = 300
    fade_ms: int = 500
    pulse_duration_ms: int = 650
    pulse_radius_px: int = 10
    pulse_alpha: float = 0.7
    pulse_min_alpha: float = 0.18
    intensity_multiplier: float = 1.0
    fade_curve: str = "linear"
    trail_length: int = 3
    trail_spacing_ms: int = 70
    max_concurrent_signals: int = 6
    tint_active_spans: bool = False
    topic_enabled: Dict[str, bool] = field(default_factory=lambda: _default_pulse_topics())


_CATEGORY_DEFAULTS = {
    "Workspace": True,
    "Pack": True,
    "Block": True,
    "Subcomponent": True,
    "Artifact": True,
    "Extension": True,
    "Plugin": True,
    "Lab": True,
    "Topic": True,
    "Unit": True,
    "Lesson": True,
    "Activity": True,
    "System": True,
}

_BADGE_LAYER_DEFAULTS = {
    "health": True,
    "correctness": True,
    "connectivity": True,
    "policy": True,
    "perf": True,
    "activity": True,
}

_QUICK_FILTER_DEFAULTS = {
    "only_errors": False,
    "only_failures": False,
    "only_expecting": False,
    "only_mismatches": False,
    "only_active": False,
    "only_stuck": False,
}


def default_view_config(lens_id: str, *, icon_style: str = ICON_STYLE_AUTO) -> ViewConfig:
    return ViewConfig(
        lens_id=lens_id or LENS_ATLAS,
        show_categories=_CATEGORY_DEFAULTS.copy(),
        show_badge_layers=_BADGE_LAYER_DEFAULTS.copy(),
        quick_filters=_QUICK_FILTER_DEFAULTS.copy(),
        icon_style=icon_style,
        node_theme="neutral",
        pulse_settings=default_pulse_settings(),
        span_stuck_seconds=10,
    )


def default_pulse_settings() -> PulseSettings:
    return PulseSettings()


def reset_to_defaults(lens_id: str, *, icon_style: str = ICON_STYLE_AUTO) -> ViewConfig:
    return default_view_config(lens_id, icon_style=icon_style)


def is_filtered(config: ViewConfig) -> bool:
    if any(not value for value in config.show_categories.values()):
        return True
    if any(not value for value in config.show_badge_layers.values()):
        return True
    if any(config.quick_filters.values()):
        return True
    return False


def build_active_filter_chips(config: ViewConfig) -> list[str]:
    chips: list[str] = []
    for key, value in config.quick_filters.items():
        if value:
            label = key.replace("_", " ").title()
            chips.append(label)
    for category, value in config.show_categories.items():
        if not value:
            chips.append(f"Hide {category}")
    for layer, value in config.show_badge_layers.items():
        if not value:
            chips.append(f"Hide {layer.title()} Badges")
    return chips


def load_window_geometry(workspace_id: str) -> Optional[str]:
    settings = _load_settings(workspace_id)
    geometry = settings.get("codesee_window_geometry")
    if isinstance(geometry, str) and geometry:
        return geometry
    return None


def load_lens_palette_state(workspace_id: str) -> Dict[str, object]:
    settings = _load_settings(workspace_id)
    raw = settings.get("lens_palette")
    if not isinstance(raw, dict):
        raw = {}
    recent = raw.get("recent", [])
    if not isinstance(recent, list):
        recent = []
    return {
        "pinned": bool(raw.get("pinned", False)),
        "recent": [str(item) for item in recent if isinstance(item, str)],
    }


def save_lens_palette_state(
    workspace_id: str, *, pinned: bool, recent: Optional[list[str]] = None
) -> None:
    settings = _load_settings(workspace_id)
    raw = settings.get("lens_palette")
    if not isinstance(raw, dict):
        raw = {}
    raw["pinned"] = bool(pinned)
    if recent is not None:
        raw["recent"] = [str(item) for item in recent if isinstance(item, str)]
    settings["lens_palette"] = raw
    _save_settings(workspace_id, settings)


def save_window_geometry(workspace_id: str, geometry: str) -> None:
    if not geometry:
        return
    settings = _load_settings(workspace_id)
    settings["codesee_window_geometry"] = geometry
    _save_settings(workspace_id, settings)


def load_view_config(workspace_id: str, lens_id: str) -> ViewConfig:
    settings = _load_settings(workspace_id)
    icon_style = settings.get("icon_style") or ICON_STYLE_AUTO
    lens_id = lens_id or settings.get("last_lens_id") or LENS_ATLAS
    raw_lenses = settings.get("lenses") if isinstance(settings.get("lenses"), dict) else {}
    raw_config = raw_lenses.get(lens_id) if isinstance(raw_lenses, dict) else {}
    if not isinstance(raw_config, dict):
        raw_config = {}
    config = default_view_config(lens_id, icon_style=icon_style)
    config.show_categories = _merge_bool_map(config.show_categories, raw_config.get("show_categories"))
    config.show_badge_layers = _merge_bool_map(config.show_badge_layers, raw_config.get("show_badge_layers"))
    config.quick_filters = _merge_bool_map(config.quick_filters, raw_config.get("quick_filters"))
    config.icon_style = icon_style
    raw_theme = settings.get("node_theme")
    if isinstance(raw_theme, str) and raw_theme.strip():
        config.node_theme = raw_theme.strip()
    config.pulse_settings = _merge_pulse_settings(config.pulse_settings, settings.get("pulse_settings"))
    config.span_stuck_seconds = _merge_int_setting(settings.get("span_stuck_seconds"), config.span_stuck_seconds)
    config.live_enabled = bool(settings.get("live_enabled", False))
    return config


def load_last_lens_id(workspace_id: str) -> str:
    settings = _load_settings(workspace_id)
    lens_id = settings.get("last_lens_id")
    return lens_id if isinstance(lens_id, str) and lens_id else LENS_ATLAS


def save_view_config(
    workspace_id: str,
    config: ViewConfig,
    *,
    last_lens_id: Optional[str] = None,
    icon_style: Optional[str] = None,
) -> None:
    settings = _load_settings(workspace_id)
    if icon_style:
        settings["icon_style"] = icon_style
    if last_lens_id:
        settings["last_lens_id"] = last_lens_id
    if config.node_theme:
        settings["node_theme"] = config.node_theme
    settings["pulse_settings"] = _pulse_settings_to_dict(config.pulse_settings)
    settings["span_stuck_seconds"] = int(config.span_stuck_seconds)
    settings["live_enabled"] = bool(config.live_enabled)
    lenses = settings.get("lenses")
    if not isinstance(lenses, dict):
        lenses = {}
    lenses[config.lens_id] = {
        "show_categories": dict(config.show_categories),
        "show_badge_layers": dict(config.show_badge_layers),
        "quick_filters": dict(config.quick_filters),
    }
    settings["lenses"] = lenses
    _save_settings(workspace_id, settings)


def build_view_preset(
    config: ViewConfig,
    *,
    lens_id: str,
    icon_style: str,
    node_theme: str,
) -> Dict[str, object]:
    return {
        "lens_id": lens_id,
        "icon_style": icon_style,
        "node_theme": node_theme,
        "show_categories": dict(config.show_categories),
        "show_badge_layers": dict(config.show_badge_layers),
        "quick_filters": dict(config.quick_filters),
        "pulse_settings": _pulse_settings_to_dict(config.pulse_settings),
        "span_stuck_seconds": int(config.span_stuck_seconds),
        "live_enabled": bool(config.live_enabled),
    }


def apply_view_preset(config: ViewConfig, preset: Dict[str, object]) -> ViewConfig:
    config.show_categories = _merge_bool_map(config.show_categories, preset.get("show_categories"))
    config.show_badge_layers = _merge_bool_map(config.show_badge_layers, preset.get("show_badge_layers"))
    config.quick_filters = _merge_bool_map(config.quick_filters, preset.get("quick_filters"))
    config.pulse_settings = _merge_pulse_settings(config.pulse_settings, preset.get("pulse_settings"))
    config.span_stuck_seconds = _merge_int_setting(
        preset.get("span_stuck_seconds"),
        config.span_stuck_seconds,
    )
    config.live_enabled = bool(preset.get("live_enabled", config.live_enabled))
    return config


def load_view_presets(workspace_id: str) -> Dict[str, Dict]:
    settings = _load_settings(workspace_id)
    presets = settings.get("view_presets")
    if not isinstance(presets, dict):
        return {}
    return {str(key): value for key, value in presets.items() if isinstance(value, dict)}


def save_view_preset(workspace_id: str, name: str, preset: Dict[str, object]) -> None:
    if not name:
        return
    settings = _load_settings(workspace_id)
    presets = settings.get("view_presets")
    if not isinstance(presets, dict):
        presets = {}
    presets[str(name)] = preset
    settings["view_presets"] = presets
    _save_settings(workspace_id, settings)


def _merge_bool_map(defaults: Dict[str, bool], raw) -> Dict[str, bool]:
    merged = dict(defaults)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, bool):
                merged[str(key)] = value
    return merged


def _merge_pulse_settings(defaults: PulseSettings, raw) -> PulseSettings:
    if not isinstance(raw, dict):
        return defaults
    merged = PulseSettings(**defaults.__dict__)
    for field_name in merged.__dict__.keys():
        if field_name not in raw:
            continue
        value = raw.get(field_name)
        if field_name == "topic_enabled":
            merged.topic_enabled = _merge_bool_map(merged.topic_enabled, value)
            continue
        if isinstance(getattr(merged, field_name), bool):
            if isinstance(value, bool):
                setattr(merged, field_name, value)
        elif isinstance(getattr(merged, field_name), float):
            try:
                setattr(merged, field_name, float(value))
            except Exception:
                continue
        elif isinstance(getattr(merged, field_name), int):
            try:
                setattr(merged, field_name, int(value))
            except Exception:
                continue
        elif isinstance(getattr(merged, field_name), str):
            if isinstance(value, str) and value.strip():
                setattr(merged, field_name, value.strip())
    return merged


def _merge_int_setting(raw, default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _pulse_settings_to_dict(settings: PulseSettings) -> Dict[str, object]:
    return {
        "travel_speed_px_per_s": int(settings.travel_speed_px_per_s),
        "travel_duration_ms": int(settings.travel_duration_ms),
        "arrive_linger_ms": int(settings.arrive_linger_ms),
        "fade_ms": int(settings.fade_ms),
        "pulse_duration_ms": int(settings.pulse_duration_ms),
        "pulse_radius_px": int(settings.pulse_radius_px),
        "pulse_alpha": float(settings.pulse_alpha),
        "pulse_min_alpha": float(settings.pulse_min_alpha),
        "intensity_multiplier": float(settings.intensity_multiplier),
        "fade_curve": str(settings.fade_curve),
        "trail_length": int(settings.trail_length),
        "trail_spacing_ms": int(settings.trail_spacing_ms),
        "max_concurrent_signals": int(settings.max_concurrent_signals),
        "tint_active_spans": bool(settings.tint_active_spans),
        "topic_enabled": dict(settings.topic_enabled),
    }


def _default_pulse_topics() -> Dict[str, bool]:
    return {
        "app.activity": True,
        "app.error": True,
        "app.crash": True,
        "job.update": True,
        "span.start": True,
        "span.update": True,
        "span.end": True,
        "bus.request": True,
        "bus.reply": True,
        "expect.check": True,
        "codesee.test_pulse": True,
    }


def _debug_log(message: str) -> None:
    try:
        if os.environ.get("PHYSICSLAB_CODESEE_DEBUG", "0") != "1":
            return
    except Exception:
        return
    try:
        print(f"[codesee.view_config] {message}")
    except Exception:
        return


def _safe_workspace_id(workspace_id: object) -> str:
    if isinstance(workspace_id, str):
        safe_id = workspace_id.strip()
        return safe_id or "default"
    if isinstance(workspace_id, bytes):
        try:
            safe_id = workspace_id.decode("utf-8", errors="ignore").strip()
        except Exception:
            safe_id = ""
        return safe_id or "default"
    return "default"


def _settings_path(workspace_id: str) -> Path:
    safe_id = _safe_workspace_id(workspace_id)
    try:
        return Path("data") / "workspaces" / safe_id / "codesee" / "settings.json"
    except Exception:
        return Path("data") / "workspaces" / "default" / "codesee" / "settings.json"


def _safe_exists(path: Path) -> bool:
    try:
        return path.exists()
    except Exception:
        return False


def _sanitize_settings(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            sanitized[key] = _sanitize_settings(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_settings(item) for item in value]
    try:
        return str(value)
    except Exception:
        return None


def _load_settings(workspace_id: str) -> Dict:
    path = _settings_path(workspace_id)
    if not _safe_exists(path):
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _debug_log(f"settings load failed path={path}")
        return {}


def _save_settings(workspace_id: str, settings: Dict) -> None:
    path = _settings_path(workspace_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        sanitized = _sanitize_settings(settings)
        path.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
    except Exception as exc:
        _debug_log(f"settings save failed path={path} err={exc}")
        return
