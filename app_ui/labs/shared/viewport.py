from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from PyQt6 import QtCore

from .math2d import Vec2

PointLike = Union[Vec2, QtCore.QPointF]


@dataclass
class ViewTransform:
    """Pan/zoom transform between world and screen coordinates.

    zoom = pixels per world unit. center_world maps to rect center.
    """

    rect_px: QtCore.QRectF
    center_world: Vec2 = Vec2(0.0, 0.0)
    zoom: float = 40.0

    def world_to_screen(self, world: PointLike) -> QtCore.QPointF:
        pt = _as_vec2(world)
        cx = self.rect_px.center().x()
        cy = self.rect_px.center().y()
        sx = cx + (pt.x - self.center_world.x) * self.zoom
        sy = cy - (pt.y - self.center_world.y) * self.zoom
        return QtCore.QPointF(sx, sy)

    def screen_to_world(self, screen: PointLike) -> Vec2:
        pt = _as_vec2(screen)
        cx = self.rect_px.center().x()
        cy = self.rect_px.center().y()
        wx = (pt.x - cx) / self.zoom + self.center_world.x
        wy = -(pt.y - cy) / self.zoom + self.center_world.y
        return Vec2(wx, wy)


def _as_vec2(value: PointLike) -> Vec2:
    if isinstance(value, Vec2):
        return value
    return Vec2(value.x(), value.y())
