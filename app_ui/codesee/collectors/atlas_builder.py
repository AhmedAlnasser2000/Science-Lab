from __future__ import annotations

from typing import Dict, List

from ..badges import badges_from_keys
from ..expectations import build_check
from ..graph_model import ArchitectureGraph, Edge, Node
from .base import CollectorContext, CollectorResult
from .content_collector import collect_content
from .inventory_collector import collect_inventory
from .platform_collector import collect_platform


def build_atlas_graph(ctx: CollectorContext) -> tuple[ArchitectureGraph, Dict[str, ArchitectureGraph]]:
    workspace_node = Node(
        node_id=f"workspace:{ctx.workspace_id}",
        title=f"Project: {ctx.workspace_id}",
        node_type="Workspace",
        badges=badges_from_keys(bottom=["workspace"]),
        checks=[
            build_check(
                check_id="atlas.workspace.present",
                node_id=f"workspace:{ctx.workspace_id}",
                expected=True,
                actual=True,
                mode="exact",
                message="Workspace root present.",
            )
        ],
    )

    results = [
        collect_platform(ctx),
        collect_inventory(ctx),
        collect_content(ctx),
    ]

    node_map: Dict[str, Node] = {workspace_node.node_id: workspace_node}
    edges: List[Edge] = []
    subgraphs: Dict[str, ArchitectureGraph] = {}

    for result in results:
        _merge_nodes(node_map, result.nodes)
        edges.extend(result.edges)
        for graph_id, graph in result.subgraphs.items():
            if graph_id not in subgraphs:
                subgraphs[graph_id] = graph

    for node in node_map.values():
        if node is workspace_node:
            continue
        if node.node_type in ("Pack", "Topic"):
            edges.append(
                Edge(
                    f"edge:{workspace_node.node_id}:{node.node_id}",
                    workspace_node.node_id,
                    node.node_id,
                    "contains",
                )
            )
        if node.node_id == "system:app_ui":
            edges.append(
                Edge(
                    f"edge:{workspace_node.node_id}:{node.node_id}",
                    workspace_node.node_id,
                    node.node_id,
                    "contains",
                )
            )

    graph = ArchitectureGraph(
        graph_id="atlas",
        title="Atlas",
        nodes=list(node_map.values()),
        edges=_dedupe_edges(edges),
    )

    return graph, subgraphs


def _merge_nodes(node_map: Dict[str, Node], nodes: List[Node]) -> None:
    for node in nodes:
        if node.node_id not in node_map:
            node_map[node.node_id] = node


def _dedupe_edges(edges: List[Edge]) -> List[Edge]:
    seen = set()
    result: List[Edge] = []
    for edge in edges:
        key = (edge.src_node_id, edge.dst_node_id, edge.kind)
        if key in seen:
            continue
        seen.add(key)
        result.append(edge)
    return result
