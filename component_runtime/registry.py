from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .types import Component, ComponentMeta


@dataclass(frozen=True)
class ComponentEntry:
    meta: ComponentMeta
    factory: Callable[[], Component]


class ComponentRegistry:
    """Simple in-process registry for component factories."""

    def __init__(self) -> None:
        self._entries: Dict[str, ComponentEntry] = {}

    def register(self, factory: Callable[[], Component]) -> None:
        component = factory()
        meta = ComponentMeta(
            component_id=component.component_id,
            display_name=component.display_name,
            kind=component.kind,
        )
        self._entries[meta.component_id] = ComponentEntry(meta=meta, factory=factory)

    def list_components(self) -> List[ComponentMeta]:
        return [entry.meta for entry in self._entries.values()]

    def get_component(self, component_id: str) -> Optional[Component]:
        entry = self._entries.get(component_id)
        if not entry:
            return None
        return entry.factory()


_REGISTRY = ComponentRegistry()


def get_registry() -> ComponentRegistry:
    return _REGISTRY


def register_component(factory: Callable[[], Component]) -> None:
    _REGISTRY.register(factory)


def register_lab_components(lab_registry) -> None:
    from .lab_component import make_lab_component

    for lab_id, plugin in lab_registry.list_labs().items():
        display_name = getattr(plugin, "title", lab_id)
        _REGISTRY.register(
            lambda lab_id=lab_id, display_name=display_name: make_lab_component(
                lab_id,
                display_name,
                lab_registry,
            )
        )
