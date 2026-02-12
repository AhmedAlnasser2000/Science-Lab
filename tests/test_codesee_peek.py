from app_ui.codesee.graph_model import ArchitectureGraph, Edge, Node
from app_ui.codesee.peek import (
    MAX_PEEK_ADD_PER_EXPAND,
    MAX_PEEK_VISIBLE_TOTAL,
    apply_expand_budget,
    breadcrumb_chain_ids,
    build_containment_index,
    collapse_subtree_ids,
    has_unloaded_subgraph,
)


def test_build_containment_index_contains_only_and_stable_order() -> None:
    root = ArchitectureGraph(
        graph_id="atlas",
        title="Atlas",
        nodes=[
            Node("root", "Root", "Workspace"),
            Node("child_b", "B Child", "Block"),
            Node("child_a", "A Child", "Block"),
        ],
        edges=[
            Edge("e1", "root", "child_b", "contains"),
            Edge("e2", "root", "child_a", "contains"),
            Edge("e3", "root", "child_a", "depends"),
        ],
    )
    node_map, children = build_containment_index(root, {})
    assert set(node_map.keys()) == {"root", "child_b", "child_a"}
    assert children["root"] == ["child_a", "child_b"]


def test_apply_expand_budget_clamp_and_total_block() -> None:
    child_ids = [f"n{i}" for i in range(200)]
    clamped = apply_expand_budget(
        child_ids,
        current_visible_total=1,
        max_add_per_expand=MAX_PEEK_ADD_PER_EXPAND,
        max_visible_total=MAX_PEEK_VISIBLE_TOTAL,
    )
    assert len(clamped.allowed_child_ids) == 150
    assert clamped.omitted_count == 50
    assert clamped.clamped is True
    assert clamped.blocked_total is False

    blocked = apply_expand_budget(
        child_ids,
        current_visible_total=MAX_PEEK_VISIBLE_TOTAL,
        max_add_per_expand=MAX_PEEK_ADD_PER_EXPAND,
        max_visible_total=MAX_PEEK_VISIBLE_TOTAL,
    )
    assert blocked.allowed_child_ids == []
    assert blocked.blocked_total is True
    assert blocked.omitted_count == len(child_ids)


def test_collapse_subtree_and_breadcrumb_chain() -> None:
    parent_by_id = {
        "root": None,
        "a": "root",
        "b": "a",
        "c": "root",
        "d": "c",
    }
    assert collapse_subtree_ids("a", parent_by_id) == {"b"}
    assert collapse_subtree_ids("root", parent_by_id) == {"a", "b", "c", "d"}
    assert breadcrumb_chain_ids("b", parent_by_id) == ["root", "a", "b"]


def test_unloaded_subgraph_hint() -> None:
    node = Node("n1", "Node", "Block", subgraph_id="sub:one")
    assert has_unloaded_subgraph(node, {}) is True
    assert has_unloaded_subgraph(node, {"sub:one": ArchitectureGraph("sub:one", "Sub", [], [])}) is False
