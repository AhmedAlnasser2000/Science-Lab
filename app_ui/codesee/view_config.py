from __future__ import annotations

import json
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


@dataclass
class PulseSettings:
    travel_speed_px_per_s: int = 900
    travel_duration_ms: int = 0
    arrive_linger_ms: int = 300
    fade_ms: int = 500
    pulse_duration_ms: int = 650
    pulse_radius_px: int = 8
    pulse_alpha: float = 0.6
    pulse_min_alpha: float = 0.12
    intensity_multiplier: float = 1.0
    fade_curve: str = "linear"
    max_concurrent_signals: int = 6
    tint_active_spans: bool = False


_CATEGORY_DEFAULTS = {
    "Workspace": True,
    "Pack": True,
    "Block": True,
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
        "max_concurrent_signals": int(settings.max_concurrent_signals),
        "tint_active_spans": bool(settings.tint_active_spans),
    }


def _settings_path(workspace_id: str) -> Path:
    safe_id = str(workspace_id or "default").strip() or "default"
    return Path("data") / "workspaces" / safe_id / "codesee" / "settings.json"


def _load_settings(workspace_id: str) -> Dict:
    path = _settings_path(workspace_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_settings(workspace_id: str, settings: Dict) -> None:
    path = _settings_path(workspace_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        return
