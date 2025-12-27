from __future__ import annotations

from typing import Dict

from .graph_model import ArchitectureGraph, Edge, Node


def build_demo_root_graph() -> ArchitectureGraph:
    nodes = [
        Node(
            node_id="module.ui",
            title="App UI",
            node_type="module",
            badges_top=["nav.stack", "profile.explorer"],
            badges_bottom=["qstacked", "screens"],
            subgraph_id="module.ui",
        ),
        Node(
            node_id="module.runtime_bus",
            title="Runtime Bus",
            node_type="module",
            badges_top=["pubsub", "request.reply"],
            badges_bottom=["in.process"],
            subgraph_id="module.runtime_bus",
        ),
        Node(
            node_id="module.core_center",
            title="Management Core",
            node_type="module",
            severity_state="correctness",
            badges_top=["jobs", "inventory"],
            badges_bottom=["policy"],
            subgraph_id="module.core_center",
        ),
        Node(
            node_id="module.component_runtime",
            title="Component Runtime",
            node_type="module",
            severity_state="error",
            badges_top=["blocks", "packs"],
            badges_bottom=["host"],
            subgraph_id="module.component_runtime",
        ),
        Node(
            node_id="module.content_system",
            title="Content System",
            node_type="module",
            badges_top=["topics", "assets"],
            badges_bottom=["status.ready"],
            subgraph_id="module.content_system",
        ),
        Node(
            node_id="module.ui_system",
            title="UI System",
            node_type="module",
            badges_top=["qss", "packs"],
            badges_bottom=["themes"],
            subgraph_id="module.ui_system",
        ),
        Node(
            node_id="module.kernel",
            title="Kernel",
            node_type="module",
            severity_state="crash",
            badges_top=["dll"],
            badges_bottom=["gravity"],
            subgraph_id="module.kernel",
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
            Node("ui.main", "Main Window", "component", badges_top=["qstacked"], badges_bottom=["routing"]),
            Node("ui.menu", "Main Menu", "component", badges_top=["profile"], badges_bottom=["buttons"]),
            Node("ui.block", "Block Host", "component", badges_top=["session"], badges_bottom=["persistence"]),
            Node("ui.catalog", "Block Catalog", "component", badges_top=["packs"], badges_bottom=["details"]),
            Node("ui.sandbox", "Block Sandbox", "component", badges_top=["templates"], badges_bottom=["start"]),
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
            Node("bus.core", "RuntimeBus", "component", badges_top=["pubsub"], badges_bottom=["sticky"]),
            Node("bus.topics", "Topics", "component", badges_top=["constants"], badges_bottom=["ids"]),
            Node("bus.messages", "Message Envelope", "component", badges_top=["schema"], badges_bottom=["payloads"]),
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
            Node("core.jobs", "Job Manager", "component", badges_top=["jobs"], badges_bottom=["threads"]),
            Node("core.inventory", "Inventory", "component", badges_top=["packs"], badges_bottom=["modules"]),
            Node("core.storage", "Storage Manager", "component", badges_top=["runs"], badges_bottom=["retention"]),
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
            Node("comp.registry", "Component Registry", "component", badges_top=["blocks"], badges_bottom=["factories"]),
            Node("comp.host", "Component Host", "component", badges_top=["mount"], badges_bottom=["errors"]),
            Node("comp.packs", "Pack Loader", "component", badges_top=["repo"], badges_bottom=["store"]),
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
            Node("content.loader", "Content Loader", "component", badges_top=["status"], badges_bottom=["assets"]),
            Node("content.repo", "Content Repo", "component", badges_top=["source"], badges_bottom=["physics_v1"]),
            Node("content.store", "Content Store", "component", badges_top=["installed"], badges_bottom=["ready"]),
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
            Node("ui.pack", "Pack Manager", "component", badges_top=["qss"], badges_bottom=["themes"]),
            Node("ui.repo", "UI Repo", "component", badges_top=["source"], badges_bottom=["packs"]),
            Node("ui.store", "UI Store", "component", badges_top=["installed"], badges_bottom=["packs"]),
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
            Node("kernel.dll", "physicslab_kernel.dll", "component", badges_top=["ffi"], badges_bottom=["gravity"]),
        ],
        edges=[],
    )

    return subgraphs
