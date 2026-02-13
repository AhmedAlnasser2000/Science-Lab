from app_ui.codesee.graph_model import ArchitectureGraph, Edge, Node
from app_ui.codesee.item_ref import ItemRef
from app_ui.codesee.relations import (
    CATEGORY_CONTAINED_BY,
    CATEGORY_CONTAINS,
    CATEGORY_DEPENDENTS,
    CATEGORY_DEPENDS_ON,
    CATEGORY_EXPORTS,
    build_relation_index,
    query_relation_page,
)


def test_contains_and_contained_by_and_dedupe_across_graphs() -> None:
    root = ArchitectureGraph(
        graph_id="root",
        title="Root",
        nodes=[
            Node("a", "A", "module"),
            Node("b", "B", "component"),
            Node("c", "C", "component"),
            Node("d", "D", "component"),
        ],
        edges=[
            Edge("e1", "a", "b", "contains"),
            Edge("e2", "a", "c", "depends"),
            Edge("e3", "d", "a", "loads"),
        ],
    )
    sub = ArchitectureGraph(
        graph_id="sub",
        title="Sub",
        nodes=[Node("a", "A", "module"), Node("b", "B", "component")],
        edges=[Edge("dup", "a", "b", "contains")],
    )
    index = build_relation_index(root, {"sub": sub})

    contains_page = query_relation_page(index, ItemRef("node", "a"), CATEGORY_CONTAINS, 0, 50, "")
    assert contains_page.total == 1
    assert [row.item_ref.id for row in contains_page.rows if row.item_ref] == ["b"]

    parent_page = query_relation_page(index, ItemRef("node", "b"), CATEGORY_CONTAINED_BY, 0, 50, "")
    assert parent_page.total == 1
    assert [row.item_ref.id for row in parent_page.rows if row.item_ref] == ["a"]


def test_depends_and_dependents_include_edge_kind_detail() -> None:
    graph = ArchitectureGraph(
        graph_id="g",
        title="Graph",
        nodes=[
            Node("a", "A", "module"),
            Node("c", "C", "module"),
            Node("d", "D", "module"),
        ],
        edges=[
            Edge("e1", "a", "c", "depends"),
            Edge("e2", "a", "c", "provides"),
            Edge("e3", "d", "a", "loads"),
        ],
    )
    index = build_relation_index(graph, {})

    outgoing = query_relation_page(index, ItemRef("node", "a"), CATEGORY_DEPENDS_ON, 0, 50, "")
    assert outgoing.total == 2
    assert sorted(row.detail for row in outgoing.rows) == ["edge: depends", "edge: provides"]

    incoming = query_relation_page(index, ItemRef("node", "a"), CATEGORY_DEPENDENTS, 0, 50, "")
    assert incoming.total == 1
    assert incoming.rows[0].item_ref.id == "d"
    assert incoming.rows[0].detail == "edge: loads"


def test_paging_and_filtering() -> None:
    nodes = [Node("root", "Root", "module")]
    edges = []
    for idx in range(120):
        node_id = f"child.{idx:03d}"
        nodes.append(Node(node_id, f"Child {idx:03d}", "component"))
        edges.append(Edge(f"edge:{idx}", "root", node_id, "contains"))
    graph = ArchitectureGraph(graph_id="g", title="Graph", nodes=nodes, edges=edges)
    index = build_relation_index(graph, {})

    first = query_relation_page(index, ItemRef("node", "root"), CATEGORY_CONTAINS, 0, 50, "")
    second = query_relation_page(index, ItemRef("node", "root"), CATEGORY_CONTAINS, 50, 50, "")
    tail = query_relation_page(index, ItemRef("node", "root"), CATEGORY_CONTAINS, 100, 50, "")
    assert first.total == 120 and len(first.rows) == 50
    assert second.total == 120 and len(second.rows) == 50
    assert tail.total == 120 and len(tail.rows) == 20

    filtered_by_name = query_relation_page(index, ItemRef("node", "root"), CATEGORY_CONTAINS, 0, 50, "child 011")
    assert filtered_by_name.total == 1
    assert filtered_by_name.rows[0].item_ref.id == "child.011"

    filtered_by_id = query_relation_page(index, ItemRef("node", "root"), CATEGORY_CONTAINS, 0, 50, "child.099")
    assert filtered_by_id.total == 1
    assert filtered_by_id.rows[0].item_ref.id == "child.099"


def test_exports_parse_metadata_to_inspectable_and_entry_rows() -> None:
    graph = ArchitectureGraph(
        graph_id="g",
        title="Graph",
        nodes=[
            Node(
                "host",
                "Host",
                "module",
                metadata={
                    "entry_points": ["svc.api", "ghost.route"],
                    "exports": {"main": "svc.main", "other": "custom.token"},
                },
            ),
            Node("svc.api", "Service API", "component"),
            Node("svc.main", "Main Service", "component"),
        ],
        edges=[],
    )
    index = build_relation_index(graph, {})
    page = query_relation_page(index, ItemRef("node", "host"), CATEGORY_EXPORTS, 0, 50, "")
    inspectable_ids = {row.item_ref.id for row in page.rows if row.item_ref is not None}
    entry_labels = {row.label for row in page.rows if row.item_ref is None}
    assert "svc.api" in inspectable_ids
    assert "svc.main" in inspectable_ids
    assert "ghost.route" in entry_labels
    assert "custom.token" in entry_labels


def test_missing_or_non_node_item_returns_empty() -> None:
    graph = ArchitectureGraph(
        graph_id="g",
        title="Graph",
        nodes=[Node("a", "A", "module")],
        edges=[],
    )
    index = build_relation_index(graph, {})

    missing = query_relation_page(index, ItemRef("node", "missing"), CATEGORY_CONTAINS, 0, 50, "")
    assert missing.total == 0
    assert missing.rows == []

    non_node = query_relation_page(index, ItemRef("edge", "e1"), CATEGORY_CONTAINS, 0, 50, "")
    assert non_node.total == 0
    assert non_node.rows == []

