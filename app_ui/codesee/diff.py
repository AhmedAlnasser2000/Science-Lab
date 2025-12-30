from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Dict, List, Set, Tuple

from .badges import Badge
from .expectations import EVACheck
from .graph_model import ArchitectureGraph, Edge, Node
from .runtime.events import SpanRecord

EdgeKey = Tuple[str, str, str]


@dataclass(frozen=True)
class NodeChange:
    before: Node
    after: Node
    fields_changed: List[str]
    badges_before: List[Badge] = field(default_factory=list)
    badges_after: List[Badge] = field(default_factory=list)
    severity_before: str = "normal"
    severity_after: str = "normal"


@dataclass
class DiffResult:
    nodes_added: Set[str] = field(default_factory=set)
    nodes_removed: Set[str] = field(default_factory=set)
    nodes_changed: Set[str] = field(default_factory=set)
    edges_added: Set[EdgeKey] = field(default_factory=set)
    edges_removed: Set[EdgeKey] = field(default_factory=set)
    node_change_details: Dict[str, NodeChange] = field(default_factory=dict)


def diff_snapshots(a_graph: ArchitectureGraph, b_graph: ArchitectureGraph) -> DiffResult:
    result = DiffResult()
    a_nodes = {node.node_id: node for node in a_graph.nodes}
    b_nodes = {node.node_id: node for node in b_graph.nodes}

    result.nodes_added = set(b_nodes.keys()) - set(a_nodes.keys())
    result.nodes_removed = set(a_nodes.keys()) - set(b_nodes.keys())
    shared_ids = set(a_nodes.keys()) & set(b_nodes.keys())

    for node_id in shared_ids:
        before = a_nodes[node_id]
        after = b_nodes[node_id]
        changed_fields = _node_changed_fields(before, after)
        if changed_fields:
            result.nodes_changed.add(node_id)
            result.node_change_details[node_id] = NodeChange(
                before=before,
                after=after,
                fields_changed=changed_fields,
                badges_before=list(before.badges),
                badges_after=list(after.badges),
                severity_before=before.effective_severity(),
                severity_after=after.effective_severity(),
            )

    a_edges = {edge_key(edge) for edge in a_graph.edges}
    b_edges = {edge_key(edge) for edge in b_graph.edges}
    result.edges_added = b_edges - a_edges
    result.edges_removed = a_edges - b_edges

    return result


def edge_key(edge: Edge) -> EdgeKey:
    return (edge.src_node_id, edge.dst_node_id, edge.kind)


def _badge_signature(badge: Badge) -> Tuple[str, str, str, str, str, str]:
    return (
        badge.key,
        badge.rail,
        badge.title,
        badge.summary,
        badge.detail or "",
        badge.severity or "",
    )


def _check_signature(check: EVACheck) -> Tuple[str, bool, str, str, str, float]:
    return (
        check.check_id,
        check.passed,
        str(check.expected),
        str(check.actual),
        check.mode,
        float(check.tolerance or 0.0),
    )


def _span_signature(span: SpanRecord) -> Tuple[str, str, str, str, str, str]:
    return (
        span.span_id,
        span.status,
        span.label,
        str(span.progress),
        str(span.message),
        span.severity or "",
    )


def _node_changed_fields(before: Node, after: Node) -> List[str]:
    changed: List[str] = []
    if before.title != after.title:
        changed.append("title")
    if before.node_type != after.node_type:
        changed.append("type")
    if before.effective_severity() != after.effective_severity():
        changed.append("severity")
    before_badges = sorted(_badge_signature(badge) for badge in before.badges)
    after_badges = sorted(_badge_signature(badge) for badge in after.badges)
    if before_badges != after_badges:
        changed.append("badges")
    before_checks = sorted(_check_signature(check) for check in before.checks)
    after_checks = sorted(_check_signature(check) for check in after.checks)
    if before_checks != after_checks:
        changed.append("checks")
    before_spans = sorted(_span_signature(span) for span in before.spans)
    after_spans = sorted(_span_signature(span) for span in after.spans)
    if before_spans != after_spans:
        changed.append("spans")
    if _metadata_signature(before.metadata) != _metadata_signature(after.metadata):
        changed.append("metadata")
    return changed


def _metadata_signature(metadata: dict) -> str:
    if not isinstance(metadata, dict):
        return ""
    try:
        return json.dumps(metadata, sort_keys=True, default=str)
    except Exception:
        return str(metadata)
