# =============================================================================
# NAV INDEX (search these tags)
# [NAV-00] Imports / constants
# [NAV-10] Density/scaling rules
# [NAV-20] Apply-to-Qt helpers
# [NAV-99] End
# =============================================================================

# === [NAV-00] Imports / constants ============================================
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

_CONFIG_PATH = Path("data/roaming/ui_scale.json")
_DEFAULT_SCALE = 100
_DEFAULT_DENSITY = "comfortable"
_BASE_FONT_SIZE: Optional[float] = None


# === [NAV-10] Density/scaling rules ==========================================
@dataclass(frozen=True)
class UiScaleConfig:
    scale_percent: int = _DEFAULT_SCALE
    density: str = _DEFAULT_DENSITY


class UiScaleNotifier(QtCore.QObject):
    changed = QtCore.pyqtSignal(object)


_NOTIFIER = UiScaleNotifier()
_CURRENT = UiScaleConfig()


# === [NAV-20] Apply-to-Qt helpers ============================================
def clamp_scale_percent(value: object) -> int:
    try:
        parsed = int(float(str(value).strip().replace("%", "")))
    except Exception:
        parsed = _DEFAULT_SCALE
    return max(50, min(250, parsed))


def load_config() -> UiScaleConfig:
    if not _CONFIG_PATH.exists():
        return UiScaleConfig()
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return UiScaleConfig()
    scale = clamp_scale_percent(data.get("scale_percent", _DEFAULT_SCALE))
    density = str(data.get("density", _DEFAULT_DENSITY)).lower()
    if density not in ("comfortable", "compact"):
        density = _DEFAULT_DENSITY
    return UiScaleConfig(scale_percent=scale, density=density)


def save_config(cfg: UiScaleConfig) -> None:
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(
            json.dumps({"scale_percent": cfg.scale_percent, "density": cfg.density}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        return


def apply_to_app(app: QtWidgets.QApplication, cfg: UiScaleConfig) -> None:
    global _BASE_FONT_SIZE, _CURRENT, _NOTIFIER
    if _BASE_FONT_SIZE is None:
        _BASE_FONT_SIZE = app.font().pointSizeF()
    previous_scale = int(_CURRENT.scale_percent or _DEFAULT_SCALE)
    scale = clamp_scale_percent(cfg.scale_percent)
    font = QtGui.QFont(app.font())
    font.setPointSizeF(_BASE_FONT_SIZE * (scale / 100.0))
    app.setFont(font)
    _CURRENT = UiScaleConfig(scale_percent=scale, density=cfg.density)
    if previous_scale > 0 and previous_scale != scale:
        ratio = float(scale) / float(previous_scale)
        _rescale_top_level_windows(app, ratio)
    try:
        _NOTIFIER.changed.emit(_CURRENT)
    except RuntimeError:
        _NOTIFIER = UiScaleNotifier()
        _NOTIFIER.changed.emit(_CURRENT)


def get_config() -> UiScaleConfig:
    return _CURRENT


def scale_px(value: int) -> int:
    scale = _CURRENT.scale_percent or _DEFAULT_SCALE
    return max(1, int(round(value * (scale / 100.0))))


def density_spacing(base: int) -> int:
    if _CURRENT.density == "compact":
        return max(2, base - 4)
    return base


def register_listener(callback: Callable[[UiScaleConfig], None]) -> None:
    global _NOTIFIER
    try:
        _NOTIFIER.changed.connect(callback)
    except RuntimeError:
        _NOTIFIER = UiScaleNotifier()
        _NOTIFIER.changed.connect(callback)


def _rescale_top_level_windows(app: QtWidgets.QApplication, ratio: float) -> None:
    if ratio <= 0.0 or abs(ratio - 1.0) < 0.01:
        return
    for widget in app.topLevelWidgets():
        if not isinstance(widget, QtWidgets.QWidget) or not widget.isWindow():
            continue
        state = widget.windowState()
        if state & (
            QtCore.Qt.WindowState.WindowMaximized
            | QtCore.Qt.WindowState.WindowFullScreen
            | QtCore.Qt.WindowState.WindowMinimized
        ):
            continue
        _rescale_widget_geometry(widget, ratio)


def _rescale_widget_geometry(widget: QtWidgets.QWidget, ratio: float) -> None:
    current_size = widget.size()
    if not current_size.isValid() or current_size.width() <= 0 or current_size.height() <= 0:
        return
    min_size = widget.minimumSize()
    target_w = int(round(current_size.width() * ratio))
    target_h = int(round(current_size.height() * ratio))
    if min_size.width() > 0:
        target_w = max(target_w, min_size.width())
    if min_size.height() > 0:
        target_h = max(target_h, min_size.height())
    screen = widget.screen() or QtWidgets.QApplication.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        target_w = min(target_w, max(100, available.width()))
        target_h = min(target_h, max(100, available.height()))
    widget.resize(max(100, target_w), max(100, target_h))


# === [NAV-99] End =============================================================
