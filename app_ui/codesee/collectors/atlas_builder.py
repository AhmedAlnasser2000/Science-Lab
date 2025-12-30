from __future__ import annotations

from typing import Dict, List

from ..badges import badges_from_keys
from ..expectations import build_check
from ..graph_model import ArchitectureGraph, Edge, Node
from ..runtime.hub import recent_checks
from .base import CollectorContext, CollectorResult
from .content_collector import collect_content
from .inventory_collector import collect_inventory
from .lab_collector import collect_labs
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
        collect_labs(ctx),
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
        if node.node_type in ("Pack", "Topic", "Lab"):
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

    _apply_runtime_checks(node_map, recent_checks(), fallback_node_id=workspace_node.node_id)

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


def _apply_runtime_checks(
    node_map: Dict[str, Node],
    checks: List,
    *,
    fallback_node_id: str,
) -> None:
    if not checks:
        return
    fallback_id = "system:content_system" if "system:content_system" in node_map else fallback_node_id
    bucket: Dict[str, List] = {}
    for check in checks:
        node_id = check.node_id if getattr(check, "node_id", None) in node_map else fallback_id
        bucket.setdefault(node_id, []).append(check)
    for node_id, extra in bucket.items():
        node = node_map.get(node_id)
        if not node:
            continue
        merged = list(node.checks) + list(extra)
        node_map[node_id] = Node(
            node_id=node.node_id,
            title=node.title,
            node_type=node.node_type,
            subgraph_id=node.subgraph_id,
            badges=node.badges,
            severity_state=node.severity_state,
            checks=merged,
        )


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
