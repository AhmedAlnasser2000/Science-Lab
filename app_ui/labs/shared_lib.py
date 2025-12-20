from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Union

from PyQt6 import QtCore, QtGui

PointLike = Union["Vec2", QtCore.QPointF]


@dataclass(frozen=True)
class Vec2:
    """Small immutable 2D vector with basic math helpers."""

    x: float
    y: float

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vec2":
        return Vec2(self.x * scalar, self.y * scalar)

    def __rmul__(self, scalar: float) -> "Vec2":
        return self.__mul__(scalar)

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> "Vec2":
        length = self.length()
        if length <= 1e-9:
            return Vec2(0.0, 0.0)
        return Vec2(self.x / length, self.y / length)

    def to_point(self) -> QtCore.QPointF:
        return QtCore.QPointF(self.x, self.y)


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


def draw_grid(painter: QtGui.QPainter, rect_px: QtCore.QRectF, step_px: float = 40.0) -> None:
    """Draw a light grid inside rect_px at the given pixel spacing."""
    if step_px <= 1:
        step_px = 1.0
    painter.save()
    pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 22))
    pen.setWidthF(1.0)
    painter.setPen(pen)
    x = rect_px.left() - (rect_px.left() % step_px)
    while x <= rect_px.right():
        painter.drawLine(QtCore.QPointF(x, rect_px.top()), QtCore.QPointF(x, rect_px.bottom()))
        x += step_px
    y = rect_px.top() - (rect_px.top() % step_px)
    while y <= rect_px.bottom():
        painter.drawLine(QtCore.QPointF(rect_px.left(), y), QtCore.QPointF(rect_px.right(), y))
        y += step_px
    painter.restore()


def draw_axes(
    painter: QtGui.QPainter,
    origin_px: PointLike,
    axis_len_px: float | None = None,
) -> None:
    """Draw X/Y axes crossing at origin_px."""
    origin = _as_vec2(origin_px).to_point()
    painter.save()
    pen = QtGui.QPen(QtGui.QColor(120, 132, 168))
    pen.setWidthF(2.0)
    painter.setPen(pen)
    length = axis_len_px or 200.0
    painter.drawLine(
        QtCore.QPointF(origin.x() - length, origin.y()),
        QtCore.QPointF(origin.x() + length, origin.y()),
    )
    painter.drawLine(
        QtCore.QPointF(origin.x(), origin.y() - length),
        QtCore.QPointF(origin.x(), origin.y() + length),
    )
    painter.restore()


def draw_vector(
    painter: QtGui.QPainter,
    origin_px: PointLike,
    vec_px: PointLike,
    arrow_head_px: float = 8.0,
) -> None:
    """Draw a vector starting at origin_px with delta vec_px."""
    origin = _as_vec2(origin_px).to_point()
    vec = _as_vec2(vec_px)
    end = QtCore.QPointF(origin.x() + vec.x, origin.y() + vec.y)
    painter.save()
    pen = QtGui.QPen(QtGui.QColor(80, 170, 255))
    pen.setWidthF(2.0)
    painter.setPen(pen)
    painter.drawLine(origin, end)

    length = vec.length()
    if length > 1e-3 and arrow_head_px > 0:
        dir_vec = vec.normalized()
        back = Vec2(end.x(), end.y()) - dir_vec * arrow_head_px
        left = Vec2(-dir_vec.y, dir_vec.x) * (arrow_head_px * 0.6)
        right = Vec2(dir_vec.y, -dir_vec.x) * (arrow_head_px * 0.6)
        head = QtGui.QPolygonF(
            [
                end,
                (back + left).to_point(),
                (back + right).to_point(),
            ]
        )
        painter.setBrush(pen.color())
        painter.drawPolygon(head)
    painter.restore()


def _as_vec2(value: PointLike) -> Vec2:
    if isinstance(value, Vec2):
        return value
    return Vec2(value.x(), value.y())
