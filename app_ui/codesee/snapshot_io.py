from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .badges import badge_from_dict, badge_from_key, badge_to_dict
from .expectations import check_from_dict, check_to_dict
from .runtime.events import span_from_dict, span_to_dict
from . import snapshot_index
from .graph_model import ArchitectureGraph, Edge, Node
from app_ui import versioning

FORMAT_VERSION = 3


def write_snapshot(graph: ArchitectureGraph, path: Path, metadata: Dict[str, Any]) -> None:
    build_info = versioning.get_build_info()
    meta = dict(metadata or {})
    meta.setdefault("build", build_info)
    payload = {
        "format_version": FORMAT_VERSION,
        "graph": _graph_to_dict(graph),
        "metadata": meta,
        "build": build_info,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        snapshot_index.register_snapshot(path, payload["metadata"])
    except Exception:
        return


def read_snapshot(path: Path) -> ArchitectureGraph:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("snapshot payload not a dict")
    if data.get("format_version") not in (1, 2, FORMAT_VERSION):
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
        "badges": [badge_to_dict(badge) for badge in node.badges],
        "checks": [_check_to_dict(check) for check in node.checks],
        "spans": [_span_to_dict(span) for span in node.spans],
        "subgraph_id": node.subgraph_id,
        "metadata": _normalize_metadata(node.metadata),
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
        badges = _badges_from_raw(raw)
        nodes.append(
            Node(
                node_id=node_id,
                title=str(raw.get("title") or node_id),
                node_type=str(raw.get("type") or "System"),
                badges=badges,
                severity_state=_optional_str(raw.get("severity_state")),
                subgraph_id=raw.get("subgraph_id"),
                checks=_checks_from_raw(raw),
                spans=_spans_from_raw(raw),
                metadata=_normalize_metadata(raw.get("metadata")),
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


def _badges_from_raw(raw: Dict[str, Any]) -> list:
    badges = []
    raw_badges = raw.get("badges")
    if isinstance(raw_badges, list):
        for item in raw_badges:
            if isinstance(item, dict):
                badge = badge_from_dict(item)
                if badge:
                    badges.append(badge)
            elif isinstance(item, str):
                badges.append(badge_from_key(item))
    top = raw.get("badges_top") or []
    bottom = raw.get("badges_bottom") or []
    if isinstance(top, list):
        for key in top:
            if isinstance(key, str):
                badges.append(badge_from_key(key, rail="top"))
    if isinstance(bottom, list):
        for key in bottom:
            if isinstance(key, str):
                badges.append(badge_from_key(key, rail="bottom"))
    return badges


def _checks_from_raw(raw: Dict[str, Any]) -> list:
    checks = []
    raw_checks = raw.get("checks")
    if isinstance(raw_checks, list):
        for item in raw_checks:
            if isinstance(item, dict):
                check = check_from_dict(item)
                if check:
                    checks.append(check)
    return checks


def _spans_from_raw(raw: Dict[str, Any]) -> list:
    spans = []
    raw_spans = raw.get("spans")
    if isinstance(raw_spans, list):
        for item in raw_spans:
            if isinstance(item, dict):
                span = span_from_dict(item)
                if span:
                    spans.append(span)
    return spans


def _check_to_dict(check) -> Dict[str, Any]:
    if isinstance(check, dict):
        return check
    return check_to_dict(check)


def _span_to_dict(span) -> Dict[str, Any]:
    if isinstance(span, dict):
        return span
    return span_to_dict(span)


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_metadata(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return _sanitize_json_value(value)


def _sanitize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_json_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
