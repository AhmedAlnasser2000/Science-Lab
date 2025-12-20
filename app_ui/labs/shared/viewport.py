from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6 import QtCore


@dataclass
class ViewTransform:
    """World<->screen transform with pan/zoom and cached scale."""

    padding_px: int = 24
    xmin: float = -10.0
    xmax: float = 10.0
    ymin: float = -10.0
    ymax: float = 10.0
    scale: float = 1.0
    width_px: int = 1
    height_px: int = 1

    def set_world_bounds(self, xmin: float, xmax: float, ymin: float, ymax: float) -> None:
        self.xmin = float(xmin)
        self.xmax = float(xmax)
        self.ymin = float(ymin)
        self.ymax = float(ymax)

    def fit(self, rect_px_width: int, rect_px_height: int) -> None:
        self.width_px = max(1, int(rect_px_width))
        self.height_px = max(1, int(rect_px_height))
        span_x = max(1e-6, self.xmax - self.xmin)
        span_y = max(1e-6, self.ymax - self.ymin)
        usable_w = max(4.0, self.width_px - 2 * self.padding_px)
        usable_h = max(4.0, self.height_px - 2 * self.padding_px)
        self.scale = min(usable_w / span_x, usable_h / span_y)

    def world_to_screen(self, world: QtCore.QPointF) -> QtCore.QPointF:
        sx = self.padding_px + (world.x() - self.xmin) * self.scale
        sy = self.height_px - self.padding_px - (world.y() - self.ymin) * self.scale
        return QtCore.QPointF(sx, sy)

    def screen_to_world(self, screen: QtCore.QPointF) -> QtCore.QPointF:
        wx = (screen.x() - self.padding_px) / self.scale + self.xmin
        wy = (self.height_px - self.padding_px - screen.y()) / self.scale + self.ymin
        return QtCore.QPointF(wx, wy)


def nice_step(span: float) -> float:
    """Return a visually pleasant grid step for a given span."""
    if span <= 0:
        return 1.0
    raw = span / 8.0
    power = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        step = m * power
        if span / step <= 12:
            return step
    return power * 10
