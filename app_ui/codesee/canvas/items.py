from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from ..graph_model import Node

NODE_WIDTH = 180.0
NODE_HEIGHT = 90.0
NODE_RADIUS = 10.0
RAIL_HEIGHT = 14.0
BADGE_RADIUS = 4.0
BADGE_SPACING = 6.0
TITLE_PADDING = 8.0


class EdgeItem(QtWidgets.QGraphicsPathItem):
    def __init__(self, src: "NodeItem", dst: "NodeItem", kind: str) -> None:
        super().__init__()
        self.src = src
        self.dst = dst
        self.kind = kind
        self.setZValue(-1)
        self.setPen(_edge_pen(kind))
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def update_path(self) -> None:
        start = self.src.center_pos()
        end = self.dst.center_pos()
        path = QtGui.QPainterPath(start)
        mid_x = (start.x() + end.x()) / 2.0
        path.cubicTo(
            QtCore.QPointF(mid_x, start.y()),
            QtCore.QPointF(mid_x, end.y()),
            end,
        )
        self.setPath(path)


class NodeItem(QtWidgets.QGraphicsItem):
    def __init__(
        self,
        node: Node,
        *,
        on_open_subgraph: Optional[Callable[[str], None]] = None,
        on_layout_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self.node = node
        self.on_open_subgraph = on_open_subgraph
        self.on_layout_changed = on_layout_changed
        self._edges: List[EdgeItem] = []
        self._last_badge_key: Optional[str] = None

        self.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(0.0, 0.0, NODE_WIDTH, NODE_HEIGHT)

    def center_pos(self) -> QtCore.QPointF:
        return self.scenePos() + QtCore.QPointF(NODE_WIDTH / 2.0, NODE_HEIGHT / 2.0)

    def add_edge(self, edge: EdgeItem) -> None:
        self._edges.append(edge)

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        rect = self.boundingRect()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QtGui.QColor("#f7f7f7"))
        painter.setPen(QtGui.QPen(_severity_color(self.node.severity_state), 2.0))
        painter.drawRoundedRect(rect, NODE_RADIUS, NODE_RADIUS)

        rail_color = QtGui.QColor("#e9e9e9")
        top_rail = QtCore.QRectF(
            rect.left() + 1.0,
            rect.top() + 1.0,
            rect.width() - 2.0,
            RAIL_HEIGHT,
        )
        bottom_rail = QtCore.QRectF(
            rect.left() + 1.0,
            rect.bottom() - RAIL_HEIGHT - 1.0,
            rect.width() - 2.0,
            RAIL_HEIGHT,
        )
        painter.fillRect(top_rail, rail_color)
        painter.fillRect(bottom_rail, rail_color)

        title_rect = QtCore.QRectF(
            rect.left() + TITLE_PADDING,
            top_rail.bottom() + 6.0,
            rect.width() - 2 * TITLE_PADDING,
            rect.height() - (2 * RAIL_HEIGHT) - 12.0,
        )
        painter.setPen(QtGui.QPen(QtGui.QColor("#222"), 1.0))
        painter.setFont(QtGui.QFont("Segoe UI", 9))
        painter.drawText(title_rect, QtCore.Qt.AlignmentFlag.AlignCenter, self.node.title)

        painter.setBrush(QtGui.QColor("#666"))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        for badge_rect, _key in self._badge_rects():
            painter.drawEllipse(badge_rect)

        if self.isSelected():
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor("#888"), 1.0, QtCore.Qt.PenStyle.DashLine))
            painter.drawRoundedRect(rect.adjusted(2.0, 2.0, -2.0, -2.0), NODE_RADIUS - 2.0, NODE_RADIUS - 2.0)

    def hoverMoveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        key = self._badge_key_at(event.pos())
        if key != self._last_badge_key:
            if key:
                tooltip = f"{self.node.title} | {key}"
                QtWidgets.QToolTip.showText(_screen_point(event), tooltip)
            else:
                QtWidgets.QToolTip.hideText()
            self._last_badge_key = key
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        QtWidgets.QToolTip.hideText()
        self._last_badge_key = None
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if self.node.subgraph_id and self.on_open_subgraph:
            self.on_open_subgraph(self.node.subgraph_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QtWidgets.QGraphicsSceneContextMenuEvent) -> None:
        if self.node.subgraph_id and self.on_open_subgraph:
            menu = QtWidgets.QMenu()
            action = menu.addAction("Open Subgraph")
            selected = menu.exec(_screen_point(event))
            if selected == action:
                self.on_open_subgraph(self.node.subgraph_id)
                event.accept()
                return
        super().contextMenuEvent(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self.on_layout_changed:
            self.on_layout_changed()

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self._edges:
                edge.update_path()
        return super().itemChange(change, value)

    def _badge_rects(self) -> List[Tuple[QtCore.QRectF, str]]:
        rects: List[Tuple[QtCore.QRectF, str]] = []
        rects.extend(self._rail_badges(self.node.badges_top, y_offset=4.0))
        rects.extend(self._rail_badges(self.node.badges_bottom, y_offset=NODE_HEIGHT - RAIL_HEIGHT + 4.0))
        return rects

    def _rail_badges(self, badges: List[str], *, y_offset: float) -> List[Tuple[QtCore.QRectF, str]]:
        rects: List[Tuple[QtCore.QRectF, str]] = []
        if not badges:
            return rects
        x = 10.0
        for key in badges:
            badge_rect = QtCore.QRectF(x, y_offset, BADGE_RADIUS * 2.0, BADGE_RADIUS * 2.0)
            rects.append((badge_rect, key))
            x += BADGE_RADIUS * 2.0 + BADGE_SPACING
        return rects

    def _badge_key_at(self, pos: QtCore.QPointF) -> Optional[str]:
        for rect, key in self._badge_rects():
            if rect.contains(pos):
                return key
        return None


def _severity_color(state: str) -> QtGui.QColor:
    if state == "error":
        return QtGui.QColor("#c0392b")
    if state == "correctness":
        return QtGui.QColor("#7b3fb3")
    if state == "crash":
        return QtGui.QColor("#111")
    return QtGui.QColor("#444")


def _edge_pen(kind: str) -> QtGui.QPen:
    color = QtGui.QColor("#888")
    if kind == "pubsub":
        color = QtGui.QColor("#4c6ef5")
    elif kind == "request":
        color = QtGui.QColor("#009688")
    pen = QtGui.QPen(color, 1.4)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    return pen


def _screen_point(event) -> QtCore.QPoint:
    pos = event.screenPos()
    if hasattr(pos, "toPoint"):
        return pos.toPoint()
    return pos
