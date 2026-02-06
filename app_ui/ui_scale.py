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
def load_config() -> UiScaleConfig:
    if not _CONFIG_PATH.exists():
        return UiScaleConfig()
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return UiScaleConfig()
    scale = int(data.get("scale_percent", _DEFAULT_SCALE))
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
    global _BASE_FONT_SIZE, _CURRENT
    if _BASE_FONT_SIZE is None:
        _BASE_FONT_SIZE = app.font().pointSizeF()
    scale = max(50, min(200, int(cfg.scale_percent)))
    font = QtGui.QFont(app.font())
    font.setPointSizeF(_BASE_FONT_SIZE * (scale / 100.0))
    app.setFont(font)
    _CURRENT = UiScaleConfig(scale_percent=scale, density=cfg.density)
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
    _NOTIFIER.changed.connect(callback)


# === [NAV-99] End =============================================================
