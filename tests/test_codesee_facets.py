from PyQt6 import QtWidgets

from app_ui.codesee import view_config
from app_ui.codesee.graph_model import ArchitectureGraph, Edge, Node
from app_ui.codesee.screen import (
    SOURCE_ATLAS,
    SOURCE_DEMO,
    CodeSeeScreen,
    _facet_enabled_defaults_for_density,
)


def _test_graph() -> ArchitectureGraph:
    return ArchitectureGraph(
        graph_id="root",
        title="Root",
        nodes=[
            Node("module.a", "A", "module"),
            Node("module.b", "B", "module"),
            Node("workspace.x", "W", "Workspace"),
        ],
        edges=[Edge("e1", "module.a", "module.b", "dependency")],
    )


def _make_screen() -> CodeSeeScreen:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return CodeSeeScreen(
        on_back=lambda: None,
        workspace_info_provider=lambda: {"id": "default"},
        allow_detach=False,
    )


def test_facet_density_profile_mapping() -> None:
    assert _facet_enabled_defaults_for_density("off") == {key: False for key in view_config.FACET_KEYS}
    minimal = _facet_enabled_defaults_for_density("minimal")
    assert minimal["deps"] is True
    assert minimal["activity"] is True
    assert minimal["packs"] is False
    standard = _facet_enabled_defaults_for_density("standard")
    assert standard["packs"] is True
    assert standard["entry_points"] is True
    assert standard["spans"] is True
    expanded = _facet_enabled_defaults_for_density("expanded")
    assert expanded["runs"] is True
    assert expanded["logs"] is True
    debug = _facet_enabled_defaults_for_density("debug")
    assert all(debug[key] for key in view_config.FACET_KEYS)


def test_system_map_facet_injection_is_deterministic_and_unique() -> None:
    screen = _make_screen()
    screen._source = SOURCE_DEMO
    screen._facet_settings = view_config.FacetSettings(
        density="minimal",
        enabled=_facet_enabled_defaults_for_density("minimal"),
        show_in_normal_view=True,
        show_in_peek_view=True,
    )
    graph = _test_graph()

    first = screen._inject_system_map_facets(graph, in_peek=False)
    second = screen._inject_system_map_facets(graph, in_peek=False)
    facet_ids_first = sorted(node.node_id for node in first.nodes if node.node_id.startswith("facet:"))
    facet_ids_second = sorted(node.node_id for node in second.nodes if node.node_id.startswith("facet:"))

    assert facet_ids_first == facet_ids_second
    assert len(facet_ids_first) == len(set(facet_ids_first))
    assert "facet:module.a:deps" in facet_ids_first
    assert "facet:module.a:activity" in facet_ids_first
    assert "facet:module.b:deps" in facet_ids_first


def test_facet_injection_blocked_when_not_system_map_source() -> None:
    screen = _make_screen()
    screen._source = SOURCE_ATLAS
    screen._facet_settings = view_config.FacetSettings(
        density="debug",
        enabled=_facet_enabled_defaults_for_density("debug"),
        show_in_normal_view=True,
        show_in_peek_view=True,
    )
    graph = _test_graph()
    injected = screen._inject_system_map_facets(graph, in_peek=False)
    assert [node.node_id for node in injected.nodes] == [node.node_id for node in graph.nodes]


def test_facet_visibility_flags_for_normal_vs_peek() -> None:
    screen = _make_screen()
    screen._source = SOURCE_DEMO
    screen._facet_settings = view_config.FacetSettings(
        density="minimal",
        enabled=_facet_enabled_defaults_for_density("minimal"),
        show_in_normal_view=False,
        show_in_peek_view=True,
    )
    graph = _test_graph()
    normal = screen._inject_system_map_facets(graph, in_peek=False)
    peek = screen._inject_system_map_facets(graph, in_peek=True)

    assert not any(node.node_id.startswith("facet:") for node in normal.nodes)
    assert any(node.node_id.startswith("facet:") for node in peek.nodes)
