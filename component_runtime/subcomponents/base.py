from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from PyQt6 import QtCore, QtGui


@dataclass(frozen=True)
class Subcomponent:
    """Small reusable unit with a stable id/name."""

    component_id: str
    display_name: str

    def dispose(self) -> None:
        """Optional cleanup hook."""
        return None


class Renderable(Protocol):
    """Render-only unit used in lab/component paint pipelines."""

    def draw(self, painter: "QtGui.QPainter", view: Any, ctx: Any) -> None:
        ...


class Controller(Protocol):
    """Optional input hooks (mouse/keyboard)."""

    def on_mouse_event(self, event: "QtGui.QMouseEvent", view: Any, ctx: Any) -> None:
        ...

    def on_key_event(self, event: "QtGui.QKeyEvent", view: Any, ctx: Any) -> None:
        ...


class ModelUnit(Protocol):
    """Optional model unit for update/compute steps."""

    def update(self, dt: float, ctx: Any) -> None:
        ...

    def compute(self, ctx: Any) -> None:
        ...
