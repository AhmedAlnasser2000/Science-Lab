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
        self._pack_component_ids: set[str] = set()

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


def register_pack_components(pack_manifests) -> None:
    from pathlib import Path

    from .lab_preset import LabPresetLauncherComponent
    from .markdown_panel import MarkdownPanelComponent
    from .types import ComponentKind

    for component_id in list(_REGISTRY._pack_component_ids):
        _REGISTRY._entries.pop(component_id, None)
    _REGISTRY._pack_component_ids.clear()

    for entry in pack_manifests or []:
        manifest = entry.get("manifest") if isinstance(entry, dict) else entry
        if not isinstance(manifest, dict):
            continue
        pack_root = entry.get("pack_root") if isinstance(entry, dict) else None
        if pack_root is None:
            pack_root = Path(".")
        components = manifest.get("components")
        if not isinstance(components, list):
            continue
        for component in components:
            if not isinstance(component, dict):
                continue
            component_id = component.get("component_id")
            impl = component.get("impl")
            display_name = component.get("display_name") or component_id
            kind = component.get("kind", "other")
            if not isinstance(component_id, str) or not component_id.strip():
                continue
            try:
                parsed_kind = ComponentKind(kind)
            except Exception:
                parsed_kind = ComponentKind.OTHER if hasattr(ComponentKind, "OTHER") else ComponentKind.PANEL
            if impl == "builtin:markdown_panel":
                _REGISTRY.register(
                    lambda component_id=component_id, display_name=display_name, parsed_kind=parsed_kind, pack_root=pack_root, component=component: MarkdownPanelComponent(
                        component_id,
                        display_name,
                        parsed_kind,
                        pack_root,
                        component.get("assets") or {},
                        component.get("params") or {},
                    )
                )
                _REGISTRY._pack_component_ids.add(component_id)
            elif impl == "builtin:lab_preset":
                _REGISTRY.register(
                    lambda component_id=component_id, display_name=display_name, parsed_kind=parsed_kind, pack_root=pack_root, component=component: LabPresetLauncherComponent(
                        component_id,
                        display_name,
                        parsed_kind,
                        pack_root,
                        component.get("params") or {},
                    )
                )
                _REGISTRY._pack_component_ids.add(component_id)
