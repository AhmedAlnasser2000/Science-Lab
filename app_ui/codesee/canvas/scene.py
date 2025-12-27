from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from ..diff import DiffResult, edge_key
from ..graph_model import ArchitectureGraph
from .items import EdgeItem, NodeItem, NODE_HEIGHT, NODE_WIDTH


class GraphScene(QtWidgets.QGraphicsScene):
    def __init__(
        self,
        *,
        on_open_subgraph: Optional[Callable[[str], None]] = None,
        on_layout_changed: Optional[Callable[[], None]] = None,
        on_inspect: Optional[Callable] = None,
        icon_style: str = "color",
    ) -> None:
        super().__init__()
        self.on_open_subgraph = on_open_subgraph
        self.on_layout_changed = on_layout_changed
        self.on_inspect = on_inspect
        self._icon_style = icon_style
        self._badge_layers: Dict[str, bool] = {}
        self._empty_message: Optional[str] = None
        self._empty_item: Optional[QtWidgets.QGraphicsTextItem] = None
        self._nodes: Dict[str, NodeItem] = {}
        self._edges: list[EdgeItem] = []
        self.setSceneRect(-5000.0, -5000.0, 10000.0, 10000.0)

    def build_graph(
        self,
        graph: ArchitectureGraph,
        positions: Dict[str, Tuple[float, float]],
        diff_result: Optional[DiffResult] = None,
    ) -> None:
        self.clear()
        self._nodes = {}
        self._edges = []
        self._empty_item = None

        if not graph.nodes and self._empty_message:
            self._empty_item = QtWidgets.QGraphicsTextItem(self._empty_message)
            self._empty_item.setDefaultTextColor(QtGui.QColor("#666"))
            self._empty_item.setFont(QtGui.QFont("Segoe UI", 10))
            self._empty_item.setPos(-220.0, -20.0)
            self.addItem(self._empty_item)
            return

        for idx, node in enumerate(graph.nodes):
            diff_state = _node_diff_state(node.node_id, diff_result)
            item = NodeItem(
                node,
                on_open_subgraph=self.on_open_subgraph,
                on_layout_changed=self.on_layout_changed,
                on_inspect=self.on_inspect,
                icon_style=self._icon_style,
                show_badge_layers=self._badge_layers,
                diff_state=diff_state,
            )
            self.addItem(item)
            pos = positions.get(node.node_id)
            if pos:
                item.setPos(pos[0], pos[1])
            else:
                col = idx % 3
                row = idx // 3
                x = col * (NODE_WIDTH + 80.0)
                y = row * (NODE_HEIGHT + 60.0)
                item.setPos(x, y)
            self._nodes[node.node_id] = item

        for edge in graph.edges:
            src = self._nodes.get(edge.src_node_id)
            dst = self._nodes.get(edge.dst_node_id)
            if not src or not dst:
                continue
            diff_state = _edge_diff_state(edge, diff_result)
            edge_item = EdgeItem(src, dst, edge.kind, diff_state=diff_state)
            src.add_edge(edge_item)
            dst.add_edge(edge_item)
            edge_item.update_path()
            self.addItem(edge_item)
            self._edges.append(edge_item)

    def set_icon_style(self, style: str) -> None:
        self._icon_style = style
        for item in self._nodes.values():
            item.set_icon_style(style)
        self.update()

    def set_badge_layers(self, layers: Dict[str, bool]) -> None:
        self._badge_layers = layers or {}
        for item in self._nodes.values():
            item.set_badge_layers(self._badge_layers)
        self.update()

    def set_empty_message(self, message: Optional[str]) -> None:
        self._empty_message = message

    def node_positions(self) -> Dict[str, Tuple[float, float]]:
        positions: Dict[str, Tuple[float, float]] = {}
        for node_id, item in self._nodes.items():
            pos = item.pos()
            positions[node_id] = (pos.x(), pos.y())
        return positions


def _node_diff_state(node_id: str, diff_result: Optional[DiffResult]) -> Optional[str]:
    if not diff_result:
        return None
    if node_id in diff_result.nodes_added:
        return "added"
    if node_id in diff_result.nodes_changed:
        return "changed"
    return None


def _edge_diff_state(edge, diff_result: Optional[DiffResult]) -> Optional[str]:
    if not diff_result:
        return None
    if edge_key(edge) in diff_result.edges_added:
        return "added"
    return None
