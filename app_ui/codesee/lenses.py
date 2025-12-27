from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

from .graph_model import Edge, Node

LensPredicate = Callable[[Node], bool]
EdgePredicate = Callable[[Edge, Node, Node], bool]


@dataclass(frozen=True)
class LensSpec:
    lens_id: str
    title: str
    node_predicate: LensPredicate
    edge_predicate: EdgePredicate


LENS_ATLAS = "atlas"
LENS_PLATFORM = "platform"
LENS_CONTENT = "content"
LENS_BUS = "bus"


def get_lenses() -> Dict[str, LensSpec]:
    return {
        LENS_ATLAS: LensSpec(LENS_ATLAS, "Atlas", _all_nodes, _all_edges),
        LENS_PLATFORM: LensSpec(LENS_PLATFORM, "Platform", _platform_nodes, _all_edges),
        LENS_CONTENT: LensSpec(LENS_CONTENT, "Content", _content_nodes, _all_edges),
        LENS_BUS: LensSpec(LENS_BUS, "Bus", _bus_nodes, _all_edges),
    }


def get_lens(lens_id: str) -> LensSpec:
    return get_lenses().get(lens_id, get_lenses()[LENS_ATLAS])


def _all_nodes(node: Node) -> bool:
    return True


def _all_edges(edge: Edge, src: Node, dst: Node) -> bool:
    return True


def _platform_nodes(node: Node) -> bool:
    node_type = (node.node_type or "").strip()
    return node_type in ("System", "Workspace")


def _content_nodes(node: Node) -> bool:
    node_type = (node.node_type or "").strip()
    return node_type in ("Workspace", "Topic", "Unit", "Lesson", "Activity")


def _bus_nodes(node: Node) -> bool:
    node_type = (node.node_type or "").strip()
    if node_type == "Workspace":
        return True
    if node_type != "System":
        return False
    token = f"{node.node_id} {node.title}".lower()
    return "bus" in token
