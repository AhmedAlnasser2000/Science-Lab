from __future__ import annotations

from typing import List

from ..graph_model import Edge, Node
from .base import CollectorContext, CollectorResult


def collect_labs(_ctx: CollectorContext) -> CollectorResult:
    nodes: List[Node] = []
    edges: List[Edge] = []
    try:
        from app_ui.labs import registry as lab_registry
    except Exception:
        return CollectorResult(nodes=nodes, edges=edges, subgraphs={})

    labs = lab_registry.list_labs()
    for lab_id, plugin in labs.items():
        title = getattr(plugin, "title", None) or lab_id
        node_id = f"lab:{lab_id}"
        nodes.append(
            Node(
                node_id=node_id,
                title=title,
                node_type="Lab",
            )
        )
        edges.append(Edge(f"edge:app_ui:{node_id}", "system:app_ui", node_id, "loads"))

    return CollectorResult(nodes=nodes, edges=edges, subgraphs={})
