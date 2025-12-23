from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from PyQt6 import QtWidgets


class ComponentKind(str, Enum):
    PANEL = "panel"
    LAB = "lab"
    TOOL = "tool"


@dataclass(frozen=True)
class ComponentMeta:
    component_id: str
    display_name: str
    kind: ComponentKind


class Component(Protocol):
    component_id: str
    display_name: str
    kind: ComponentKind

    def create_widget(self, ctx: "ComponentContext") -> "QtWidgets.QWidget":
        ...

    def dispose(self) -> None:
        ...
