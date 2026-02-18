from PyQt6 import QtWidgets

from app_ui.codesee import view_config
from app_ui.codesee.graph_model import ArchitectureGraph, Edge, Node
from app_ui.codesee.item_ref import ItemRef
from app_ui.codesee.screen import (
    FACET_KEYS_ACTIVITY,
    FACET_KEYS_RELATIONS,
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


def _container_graph() -> ArchitectureGraph:
    return ArchitectureGraph(
        graph_id="root",
        title="Root",
        nodes=[
            Node("module.core_central", "Core Central", "module"),
            Node("module.core_center", "Management Core", "module"),
            Node("module.runtime_bus", "Communication Core", "module"),
        ],
        edges=[
            Edge("contains.core.center", "module.core_central", "module.core_center", "contains"),
            Edge("contains.core.bus", "module.core_central", "module.runtime_bus", "contains"),
        ],
    )


def _make_screen() -> CodeSeeScreen:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    screen = CodeSeeScreen(
        on_back=lambda: None,
        workspace_info_provider=lambda: {"id": "default"},
        allow_detach=False,
    )
    screen.scene = type("SceneStub", (), {"selectedItems": lambda self: []})()
    return screen


def _set_facet_settings(
    screen: CodeSeeScreen,
    *,
    density: str,
    facet_scope: str,
    show_in_normal_view: bool = True,
    show_in_peek_view: bool = True,
) -> None:
    screen._facet_settings = view_config.FacetSettings(
        density=density,
        enabled=_facet_enabled_defaults_for_density(density),
        facet_scope=facet_scope,
        show_in_normal_view=show_in_normal_view,
        show_in_peek_view=show_in_peek_view,
    )


def _facet_ids(graph: ArchitectureGraph) -> set[str]:
    return {node.node_id for node in graph.nodes if node.node_id.startswith("facet:")}


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


def test_selected_scope_injects_for_selected_owner_only() -> None:
    screen = _make_screen()
    screen._source = SOURCE_DEMO
    _set_facet_settings(screen, density="minimal", facet_scope="selected")
    screen.selected_item = ItemRef(kind="node", id="module.a")

    injected = screen._inject_system_map_facets(_test_graph(), in_peek=False)
    facet_ids = _facet_ids(injected)

    assert "facet:module.a:deps" in facet_ids
    assert "facet:module.a:activity" in facet_ids
    assert "facet:module.b:deps" not in facet_ids
    assert "facet:workspace.x:deps" not in facet_ids


def test_peek_graph_scope_injects_for_all_visible_modules_in_peek() -> None:
    screen = _make_screen()
    screen._source = SOURCE_DEMO
    _set_facet_settings(screen, density="minimal", facet_scope="peek_graph")

    injected = screen._inject_system_map_facets(_test_graph(), in_peek=True)
    facet_ids = _facet_ids(injected)

    assert "facet:module.a:deps" in facet_ids
    assert "facet:module.b:deps" in facet_ids
    assert "facet:workspace.x:deps" not in facet_ids


def test_peek_graph_scope_falls_back_to_selected_when_not_in_peek() -> None:
    screen = _make_screen()
    screen._source = SOURCE_DEMO
    _set_facet_settings(screen, density="minimal", facet_scope="peek_graph")
    screen.selected_item = ItemRef(kind="node", id="module.b")

    injected = screen._inject_system_map_facets(_test_graph(), in_peek=False)
    facet_ids = _facet_ids(injected)

    assert "facet:module.b:deps" in facet_ids
    assert "facet:module.a:deps" not in facet_ids


def test_container_policy_suppresses_runtime_facets() -> None:
    screen = _make_screen()
    screen._source = SOURCE_DEMO
    _set_facet_settings(screen, density="debug", facet_scope="selected")
    screen.selected_item = ItemRef(kind="node", id="module.core_central")

    injected = screen._inject_system_map_facets(_container_graph(), in_peek=False)
    facet_ids = _facet_ids(injected)

    for key in FACET_KEYS_RELATIONS:
        assert f"facet:module.core_central:{key}" in facet_ids
    for key in FACET_KEYS_ACTIVITY:
        assert f"facet:module.core_central:{key}" not in facet_ids


def test_facet_edge_semantics_are_backward_compatible_with_provenance() -> None:
    screen = _make_screen()
    screen._source = SOURCE_DEMO
    _set_facet_settings(screen, density="minimal", facet_scope="selected")
    screen.selected_item = ItemRef(kind="node", id="module.a")

    injected = screen._inject_system_map_facets(_test_graph(), in_peek=False)

    facet_node = next(node for node in injected.nodes if node.node_id == "facet:module.a:deps")
    assert "A" in facet_node.title
    assert "Dependencies" in facet_node.title
    meta = facet_node.metadata.get("codesee_facet", {})
    assert meta.get("base_node_id") == "module.a"
    assert meta.get("owner_label") == "A"

    facet_edge = next(edge for edge in injected.edges if edge.edge_id == "facet-edge:module.a:deps")
    assert facet_edge.kind == "facet"
    assert facet_edge.metadata.get("relation") == "facet_of"


def test_facet_injection_blocked_when_not_system_map_source() -> None:
    screen = _make_screen()
    screen._source = SOURCE_ATLAS
    _set_facet_settings(screen, density="debug", facet_scope="selected")
    screen.selected_item = ItemRef(kind="node", id="module.a")

    graph = _test_graph()
    injected = screen._inject_system_map_facets(graph, in_peek=False)
    assert [node.node_id for node in injected.nodes] == [node.node_id for node in graph.nodes]


def test_facet_visibility_flags_for_normal_vs_peek() -> None:
    screen = _make_screen()
    screen._source = SOURCE_DEMO
    _set_facet_settings(
        screen,
        density="minimal",
        facet_scope="peek_graph",
        show_in_normal_view=False,
        show_in_peek_view=True,
    )

    normal = screen._inject_system_map_facets(_test_graph(), in_peek=False)
    peek = screen._inject_system_map_facets(_test_graph(), in_peek=True)

    assert not _facet_ids(normal)
    assert _facet_ids(peek)


def test_scope_toggle_keeps_facet_ids_deterministic_without_duplicates() -> None:
    screen = _make_screen()
    screen._source = SOURCE_DEMO
    screen.selected_item = ItemRef(kind="node", id="module.a")
    graph = _test_graph()

    _set_facet_settings(screen, density="minimal", facet_scope="selected")
    selected_graph = screen._inject_system_map_facets(graph, in_peek=False)
    selected_ids = _facet_ids(selected_graph)

    _set_facet_settings(screen, density="minimal", facet_scope="peek_graph")
    peek_graph = screen._inject_system_map_facets(graph, in_peek=True)
    peek_ids = _facet_ids(peek_graph)

    assert len(selected_ids) == len(set(selected_ids))
    assert len(peek_ids) == len(set(peek_ids))
    assert "facet:module.a:deps" in selected_ids
    assert "facet:module.a:deps" in peek_ids
    assert "facet:module.b:deps" in peek_ids
