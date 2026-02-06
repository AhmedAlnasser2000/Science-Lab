# =============================================================================
# NAV INDEX (search these tags)
# [NAV-00] Imports / constants
# [NAV-10] Public API
# [NAV-99] end
# =============================================================================

# === [NAV-00] Imports / constants ============================================
from __future__ import annotations

from typing import Dict

from ..badges import badges_from_keys
from ..expectations import build_check
from ..graph_model import ArchitectureGraph, Edge, Node

# === [NAV-10] Public API ======================================================


def build_demo_root_graph() -> ArchitectureGraph:
    nodes = [
        Node(
            node_id="module.ui",
            title="App UI",
            node_type="module",
            badges=badges_from_keys(top=["state.warn"]),
            subgraph_id="module.ui",
            checks=[
                build_check(
                    check_id="demo.ui.check.pass",
                    node_id="module.ui",
                    expected="UI ready",
                    actual="UI ready",
                    mode="exact",
                    message="UI status matches expected.",
                )
            ],
        ),
        Node(
            node_id="module.runtime_bus",
            title="Runtime Bus",
            node_type="module",
            badges=badges_from_keys(bottom=["probe.pass"]),
            subgraph_id="module.runtime_bus",
        ),
        Node(
            node_id="module.core_center",
            title="Management Core",
            node_type="module",
            badges=badges_from_keys(bottom=["expect.value"]),
            subgraph_id="module.core_center",
        ),
        Node(
            node_id="module.component_runtime",
            title="Component Runtime",
            node_type="module",
            badges=badges_from_keys(top=["state.error"]),
            subgraph_id="module.component_runtime",
        ),
        Node(
            node_id="module.content_system",
            title="Content System",
            node_type="module",
            badges=badges_from_keys(top=["conn.offline"]),
            subgraph_id="module.content_system",
        ),
        Node(
            node_id="module.ui_system",
            title="UI System",
            node_type="module",
            badges=badges_from_keys(top=["activity.muted"]),
            subgraph_id="module.ui_system",
        ),
        Node(
            node_id="module.kernel",
            title="Kernel",
            node_type="module",
            badges=badges_from_keys(top=["state.crash"], bottom=["probe.fail"]),
            subgraph_id="module.kernel",
            checks=[
                build_check(
                    check_id="demo.kernel.mismatch",
                    node_id="module.kernel",
                    expected={"gravity": 9.8},
                    actual={"gravity": 8.1},
                    mode="tolerance",
                    tolerance=0.1,
                    message="Gravity constant mismatch.",
                )
            ],
        ),
    ]
    edges = [
        Edge("edge.ui.bus", "module.ui", "module.runtime_bus", "request"),
        Edge("edge.ui.content", "module.ui", "module.content_system", "dependency"),
        Edge("edge.ui.components", "module.ui", "module.component_runtime", "dependency"),
        Edge("edge.ui.ui_system", "module.ui", "module.ui_system", "dependency"),
        Edge("edge.ui.kernel", "module.ui", "module.kernel", "dependency"),
        Edge("edge.core.bus", "module.core_center", "module.runtime_bus", "pubsub"),
        Edge("edge.components.bus", "module.component_runtime", "module.runtime_bus", "pubsub"),
    ]
    return ArchitectureGraph(graph_id="root", title="Root", nodes=nodes, edges=edges)


def build_demo_subgraphs() -> Dict[str, ArchitectureGraph]:
    subgraphs: Dict[str, ArchitectureGraph] = {}

    subgraphs["module.ui"] = ArchitectureGraph(
        graph_id="module.ui",
        title="App UI",
        nodes=[
            Node("ui.main", "Main Window", "component"),
            Node("ui.menu", "Main Menu", "component"),
            Node("ui.block", "Block Host", "component"),
            Node("ui.catalog", "Block Catalog", "component"),
            Node("ui.sandbox", "Block Sandbox", "component"),
        ],
        edges=[
            Edge("ui.edge.menu", "ui.main", "ui.menu", "nav"),
            Edge("ui.edge.block", "ui.main", "ui.block", "nav"),
            Edge("ui.edge.catalog", "ui.main", "ui.catalog", "nav"),
            Edge("ui.edge.sandbox", "ui.main", "ui.sandbox", "nav"),
        ],
    )

    subgraphs["module.runtime_bus"] = ArchitectureGraph(
        graph_id="module.runtime_bus",
        title="Runtime Bus",
        nodes=[
            Node("bus.core", "RuntimeBus", "component"),
            Node("bus.topics", "Topics", "component"),
            Node("bus.messages", "Message Envelope", "component"),
        ],
        edges=[
            Edge("bus.edge.topics", "bus.core", "bus.topics", "lookup"),
            Edge("bus.edge.messages", "bus.core", "bus.messages", "schema"),
        ],
    )

    subgraphs["module.core_center"] = ArchitectureGraph(
        graph_id="module.core_center",
        title="Management Core",
        nodes=[
            Node("core.jobs", "Job Manager", "component"),
            Node("core.inventory", "Inventory", "component"),
            Node("core.storage", "Storage Manager", "component"),
        ],
        edges=[
            Edge("core.edge.jobs", "core.jobs", "core.storage", "request"),
            Edge("core.edge.inventory", "core.inventory", "core.storage", "dependency"),
        ],
    )

    subgraphs["module.component_runtime"] = ArchitectureGraph(
        graph_id="module.component_runtime",
        title="Component Runtime",
        nodes=[
            Node("comp.registry", "Component Registry", "component"),
            Node("comp.host", "Component Host", "component"),
            Node("comp.packs", "Pack Loader", "component"),
        ],
        edges=[
            Edge("comp.edge.host", "comp.registry", "comp.host", "dependency"),
            Edge("comp.edge.packs", "comp.packs", "comp.registry", "load"),
        ],
    )

    subgraphs["module.content_system"] = ArchitectureGraph(
        graph_id="module.content_system",
        title="Content System",
        nodes=[
            Node("content.loader", "Content Loader", "component"),
            Node("content.repo", "Content Repo", "component"),
            Node("content.store", "Content Store", "component"),
        ],
        edges=[
            Edge("content.edge.repo", "content.repo", "content.loader", "dependency"),
            Edge("content.edge.store", "content.store", "content.loader", "dependency"),
        ],
    )

    subgraphs["module.ui_system"] = ArchitectureGraph(
        graph_id="module.ui_system",
        title="UI System",
        nodes=[
            Node("ui.pack", "Pack Manager", "component"),
            Node("ui.repo", "UI Repo", "component"),
            Node("ui.store", "UI Store", "component"),
        ],
        edges=[
            Edge("ui.edge.repo", "ui.repo", "ui.pack", "dependency"),
            Edge("ui.edge.store", "ui.store", "ui.pack", "dependency"),
        ],
    )

    subgraphs["module.kernel"] = ArchitectureGraph(
        graph_id="module.kernel",
        title="Kernel",
        nodes=[
            Node("kernel.dll", "physicslab_kernel.dll", "component"),
        ],
        edges=[],
    )

    return subgraphs


# === [NAV-99] end =============================================================
