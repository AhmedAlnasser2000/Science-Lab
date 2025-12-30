from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .badges import Badge, badge_from_dict, badge_from_key, sort_by_priority, severity_for_badge
from .expectations import EVACheck, check_from_dict
from .runtime.events import SpanRecord, span_from_dict


@dataclass(frozen=True)
class Node:
    node_id: str
    title: str
    node_type: str
    subgraph_id: Optional[str] = None
    badges: List[Badge] = field(default_factory=list)
    severity_state: Optional[str] = None
    checks: List[EVACheck] = field(default_factory=list)
    spans: List[SpanRecord] = field(default_factory=list)

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

        checks: List[EVACheck] = []
        for entry in self.checks or []:
            if isinstance(entry, EVACheck):
                checks.append(entry)
            elif isinstance(entry, dict):
                parsed = check_from_dict(entry)
                if parsed:
                    checks.append(parsed)
        object.__setattr__(self, "checks", checks)

        spans: List[SpanRecord] = []
        for entry in self.spans or []:
            if isinstance(entry, SpanRecord):
                spans.append(entry)
            elif isinstance(entry, dict):
                parsed = span_from_dict(entry)
                if parsed:
                    spans.append(parsed)
        object.__setattr__(self, "spans", spans)

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
