from __future__ import annotations

import math
from typing import Union

from PyQt6 import QtCore, QtGui

from .math2d import Vec2

PointLike = Union[Vec2, QtCore.QPointF]
AxesOrigin = Union[Vec2, QtCore.QPointF, QtCore.QRectF]


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
    origin_px: AxesOrigin,
    axis_len_px: float | None = None,
) -> None:
    """Draw X/Y axes crossing at origin_px or rect center."""
    origin, default_len = _resolve_axes_origin(origin_px)
    painter.save()
    pen = QtGui.QPen(QtGui.QColor(120, 132, 168))
    pen.setWidthF(2.0)
    painter.setPen(pen)
    length = axis_len_px if axis_len_px is not None else default_len
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


def _resolve_axes_origin(origin_px: AxesOrigin) -> tuple[QtCore.QPointF, float]:
    if isinstance(origin_px, QtCore.QRectF):
        center = origin_px.center()
        default_len = min(origin_px.width(), origin_px.height()) / 2.0
        return center, max(20.0, default_len)
    point = _as_vec2(origin_px).to_point()
    return point, 200.0
