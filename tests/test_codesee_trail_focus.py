from app_ui.codesee.runtime.trail_focus import (
    clamp_inactive_edge_opacity,
    clamp_inactive_node_opacity,
    clamp_monitor_border_px,
    compute_trail_focus,
)


def test_compute_trail_focus_sets_nodes_and_edges() -> None:
    result = compute_trail_focus(
        visible_nodes={"a", "b", "c", "d"},
        visible_edges={("a", "b"), ("b", "c"), ("c", "d")},
        monitor_states={
            "b": {"state": "RUNNING"},
            "d": {"state": "INACTIVE"},
        },
        trace_nodes={"c"},
        trace_edges=[("a", "b"), ("d", "c"), ("x", "y")],
        selected_node_ids={"a"},
        context_node_ids=set(),
        enabled=True,
        inactive_node_opacity=0.4,
        inactive_edge_opacity=0.2,
    )
    assert result.focus_nodes == {"a", "b", "c"}
    assert result.focus_edges == {("a", "b"), ("c", "d")}


def test_compute_trail_focus_opacity_enabled() -> None:
    result = compute_trail_focus(
        visible_nodes={"a", "b"},
        visible_edges={("a", "b"), ("b", "a")},
        monitor_states={"a": {"state": "FATAL"}},
        trace_nodes=set(),
        trace_edges=[],
        selected_node_ids=set(),
        context_node_ids=set(),
        enabled=True,
        inactive_node_opacity=0.35,
        inactive_edge_opacity=0.2,
    )
    assert result.node_opacity["a"] == 1.0
    assert result.node_opacity["b"] == 0.35
    assert result.edge_opacity[("a", "b")] == 0.2
    assert result.edge_opacity[("b", "a")] == 0.2


def test_compute_trail_focus_opacity_disabled_restores_all() -> None:
    result = compute_trail_focus(
        visible_nodes={"a", "b"},
        visible_edges={("a", "b")},
        monitor_states={"a": {"state": "RUNNING"}},
        trace_nodes={"a"},
        trace_edges=[("a", "b")],
        selected_node_ids={"a"},
        context_node_ids=set(),
        enabled=False,
        inactive_node_opacity=0.2,
        inactive_edge_opacity=0.1,
    )
    assert result.node_opacity == {"a": 1.0, "b": 1.0}
    assert result.edge_opacity == {("a", "b"): 1.0}


def test_trail_focus_clamps_settings() -> None:
    assert clamp_inactive_node_opacity(-1.0) == 0.10
    assert clamp_inactive_node_opacity(5.0) == 1.0
    assert clamp_inactive_edge_opacity(-1.0) == 0.05
    assert clamp_inactive_edge_opacity(5.0) == 1.0
    assert clamp_monitor_border_px(-4) == 1
    assert clamp_monitor_border_px(99) == 6


def test_compute_trail_focus_includes_context_nodes() -> None:
    result = compute_trail_focus(
        visible_nodes={"system:app_ui", "system:core_center"},
        visible_edges={("system:app_ui", "system:core_center")},
        monitor_states={},
        trace_nodes=set(),
        trace_edges=[],
        selected_node_ids=set(),
        context_node_ids={"system:app_ui"},
        enabled=True,
        inactive_node_opacity=0.4,
        inactive_edge_opacity=0.2,
    )
    assert result.focus_nodes == {"system:app_ui"}
    assert result.node_opacity["system:app_ui"] == 1.0
    assert result.node_opacity["system:core_center"] == 0.4
