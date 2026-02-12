from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from .graph_model import ArchitectureGraph, Node
from .item_ref import ItemRef

MAX_PEEK_ADD_PER_EXPAND = 150
MAX_PEEK_VISIBLE_TOTAL = 1200


@dataclass
class PeekContext:
    peek_active: bool = False
    peek_root: Optional[ItemRef] = None
    peek_visible: set[ItemRef] = field(default_factory=set)
    peek_expanded: set[ItemRef] = field(default_factory=set)
    peek_breadcrumb: list[ItemRef] = field(default_factory=list)
    include_external_context: bool = False
    parent_by_id: dict[str, Optional[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class PeekBudgetResult:
    allowed_child_ids: list[str]
    omitted_count: int
    blocked_total: bool
    clamped: bool


def build_containment_index(
    active_root: Optional[ArchitectureGraph],
    active_subgraphs: Dict[str, ArchitectureGraph],
) -> tuple[Dict[str, Node], Dict[str, List[str]]]:
    graphs: list[ArchitectureGraph] = []
    if active_root is not None:
        graphs.append(active_root)
    for graph in active_subgraphs.values():
        if graph is None:
            continue
        if any(existing.graph_id == graph.graph_id for existing in graphs):
            continue
        graphs.append(graph)

    node_map: Dict[str, Node] = {}
    for graph in graphs:
        for node in graph.nodes:
            node_map.setdefault(node.node_id, node)

    children_by_id: Dict[str, set[str]] = {}
    for graph in graphs:
        for edge in graph.edges:
            if edge.kind != "contains":
                continue
            if edge.src_node_id not in node_map or edge.dst_node_id not in node_map:
                continue
            children_by_id.setdefault(edge.src_node_id, set()).add(edge.dst_node_id)

    ordered_children: Dict[str, List[str]] = {}
    for node_id, child_ids in children_by_id.items():
        ordered_children[node_id] = sorted(child_ids, key=lambda cid: _stable_sort_key(cid, node_map))

    return node_map, ordered_children


def apply_expand_budget(
    child_ids: Sequence[str],
    *,
    current_visible_total: int,
    max_add_per_expand: int = MAX_PEEK_ADD_PER_EXPAND,
    max_visible_total: int = MAX_PEEK_VISIBLE_TOTAL,
) -> PeekBudgetResult:
    ordered = list(child_ids)
    if not ordered:
        return PeekBudgetResult([], 0, False, False)
    remaining_capacity = max(0, int(max_visible_total) - int(current_visible_total))
    if remaining_capacity <= 0:
        return PeekBudgetResult([], len(ordered), True, False)

    add_limit = max(0, min(int(max_add_per_expand), remaining_capacity))
    allowed = ordered[:add_limit]
    omitted = max(0, len(ordered) - len(allowed))
    clamped = omitted > 0 and len(allowed) > 0
    blocked_total = len(allowed) == 0 and omitted > 0
    return PeekBudgetResult(allowed, omitted, blocked_total, clamped)


def collapse_subtree_ids(root_id: str, parent_by_id: Dict[str, Optional[str]]) -> set[str]:
    children_by_parent: Dict[str, list[str]] = {}
    for node_id, parent in parent_by_id.items():
        if parent is None:
            continue
        children_by_parent.setdefault(parent, []).append(node_id)
    to_remove: set[str] = set()
    stack = list(children_by_parent.get(root_id, []))
    while stack:
        node_id = stack.pop()
        if node_id in to_remove:
            continue
        to_remove.add(node_id)
        stack.extend(children_by_parent.get(node_id, []))
    return to_remove


def breadcrumb_chain_ids(node_id: str, parent_by_id: Dict[str, Optional[str]]) -> list[str]:
    chain: list[str] = []
    seen: set[str] = set()
    cursor: Optional[str] = node_id
    while cursor:
        if cursor in seen:
            break
        seen.add(cursor)
        chain.append(cursor)
        cursor = parent_by_id.get(cursor)
    chain.reverse()
    return chain


def item_ref_for_node_id(node_id: str) -> ItemRef:
    return ItemRef(kind="node", id=str(node_id))


def has_unloaded_subgraph(node: Optional[Node], active_subgraphs: Dict[str, ArchitectureGraph]) -> bool:
    if node is None:
        return False
    subgraph_id = (node.subgraph_id or "").strip()
    if not subgraph_id:
        return False
    return subgraph_id not in active_subgraphs


def _stable_sort_key(node_id: str, node_map: Dict[str, Node]) -> tuple[str, str]:
    node = node_map.get(node_id)
    title = (node.title if node else "") or ""
    return (title.strip().lower(), str(node_id))
