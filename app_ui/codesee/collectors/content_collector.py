from __future__ import annotations

from typing import Dict, List

from ..graph_model import ArchitectureGraph, Edge, Node
from .base import CollectorContext, CollectorResult


def collect_content(ctx: CollectorContext) -> CollectorResult:
    tree = _load_tree(ctx)
    module = tree.get("module") if isinstance(tree, dict) else None
    if not isinstance(module, dict):
        return CollectorResult()

    module_id = str(module.get("module_id") or "content")
    topic_id = f"topic:{module_id}"
    topic_title = module.get("title") or module_id
    topic_node = Node(
        node_id=topic_id,
        title=str(topic_title),
        node_type="Topic",
        badges_top=["content"],
        badges_bottom=["topic"],
        subgraph_id=topic_id,
    )

    subgraph_nodes: List[Node] = [topic_node]
    subgraph_edges: List[Edge] = []

    for section in module.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_id") or "unit")
        unit_id = f"unit:{section_id}"
        unit_title = section.get("title") or section_id
        unit_node = Node(
            node_id=unit_id,
            title=str(unit_title),
            node_type="Unit",
            badges_bottom=["unit"],
        )
        subgraph_nodes.append(unit_node)
        subgraph_edges.append(Edge(f"edge:{topic_id}:{unit_id}", topic_id, unit_id, "contains"))

        for package in section.get("packages", []) or []:
            if not isinstance(package, dict):
                continue
            package_id = str(package.get("package_id") or "lesson")
            lesson_id = f"lesson:{package_id}"
            lesson_title = package.get("title") or package_id
            lesson_node = Node(
                node_id=lesson_id,
                title=str(lesson_title),
                node_type="Lesson",
                badges_bottom=["lesson"],
            )
            subgraph_nodes.append(lesson_node)
            subgraph_edges.append(Edge(f"edge:{unit_id}:{lesson_id}", unit_id, lesson_id, "contains"))

            for part in package.get("parts", []) or []:
                if not isinstance(part, dict):
                    continue
                part_id = str(part.get("part_id") or "activity")
                activity_id = f"activity:{part_id}"
                activity_title = part.get("title") or part_id
                activity_node = Node(
                    node_id=activity_id,
                    title=str(activity_title),
                    node_type="Activity",
                    badges_bottom=["activity"],
                )
                subgraph_nodes.append(activity_node)
                subgraph_edges.append(
                    Edge(f"edge:{lesson_id}:{activity_id}", lesson_id, activity_id, "contains")
                )

    subgraph = ArchitectureGraph(
        graph_id=topic_id,
        title=str(topic_title),
        nodes=subgraph_nodes,
        edges=subgraph_edges,
    )

    return CollectorResult(nodes=[topic_node], edges=[], subgraphs={topic_id: subgraph})


def _load_tree(ctx: CollectorContext) -> Dict:
    adapter = ctx.content_adapter
    if adapter and hasattr(adapter, "list_tree"):
        try:
            return adapter.list_tree()
        except Exception:
            return {}
    try:
        import content_system

        return content_system.list_tree()
    except Exception:
        return {}
