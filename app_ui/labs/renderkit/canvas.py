from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from .assets import AssetResolver, AssetCache, DEFAULT_STORE_ROOT


@dataclass
class RenderContext:
    resolver: AssetResolver
    cache: AssetCache
    palette: QtGui.QPalette
    dpi_scale: float
    world_bounds: Dict[str, float]
    world_to_screen: Callable[[QtCore.QPointF], QtCore.QPointF]
    screen_to_world: Callable[[QtCore.QPoint], QtCore.QPointF]


class RenderCanvas(QtWidgets.QWidget):
    """Lightweight canvas that applies world->screen transform and executes layers."""

    def __init__(
        self,
        resolver: Optional[AssetResolver] = None,
        cache: Optional[AssetCache] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)
        self.resolver = resolver or AssetResolver(DEFAULT_STORE_ROOT)
        self.cache = cache or AssetCache()
        self.world_bounds: Dict[str, float] = {"xmin": -10.0, "xmax": 10.0, "ymin": -10.0, "ymax": 10.0}
        self.layers: List[Callable[[QtGui.QPainter, RenderContext], None]] = []
        self.padding = 28
        self._tf_cache: Dict[str, float] = {}
        self.setMinimumHeight(320)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

    def set_world_bounds(self, xmin: float, xmax: float, ymin: float, ymax: float) -> None:
        self.world_bounds = {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax}
        self.update()

    def set_layers(self, layers: Sequence[Callable[[QtGui.QPainter, RenderContext], None]]) -> None:
        self.layers = list(layers or [])
        self.update()

    # -- transform helpers ------------------------------------------------
    def _compute_transform(self) -> Dict[str, float]:
        w = max(1, self.width())
        h = max(1, self.height())
        pad = self.padding
        wb = self.world_bounds
        span_x = max(1e-6, wb["xmax"] - wb["xmin"])
        span_y = max(1e-6, wb["ymax"] - wb["ymin"])
        usable_w = max(4.0, w - 2 * pad)
        usable_h = max(4.0, h - 2 * pad)
        scale = min(usable_w / span_x, usable_h / span_y)
        self._tf_cache = {"w": w, "h": h, "pad": pad, "scale": scale, "wb": wb}
        return self._tf_cache

    def world_to_screen(self, pt: QtCore.QPointF) -> QtCore.QPointF:
        tf = self._tf_cache or self._compute_transform()
        wb = tf["wb"]
        scale = tf["scale"]
        pad = tf["pad"]
        h = tf["h"]
        sx = pad + (pt.x() - wb["xmin"]) * scale
        sy = h - pad - (pt.y() - wb["ymin"]) * scale
        return QtCore.QPointF(sx, sy)

    def screen_to_world(self, pt: QtCore.QPoint) -> QtCore.QPointF:
        tf = self._tf_cache or self._compute_transform()
        wb = tf["wb"]
        scale = tf["scale"]
        pad = tf["pad"]
        h = tf["h"]
        x = wb["xmin"] + (pt.x() - pad) / scale
        y = wb["ymin"] + (h - pad - pt.y()) / scale
        return QtCore.QPointF(x, y)

    # -- paint ------------------------------------------------------------
    def paintEvent(self, _: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        bg = self.palette().color(QtGui.QPalette.ColorRole.Base)
        painter.fillRect(self.rect(), bg)

        tf = self._compute_transform()
        dpi_scale = max(1.0, self.devicePixelRatioF())
        ctx = RenderContext(
            resolver=self.resolver,
            cache=self.cache,
            palette=self.palette(),
            dpi_scale=dpi_scale,
            world_bounds=self.world_bounds,
            world_to_screen=self.world_to_screen,
            screen_to_world=self.screen_to_world,
        )
        for layer in self.layers:
            try:
                layer(painter, ctx)
            except Exception:
                # Do not crash the UI for a single layer failure.
                continue




