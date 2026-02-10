from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .graph_model import Edge, Node


@dataclass(frozen=True)
class ItemRef:
    kind: str
    id: str
    namespace: Optional[str] = None


def itemref_from_node(node: Node) -> ItemRef:
    return ItemRef(kind="node", id=str(node.node_id))


def itemref_from_edge(edge: Edge) -> ItemRef:
    return ItemRef(kind="edge", id=str(edge.edge_id))


def itemref_display_name(item_ref: ItemRef) -> str:
    if item_ref.kind == "node":
        return item_ref.id
    if item_ref.kind == "edge":
        return f"Edge {item_ref.id}"
    return f"{item_ref.kind}:{item_ref.id}"
