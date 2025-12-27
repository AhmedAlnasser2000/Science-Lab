from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol

from ..graph_model import ArchitectureGraph, Edge, Node


@dataclass
class CollectorContext:
    workspace_id: str
    workspace_info: Dict[str, Any]
    bus: Any = None
    content_adapter: Any = None


@dataclass
class CollectorResult:
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    subgraphs: Dict[str, ArchitectureGraph] = field(default_factory=dict)


class Collector(Protocol):
    def collect(self, ctx: CollectorContext) -> CollectorResult:
        ...
