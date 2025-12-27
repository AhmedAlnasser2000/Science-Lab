from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .badges import Badge, badge_from_dict, badge_from_key, sort_by_priority, severity_for_badge


@dataclass(frozen=True)
class Node:
    node_id: str
    title: str
    node_type: str
    subgraph_id: Optional[str] = None
    badges: List[Badge] = field(default_factory=list)
    severity_state: Optional[str] = None

    def __post_init__(self) -> None:
        normalized: List[Badge] = []
        for entry in self.badges or []:
            if isinstance(entry, Badge):
                normalized.append(entry)
                continue
            if isinstance(entry, str):
                normalized.append(badge_from_key(entry))
                continue
            if isinstance(entry, dict):
                badge = badge_from_dict(entry)
                if badge:
                    normalized.append(badge)
        object.__setattr__(self, "badges", normalized)

    @property
    def id(self) -> str:
        return self.node_id

    @property
    def type(self) -> str:
        return self.node_type

    def badges_for_rail(self, rail: str) -> List[Badge]:
        if rail not in ("top", "bottom"):
            return []
        return [badge for badge in sort_by_priority(self.badges) if badge.rail == rail]

    def effective_severity(self) -> str:
        if self.badges:
            ordered = sort_by_priority(self.badges)
            if ordered:
                return severity_for_badge(ordered[0])
        if self.severity_state:
            return self.severity_state
        return "normal"


@dataclass(frozen=True)
class Edge:
    edge_id: str
    src_node_id: str
    dst_node_id: str
    kind: str = "dependency"

    @property
    def id(self) -> str:
        return self.edge_id


@dataclass
class ArchitectureGraph:
    graph_id: str
    title: str
    nodes: List[Node]
    edges: List[Edge]

    def node_map(self) -> Dict[str, Node]:
        return {node.node_id: node for node in self.nodes}

    def get_node(self, node_id: str) -> Optional[Node]:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None
