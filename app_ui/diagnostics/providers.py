from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional


@dataclass
class DiagnosticsContext:
    workspace_id: str
    data_root: str


class DiagnosticsProvider:
    def __init__(
        self,
        *,
        id: str,
        title: str,
        is_available: Callable[[DiagnosticsContext], bool],
        create_widget: Optional[Callable[[DiagnosticsContext], object]] = None,
        render_text: Optional[Callable[[DiagnosticsContext], str]] = None,
    ) -> None:
        self.id = id
        self.title = title
        self.is_available = is_available
        self.create_widget = create_widget
        self.render_text = render_text


_registry: List[DiagnosticsProvider] = []


def register_provider(provider: DiagnosticsProvider) -> None:
    if any(p.id == provider.id for p in _registry):
        return
    _registry.append(provider)


def list_providers(ctx: DiagnosticsContext) -> Iterable[DiagnosticsProvider]:
    for provider in _registry:
        try:
            if provider.is_available(ctx):
                yield provider
        except Exception:  # pragma: no cover - defensive
            continue


def clear_providers() -> None:
    _registry.clear()
