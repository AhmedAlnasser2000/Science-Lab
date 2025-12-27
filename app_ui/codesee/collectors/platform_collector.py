from __future__ import annotations

from ..badges import badges_from_keys
from ..graph_model import Edge, Node
from .base import CollectorContext, CollectorResult


def collect_platform(ctx: CollectorContext) -> CollectorResult:
    nodes = [
        Node("system:app_ui", "app_ui", "System", badges=badges_from_keys(bottom=["ui"])),
        Node("system:runtime_bus", "runtime_bus", "System", badges=badges_from_keys(bottom=["bus"])),
        Node("system:content_system", "content_system", "System", badges=badges_from_keys(bottom=["content"])),
        Node("system:component_runtime", "component_runtime", "System", badges=badges_from_keys(bottom=["blocks"])),
        Node("system:ui_system", "ui_system", "System", badges=badges_from_keys(bottom=["themes"])),
    ]
    edges = [
        Edge("edge:app_ui:bus", "system:app_ui", "system:runtime_bus", "depends"),
        Edge("edge:app_ui:content", "system:app_ui", "system:content_system", "depends"),
        Edge("edge:app_ui:components", "system:app_ui", "system:component_runtime", "depends"),
        Edge("edge:app_ui:ui", "system:app_ui", "system:ui_system", "depends"),
    ]

    if _core_center_available():
        nodes.append(
            Node("system:core_center", "core_center", "System", badges=badges_from_keys(bottom=["optional"]))
        )
        edges.append(Edge("edge:core:bus", "system:core_center", "system:runtime_bus", "depends"))

    return CollectorResult(nodes=nodes, edges=edges, subgraphs={})


def _core_center_available() -> bool:
    try:
        import core_center  # noqa: F401

        return True
    except Exception:
        return False
