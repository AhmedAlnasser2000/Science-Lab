"""Compatibility module for shared lab utilities."""

from .math2d import Vec2
from .viewport import ViewTransform
from .primitives import draw_axes, draw_grid, draw_vector

__all__ = ["Vec2", "ViewTransform", "draw_axes", "draw_grid", "draw_vector"]
