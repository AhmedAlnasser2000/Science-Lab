from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .graph_model import ArchitectureGraph, Edge, Node

FORMAT_VERSION = 1


def write_snapshot(graph: ArchitectureGraph, path: Path, metadata: Dict[str, Any]) -> None:
    payload = {
        "format_version": FORMAT_VERSION,
        "graph": _graph_to_dict(graph),
        "metadata": metadata or {},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        return


def read_snapshot(path: Path) -> ArchitectureGraph:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("snapshot payload not a dict")
    if data.get("format_version") != FORMAT_VERSION:
        raise ValueError("unsupported snapshot format")
    graph = data.get("graph")
    if not isinstance(graph, dict):
        raise ValueError("snapshot missing graph")
    return _graph_from_dict(graph)


def _graph_to_dict(graph: ArchitectureGraph) -> Dict[str, Any]:
    return {
        "graph_id": graph.graph_id,
        "title": graph.title,
        "nodes": [_node_to_dict(node) for node in graph.nodes],
        "edges": [_edge_to_dict(edge) for edge in graph.edges],
    }


def _node_to_dict(node: Node) -> Dict[str, Any]:
    return {
        "id": node.node_id,
        "title": node.title,
        "type": node.node_type,
        "severity_state": node.severity_state,
        "badges_top": list(node.badges_top),
        "badges_bottom": list(node.badges_bottom),
        "subgraph_id": node.subgraph_id,
    }


def _edge_to_dict(edge: Edge) -> Dict[str, Any]:
    return {
        "id": edge.edge_id,
        "src": edge.src_node_id,
        "dst": edge.dst_node_id,
        "kind": edge.kind,
    }


def _graph_from_dict(graph: Dict[str, Any]) -> ArchitectureGraph:
    graph_id = str(graph.get("graph_id") or "snapshot")
    title = str(graph.get("title") or graph_id)
    nodes = []
    for raw in graph.get("nodes") or []:
        if not isinstance(raw, dict):
            continue
        node_id = str(raw.get("id") or "")
        if not node_id:
            continue
        nodes.append(
            Node(
                node_id=node_id,
                title=str(raw.get("title") or node_id),
                node_type=str(raw.get("type") or "System"),
                severity_state=str(raw.get("severity_state") or "normal"),
                badges_top=list(raw.get("badges_top") or []),
                badges_bottom=list(raw.get("badges_bottom") or []),
                subgraph_id=raw.get("subgraph_id"),
            )
        )
    edges = []
    for raw in graph.get("edges") or []:
        if not isinstance(raw, dict):
            continue
        edge_id = str(raw.get("id") or "")
        src = str(raw.get("src") or "")
        dst = str(raw.get("dst") or "")
        if not edge_id or not src or not dst:
            continue
        edges.append(Edge(edge_id=edge_id, src_node_id=src, dst_node_id=dst, kind=str(raw.get("kind") or "contains")))
    return ArchitectureGraph(graph_id=graph_id, title=title, nodes=nodes, edges=edges)
