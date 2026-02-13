from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from .graph_model import ArchitectureGraph, Node
from .item_ref import ItemRef

CATEGORY_CONTAINS = "contains"
CATEGORY_CONTAINED_BY = "contained_by"
CATEGORY_DEPENDS_ON = "depends_on"
CATEGORY_DEPENDENTS = "dependents"
CATEGORY_EXPORTS = "exports"

RELATION_CATEGORIES = (
    CATEGORY_CONTAINS,
    CATEGORY_CONTAINED_BY,
    CATEGORY_DEPENDS_ON,
    CATEGORY_DEPENDENTS,
    CATEGORY_EXPORTS,
)

EXPORT_METADATA_KEYS = (
    "exports",
    "export",
    "entry_points",
    "entrypoint",
    "entrypoints",
)


@dataclass(frozen=True)
class RelationRow:
    label: str
    item_ref: Optional[ItemRef]
    kind_badge: str
    detail: str = ""


@dataclass(frozen=True)
class RelationPage:
    rows: List[RelationRow]
    total: int


@dataclass
class RelationIndex:
    node_map: Dict[str, Node] = field(default_factory=dict)
    contains_out: Dict[str, List[str]] = field(default_factory=dict)
    contains_in: Dict[str, List[str]] = field(default_factory=dict)
    non_contains_out: Dict[str, List[tuple[str, str]]] = field(default_factory=dict)
    non_contains_in: Dict[str, List[tuple[str, str]]] = field(default_factory=dict)


def build_relation_index(
    active_root: Optional[ArchitectureGraph],
    active_subgraphs: Dict[str, ArchitectureGraph],
) -> RelationIndex:
    graphs = list(_iter_graphs(active_root, active_subgraphs))
    node_map: Dict[str, Node] = {}
    for graph in graphs:
        for node in graph.nodes:
            node_map.setdefault(node.node_id, node)

    contains_out_set: Dict[str, set[str]] = {}
    contains_in_set: Dict[str, set[str]] = {}
    non_contains_out_set: Dict[str, set[tuple[str, str]]] = {}
    non_contains_in_set: Dict[str, set[tuple[str, str]]] = {}
    seen_edges: set[tuple[str, str, str]] = set()

    for graph in graphs:
        for edge in graph.edges:
            src_id = str(edge.src_node_id)
            dst_id = str(edge.dst_node_id)
            kind = str(edge.kind or "")
            edge_key = (src_id, dst_id, kind)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            if src_id not in node_map or dst_id not in node_map:
                continue
            if kind == CATEGORY_CONTAINS:
                contains_out_set.setdefault(src_id, set()).add(dst_id)
                contains_in_set.setdefault(dst_id, set()).add(src_id)
                continue
            non_contains_out_set.setdefault(src_id, set()).add((dst_id, kind))
            non_contains_in_set.setdefault(dst_id, set()).add((src_id, kind))

    contains_out = {
        node_id: sorted(child_ids, key=lambda child_id: _node_sort_key(child_id, node_map))
        for node_id, child_ids in contains_out_set.items()
    }
    contains_in = {
        node_id: sorted(parent_ids, key=lambda parent_id: _node_sort_key(parent_id, node_map))
        for node_id, parent_ids in contains_in_set.items()
    }
    non_contains_out = {
        node_id: sorted(edges, key=lambda entry: _edge_out_sort_key(entry, node_map))
        for node_id, edges in non_contains_out_set.items()
    }
    non_contains_in = {
        node_id: sorted(edges, key=lambda entry: _edge_in_sort_key(entry, node_map))
        for node_id, edges in non_contains_in_set.items()
    }

    return RelationIndex(
        node_map=node_map,
        contains_out=contains_out,
        contains_in=contains_in,
        non_contains_out=non_contains_out,
        non_contains_in=non_contains_in,
    )


def query_relation_page(
    index: RelationIndex,
    item_ref: ItemRef,
    category: str,
    offset: int,
    limit: int,
    filter_text: str,
) -> RelationPage:
    if category not in RELATION_CATEGORIES:
        return RelationPage(rows=[], total=0)
    if item_ref.kind != "node":
        return RelationPage(rows=[], total=0)
    node_id = str(item_ref.id)
    if node_id not in index.node_map:
        return RelationPage(rows=[], total=0)

    if category == CATEGORY_CONTAINS:
        rows = _node_rows(index, index.contains_out.get(node_id, []))
    elif category == CATEGORY_CONTAINED_BY:
        rows = _node_rows(index, index.contains_in.get(node_id, []))
    elif category == CATEGORY_DEPENDS_ON:
        rows = _edge_rows(index, index.non_contains_out.get(node_id, []))
    elif category == CATEGORY_DEPENDENTS:
        rows = _edge_rows(index, index.non_contains_in.get(node_id, []))
    else:
        rows = _exports_rows(index, index.node_map[node_id])

    needle = (filter_text or "").strip().lower()
    if needle:
        rows = [row for row in rows if _relation_row_matches(row, needle)]
    rows = sorted(rows, key=_relation_row_sort_key)
    total = len(rows)

    safe_offset = max(0, int(offset))
    safe_limit = max(0, int(limit))
    if safe_limit == 0:
        return RelationPage(rows=[], total=total)
    return RelationPage(rows=rows[safe_offset : safe_offset + safe_limit], total=total)


