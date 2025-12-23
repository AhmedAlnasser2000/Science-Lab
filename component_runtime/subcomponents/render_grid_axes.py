from __future__ import annotations

from typing import Any

from PyQt6 import QtCore, QtGui

from app_ui.labs.shared import primitives as shared_primitives

from .base import Renderable, Subcomponent


class GridAxesRenderable(Subcomponent, Renderable):
    def __init__(self) -> None:
        super().__init__(component_id="render.grid_axes", display_name="Grid & Axes")

    def draw(self, painter: QtGui.QPainter, view: Any, ctx: Any) -> None:
        rect_px = _ctx_value(ctx, "rect_px", None)
        if not isinstance(rect_px, QtCore.QRectF):
            rect_px = QtCore.QRectF(painter.viewport())

        origin_px = _ctx_value(ctx, "origin_px", None)
        if not isinstance(origin_px, QtCore.QPointF):
            origin_px = _default_origin(view, rect_px)

        step_px = _ctx_value(ctx, "step_px", 40.0)
        axis_len = _ctx_value(ctx, "axis_len_px", None)
        if axis_len is None:
            axis_len = min(rect_px.width(), rect_px.height()) / 2.0

        show_grid = _flag(ctx, "show_grid", True)
        show_axes = _flag(ctx, "show_axes", True)

        if show_grid:
            shared_primitives.draw_grid(painter, rect_px, step_px=step_px)
        if show_axes:
            shared_primitives.draw_axes(painter, origin_px, axis_len_px=axis_len)


def _default_origin(view: Any, rect_px: QtCore.QRectF) -> QtCore.QPointF:
    if view is not None and hasattr(view, "world_to_screen"):
        try:
            return view.world_to_screen(QtCore.QPointF(0.0, 0.0))
        except Exception:
            pass
    return rect_px.center()


def _ctx_value(ctx: Any, key: str, default: Any) -> Any:
    if isinstance(ctx, dict):
        return ctx.get(key, default)
    return getattr(ctx, key, default)


def _flag(ctx: Any, key: str, default: bool) -> bool:
    prefs = _ctx_value(ctx, "lab_prefs", None)
    if prefs is not None and hasattr(prefs, key):
        try:
            return bool(getattr(prefs, key))
        except Exception:
            return default
    value = _ctx_value(ctx, key, default)
    try:
        return bool(value)
    except Exception:
        return default
