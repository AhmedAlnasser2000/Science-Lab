from __future__ import annotations

import math
from typing import Callable, Optional, Tuple

from PyQt6 import QtCore, QtGui

from .assets import AssetResolver, AssetCache
from .canvas import RenderContext


def _nice_step(span: float) -> float:
    if span <= 0:
        return 1.0
    raw = span / 8.0
    power = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        step = m * power
        if span / step <= 12:
            return step
    return power * 10


def draw_grid(painter: QtGui.QPainter, ctx: RenderContext, step: float = 1.0) -> None:
    wb = ctx.world_bounds
    span = max(wb["xmax"] - wb["xmin"], wb["ymax"] - wb["ymin"])
    step = _nice_step(span if step <= 0 else step)

    painter.save()
    grid_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 22))
    grid_pen.setWidthF(1.0)
    painter.setPen(grid_pen)

    x = math.ceil(wb["xmin"] / step) * step
    while x <= wb["xmax"]:
        p1 = ctx.world_to_screen(QtCore.QPointF(x, wb["ymin"]))
        p2 = ctx.world_to_screen(QtCore.QPointF(x, wb["ymax"]))
        painter.drawLine(p1, p2)
        x += step

    y = math.ceil(wb["ymin"] / step) * step
    while y <= wb["ymax"]:
        p1 = ctx.world_to_screen(QtCore.QPointF(wb["xmin"], y))
        p2 = ctx.world_to_screen(QtCore.QPointF(wb["xmax"], y))
        painter.drawLine(p1, p2)
        y += step
    painter.restore()


def draw_axes(painter: QtGui.QPainter, ctx: RenderContext) -> None:
    wb = ctx.world_bounds
    painter.save()
    axis_pen = QtGui.QPen(QtGui.QColor(120, 132, 168), 2)
    painter.setPen(axis_pen)
    painter.drawLine(
        ctx.world_to_screen(QtCore.QPointF(wb["xmin"], 0)),
        ctx.world_to_screen(QtCore.QPointF(wb["xmax"], 0)),
    )
    painter.drawLine(
        ctx.world_to_screen(QtCore.QPointF(0, wb["ymin"])),
        ctx.world_to_screen(QtCore.QPointF(0, wb["ymax"])),
    )
    painter.restore()


def draw_svg_sprite(
    painter: QtGui.QPainter,
    ctx: RenderContext,
    asset_rel_path: str,
    world_pos: Tuple[float, float],
    world_size: Tuple[float, float],
    *,
    tint_role: Optional[QtGui.QPalette.ColorRole] = None,
    tint_color: Optional[QtGui.QColor] = None,
    rotation_deg: float = 0.0,
) -> bool:
    resolver: AssetResolver = ctx.resolver
    cache: AssetCache = ctx.cache
    asset_path = resolver.resolve(asset_rel_path)
    if not asset_path:
        return False

    size_px = _world_size_to_px(ctx, world_size)
    color = tint_color or (ctx.palette.color(tint_role) if tint_role else None)
    pixmap = cache.get_pixmap(asset_path, size_px, dpi_scale=ctx.dpi_scale, tint=color)
    if not pixmap or pixmap.isNull():
        return False

    center_screen = ctx.world_to_screen(QtCore.QPointF(*world_pos))
    half_w = pixmap.width() / (2 * pixmap.devicePixelRatioF())
    half_h = pixmap.height() / (2 * pixmap.devicePixelRatioF())
    target = QtCore.QRectF(
        center_screen.x() - half_w,
        center_screen.y() - half_h,
        half_w * 2,
        half_h * 2,
    )

    painter.save()
    if rotation_deg:
        painter.translate(center_screen)
        painter.rotate(rotation_deg)
        painter.translate(-center_screen)
    painter.drawPixmap(target, pixmap, pixmap.rect())
    painter.restore()
    return True


def draw_arrow_sprite(
    painter: QtGui.QPainter,
    ctx: RenderContext,
    start_world: Tuple[float, float],
    end_world: Tuple[float, float],
    *,
    asset_rel_path: str = "assets/lab_viz/arrow.svg",
    label: Optional[str] = None,
    color_role: QtGui.QPalette.ColorRole = QtGui.QPalette.ColorRole.Highlight,
    color: Optional[QtGui.QColor] = None,
    width: float = 2.0,
) -> None:
    start = ctx.world_to_screen(QtCore.QPointF(*start_world))
    end = ctx.world_to_screen(QtCore.QPointF(*end_world))
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    angle_deg = math.degrees(math.atan2(dy, dx))
    length_px = math.hypot(dx, dy)
    # Size sprite proportional to length; cap minimum.
    sprite_len = max(18.0, min(length_px, 120.0))
    sprite_size = (int(sprite_len), int(sprite_len * 0.3))
    color = color or ctx.palette.color(color_role)
    ok = False
    if length_px > 2:
        ok = draw_svg_sprite(
            painter,
            ctx,
            asset_rel_path,
            end_world,
            (sprite_size[0] / _px_per_world(ctx), sprite_size[1] / _px_per_world(ctx)),
            tint_role=color_role if color is None else None,
            tint_color=color,
            rotation_deg=angle_deg,
        )
    if not ok:
        # Fallback: simple line + head.
        painter.save()
        painter.setPen(QtGui.QPen(color, width))
        painter.drawLine(start, end)
        _draw_head(painter, start, end, color, width)
        painter.restore()

    if label:
        painter.save()
        painter.setPen(color)
        offset = QtCore.QPointF(8.0, -8.0)
        painter.drawText(end + offset, label)
        painter.restore()


def _draw_head(painter: QtGui.QPainter, start: QtCore.QPointF, end: QtCore.QPointF, color: QtGui.QColor, width: float) -> None:
    vec = end - start
    length = math.hypot(vec.x(), vec.y())
    if length < 1e-3:
        return
    head_len = min(14.0, 0.18 * length + 6.0)
    head_width = head_len * 0.6
    direction = QtCore.QPointF(vec.x() / length, vec.y() / length)
    back = end - direction * head_len
    left = QtCore.QPointF(-direction.y() * head_width, direction.x() * head_width)
    right = -left
    head = QtGui.QPolygonF([end, back + left, back + right])
    painter.setBrush(color)
    painter.setPen(QtGui.QPen(color, width))
    painter.drawPolygon(head)


def _world_size_to_px(ctx: RenderContext, world_size: Tuple[float, float]) -> Tuple[int, int]:
    base_scale = _px_per_world(ctx)
    return (
        max(1, int(world_size[0] * base_scale)),
        max(1, int(world_size[1] * base_scale)),
    )


def _px_per_world(ctx: RenderContext) -> float:
    p0 = ctx.world_to_screen(QtCore.QPointF(0.0, 0.0))
    p1 = ctx.world_to_screen(QtCore.QPointF(1.0, 0.0))
    return max(1e-3, math.hypot(p1.x() - p0.x(), p1.y() - p0.y()))