def _iter_graphs(
    active_root: Optional[ArchitectureGraph],
    active_subgraphs: Dict[str, ArchitectureGraph],
) -> Iterable[ArchitectureGraph]:
    seen: set[str] = set()
    if active_root is not None:
        key = str(active_root.graph_id)
        seen.add(key)
        yield active_root
    for graph in active_subgraphs.values():
        if graph is None:
            continue
        key = str(graph.graph_id)
        if key in seen:
            continue
        seen.add(key)
        yield graph


def _node_rows(index: RelationIndex, node_ids: List[str]) -> List[RelationRow]:
    rows: List[RelationRow] = []
    for node_id in node_ids:
        node = index.node_map.get(node_id)
        if node is None:
            continue
        rows.append(
            RelationRow(
                label=_node_label(node),
                item_ref=ItemRef(kind="node", id=node.node_id),
                kind_badge=str(node.node_type or "node"),
            )
        )
    return rows


def _edge_rows(index: RelationIndex, edges: List[tuple[str, str]]) -> List[RelationRow]:
    rows: List[RelationRow] = []
    for related_id, edge_kind in edges:
        node = index.node_map.get(related_id)
        if node is None:
            continue
        rows.append(
            RelationRow(
                label=_node_label(node),
                item_ref=ItemRef(kind="node", id=node.node_id),
                kind_badge=str(node.node_type or "node"),
                detail=f"edge: {edge_kind or 'unknown'}",
            )
        )
    return rows


def _exports_rows(index: RelationIndex, node: Node) -> List[RelationRow]:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    rows: List[RelationRow] = []
    seen: set[tuple[str, str, str, str]] = set()
    for key in EXPORT_METADATA_KEYS:
        if key not in metadata:
            continue
        for token in _flatten_metadata_values(metadata.get(key)):
            value = token.strip()
            if not value:
                continue
            if value in index.node_map:
                target = index.node_map[value]
                row = RelationRow(
                    label=_node_label(target),
                    item_ref=ItemRef(kind="node", id=target.node_id),
                    kind_badge=str(target.node_type or "node"),
                    detail=f"metadata: {key}",
                )
            else:
                row = RelationRow(
                    label=value,
                    item_ref=None,
                    kind_badge="entry",
                    detail=f"metadata: {key}",
                )
            dedupe_key = (row.label, row.item_ref.id if row.item_ref else "", row.kind_badge, row.detail)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(row)
    return rows


def _flatten_metadata_values(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        values: List[str] = []
        for key, sub_value in value.items():
            values.extend(_flatten_metadata_values(key))
            values.extend(_flatten_metadata_values(sub_value))
        return values
    if isinstance(value, (list, tuple, set)):
        values: List[str] = []
        for entry in value:
            values.extend(_flatten_metadata_values(entry))
        return values
    return [str(value)]


def _relation_row_matches(row: RelationRow, needle: str) -> bool:
    hay = [row.label, row.detail]
    if row.item_ref is not None:
        hay.append(str(row.item_ref.id))
    return needle in " ".join(hay).lower()


def _relation_row_sort_key(row: RelationRow) -> tuple[str, str, str]:
    row_id = row.item_ref.id if row.item_ref is not None else ""
    return (row.label.strip().lower(), str(row_id).strip().lower(), row.detail.strip().lower())


def _node_sort_key(node_id: str, node_map: Dict[str, Node]) -> tuple[str, str]:
    node = node_map.get(node_id)
    title = node.title if node else ""
    return (str(title or "").strip().lower(), str(node_id))


def _edge_out_sort_key(entry: tuple[str, str], node_map: Dict[str, Node]) -> tuple[str, str, str]:
    dst_id, edge_kind = entry
    node = node_map.get(dst_id)
    title = node.title if node else ""
    return (str(title or "").strip().lower(), str(dst_id), str(edge_kind))


def _edge_in_sort_key(entry: tuple[str, str], node_map: Dict[str, Node]) -> tuple[str, str, str]:
    src_id, edge_kind = entry
    node = node_map.get(src_id)
    title = node.title if node else ""
    return (str(title or "").strip().lower(), str(src_id), str(edge_kind))


def _node_label(node: Node) -> str:
    return str(node.title or node.node_id)

