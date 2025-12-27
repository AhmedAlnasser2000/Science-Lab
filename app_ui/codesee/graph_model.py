from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Node:
    node_id: str
    title: str
    node_type: str
    severity_state: str = "normal"
    badges_top: List[str] = field(default_factory=list)
    badges_bottom: List[str] = field(default_factory=list)
    subgraph_id: Optional[str] = None

    @property
    def id(self) -> str:
        return self.node_id

    @property
    def type(self) -> str:
        return self.node_type


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
