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
        metadata = {
            "lab_id": lab_id,
            "declared_by": "app_ui.labs.registry",
        }
        plugin_name = type(plugin).__name__ if plugin else None
        if plugin_name:
            metadata["plugin"] = plugin_name
        nodes.append(
            Node(
                node_id=node_id,
                title=title,
                node_type="Lab",
                metadata=metadata,
            )
        )
        edges.append(Edge(f"edge:app_ui:{node_id}", "system:app_ui", node_id, "loads"))

    return CollectorResult(nodes=nodes, edges=edges, subgraphs={})
