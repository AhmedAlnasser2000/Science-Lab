from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtSvg, QtWidgets

from ..badges import Badge
from app_ui import ui_scale
from ..graph_model import Node
from ..icon_pack import resolve_icon_path

NODE_WIDTH = 180.0
NODE_HEIGHT = 90.0
NODE_RADIUS = 10.0
RAIL_HEIGHT_BASE = 14
ICON_SIZE_BASE = 12
ICON_SPACING_BASE = 6
TITLE_PADDING = 8.0
DIFF_BADGE_SIZE_BASE = 12
_ICON_CACHE: Dict[Tuple[str, float], QtGui.QPixmap] = {}


class EdgeItem(QtWidgets.QGraphicsPathItem):
    def __init__(self, src: "NodeItem", dst: "NodeItem", kind: str, diff_state: Optional[str] = None) -> None:
        super().__init__()
        self.src = src
        self.dst = dst
        self.kind = kind
        self.diff_state = diff_state
        self.setZValue(-1)
        self.setPen(_edge_pen(kind, diff_state))
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
        on_inspect: Optional[Callable[[Node, Optional[Badge]], None]] = None,
        icon_style: str = "color",
        node_theme: str = "neutral",
        show_badge_layers: Optional[Dict[str, bool]] = None,
        diff_state: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.node = node
        self.on_open_subgraph = on_open_subgraph
        self.on_layout_changed = on_layout_changed
        self.on_inspect = on_inspect
        self._icon_style = icon_style
        self._node_theme = node_theme or "neutral"
        self._show_badge_layers = show_badge_layers or {}
        self._diff_state = diff_state
        self._edges: List[EdgeItem] = []
        self._last_badge_key: Optional[str] = None
        self._highlight_strength = 0.0
        self._highlight_color = QtGui.QColor("#4c6ef5")
        self._tint_strength = 0.0
        self._tint_color = QtGui.QColor("#4c6ef5")

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

    def set_icon_style(self, style: str) -> None:
        self._icon_style = style
        self.update()

    def set_node_theme(self, theme: str) -> None:
        self._node_theme = theme or "neutral"
        self.update()

    def set_badge_layers(self, layers: Dict[str, bool]) -> None:
        self._show_badge_layers = layers or {}
        self.update()

    def set_diff_state(self, diff_state: Optional[str]) -> None:
        self._diff_state = diff_state
        self.update()

    def flash(self, color: Optional[QtGui.QColor], *, reduced_motion: bool) -> None:
        self.set_highlight(1.0, color)

    def pulse(
        self,
        color: Optional[QtGui.QColor],
        *,
        duration_ms: int = 800,
        reduced_motion: bool,
    ) -> None:
        self.set_highlight(1.0, color)

    def arrival_pulse(
        self,
        color: Optional[QtGui.QColor],
        *,
        linger_ms: int,
        fade_ms: int,
        reduced_motion: bool,
    ) -> None:
        self.set_highlight(1.0, color)

    def set_highlight(self, strength: float, color: Optional[QtGui.QColor] = None) -> None:
        if color is not None:
            self._highlight_color = color
        self._highlight_strength = max(0.0, min(1.0, float(strength)))
        self.update()

    def set_tint(self, strength: float, color: Optional[QtGui.QColor] = None) -> None:
        if color is not None:
            self._tint_color = color
        self._tint_strength = max(0.0, min(1.0, float(strength)))
        self.update()

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        rect = self.boundingRect()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QtGui.QColor("#f7f7f7"))
        painter.setPen(QtGui.QPen(_severity_color(self.node.effective_severity()), 2.0))
        painter.drawRoundedRect(rect, NODE_RADIUS, NODE_RADIUS)

        if self._tint_strength > 0.0:
            tint = QtGui.QColor(self._tint_color)
            tint.setAlphaF(min(0.25, 0.08 + (self._tint_strength * 0.2)))
            painter.setBrush(tint)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            inset = 2.0
            painter.drawRoundedRect(
                rect.adjusted(inset, inset, -inset, -inset),
                NODE_RADIUS - 2.0,
                NODE_RADIUS - 2.0,
            )

        _paint_theme_marker(painter, rect, self.node.node_type, self._icon_style, self._node_theme)

        rail_color = QtGui.QColor("#e9e9e9")
        rail_height = _rail_height()
        top_rail = QtCore.QRectF(
            rect.left() + 1.0,
            rect.top() + 1.0,
            rect.width() - 2.0,
            rail_height,
        )
        bottom_rail = QtCore.QRectF(
            rect.left() + 1.0,
            rect.bottom() - rail_height - 1.0,
            rect.width() - 2.0,
            rail_height,
        )
        painter.fillRect(top_rail, rail_color)
        painter.fillRect(bottom_rail, rail_color)

        title_rect = QtCore.QRectF(
            rect.left() + TITLE_PADDING,
            top_rail.bottom() + 6.0,
            rect.width() - 2 * TITLE_PADDING,
            rect.height() - (2 * rail_height) - 12.0,
        )
        painter.setPen(QtGui.QPen(QtGui.QColor("#222"), 1.0))
        painter.setFont(QtGui.QFont("Segoe UI", 9))
        painter.drawText(title_rect, QtCore.Qt.AlignmentFlag.AlignCenter, self.node.title)

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        for badge_rect, badge in self._badge_rects():
            pixmap = _icon_pixmap(badge.key, self._icon_style, _icon_size())
            if pixmap is None:
                _paint_fallback_badge(painter, badge_rect, badge, self._icon_style)
            else:
                painter.drawPixmap(badge_rect.toRect(), pixmap)

        if self.isSelected():
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor("#888"), 1.0, QtCore.Qt.PenStyle.DashLine))
            painter.drawRoundedRect(rect.adjusted(2.0, 2.0, -2.0, -2.0), NODE_RADIUS - 2.0, NODE_RADIUS - 2.0)

        if self._diff_state:
            _paint_diff_badge(painter, rect, self._diff_state)

        if self._highlight_strength > 0.0:
            color = QtGui.QColor(self._highlight_color)
            color.setAlphaF(min(1.0, self._highlight_strength))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(color, 3.0))
            painter.drawRoundedRect(rect.adjusted(1.0, 1.0, -1.0, -1.0), NODE_RADIUS, NODE_RADIUS)

    def hoverMoveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        badge = self._badge_at(event.pos())
        key = badge.key if badge else None
        if key != self._last_badge_key:
            if key:
                summary = badge.summary if badge else ""
                tooltip = f"{self.node.title} | {key}"
                if summary:
                    tooltip = f"{tooltip}: {summary}"
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
        menu = QtWidgets.QMenu()
        inspect_action = menu.addAction("Inspect")
        open_action = None
        if self.node.subgraph_id and self.on_open_subgraph:
            open_action = menu.addAction("Open Subgraph")
        selected = menu.exec(_screen_point(event))
        if selected == inspect_action and self.on_inspect:
            self.on_inspect(self.node, None)
            event.accept()
            return
        if selected == open_action and self.node.subgraph_id and self.on_open_subgraph:
            self.on_open_subgraph(self.node.subgraph_id)
            event.accept()
            return
        super().contextMenuEvent(event)

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self.on_inspect:
            badge = self._badge_at(event.pos())
            if badge:
                self.on_inspect(self.node, badge)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self.on_layout_changed:
            self.on_layout_changed()

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self._edges:
                edge.update_path()
        return super().itemChange(change, value)

    def _badge_rects(self) -> List[Tuple[QtCore.QRectF, Badge]]:
        rects: List[Tuple[QtCore.QRectF, Badge]] = []
        rects.extend(
            self._rail_badges(
                [badge for badge in self.node.badges_for_rail("top") if self._badge_visible(badge)],
                y_offset=_rail_y_offset(top=True),
            )
        )
        rects.extend(
            self._rail_badges(
                [badge for badge in self.node.badges_for_rail("bottom") if self._badge_visible(badge)],
                y_offset=_rail_y_offset(top=False),
            )
        )
        return rects

    def _rail_badges(self, badges: List[Badge], *, y_offset: float) -> List[Tuple[QtCore.QRectF, Badge]]:
        rects: List[Tuple[QtCore.QRectF, Badge]] = []
        if not badges:
            return rects
        x = 10.0
        for badge in badges:
            size = _icon_size()
            badge_rect = QtCore.QRectF(x, y_offset, size, size)
            rects.append((badge_rect, badge))
            x += size + _icon_spacing()
        return rects

    def _badge_at(self, pos: QtCore.QPointF) -> Optional[Badge]:
        for rect, badge in self._badge_rects():
            if rect.contains(pos):
                return badge
        return None

    def _badge_visible(self, badge: Badge) -> bool:
        layer = _badge_layer(badge.key)
        if not layer:
            return True
        return self._show_badge_layers.get(layer, True)


class SignalDotItem(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, *, radius: float, color: Optional[QtGui.QColor], alpha: float) -> None:
        radius = max(3.0, float(radius))
        super().__init__(-radius, -radius, radius * 2.0, radius * 2.0)
        tint = QtGui.QColor(color) if isinstance(color, QtGui.QColor) else QtGui.QColor("#4c6ef5")
        tint.setAlphaF(max(0.2, min(1.0, float(alpha))))
        self.setBrush(tint)
        outline = QtGui.QColor("#111")
        outline.setAlphaF(0.35)
        self.setPen(QtGui.QPen(outline, 1.0))
        self.setZValue(2.0)


def _severity_color(state: str) -> QtGui.QColor:
    if state in ("probe.fail", "correctness", "failure"):
        return QtGui.QColor("#7b3fb3")
    if state == "error":
        return QtGui.QColor("#c0392b")
    if state == "warn":
        return QtGui.QColor("#d68910")
    if state == "crash":
        return QtGui.QColor("#111")
    return QtGui.QColor("#444")


def _paint_theme_marker(
    painter: QtGui.QPainter,
    rect: QtCore.QRectF,
    node_type: str,
    icon_style: str,
    theme: str,
) -> None:
    if theme != "categorical":
        return
    node_type = (node_type or "").strip()
    if icon_style == "mono":
        pen_style, width = _mono_theme_style(node_type)
        pen = QtGui.QPen(QtGui.QColor("#666"), width, pen_style)
        painter.setPen(pen)
        y = rect.top() + 3.0
        painter.drawLine(
            QtCore.QPointF(rect.left() + 6.0, y),
            QtCore.QPointF(rect.right() - 6.0, y),
        )
        return
    color = _theme_color(node_type)
    color.setAlphaF(0.35)
    stripe = QtCore.QRectF(rect.left() + 2.0, rect.top() + 2.0, rect.width() - 4.0, 4.0)
    painter.fillRect(stripe, color)


def _theme_color(node_type: str) -> QtGui.QColor:
    return QtGui.QColor(
        {
            "Workspace": "#6c757d",
            "Pack": "#2b8a3e",
            "Block": "#1971c2",
            "Lab": "#e8590c",
            "Topic": "#845ef7",
            "Unit": "#7048e8",
            "Lesson": "#5f3dc4",
            "Activity": "#4c6ef5",
            "System": "#2f9e44",
        }.get(node_type or "", "#6c757d")
    )


def _mono_theme_style(node_type: str) -> tuple[QtCore.Qt.PenStyle, float]:
    styles = {
        "Workspace": QtCore.Qt.PenStyle.SolidLine,
        "Pack": QtCore.Qt.PenStyle.DashLine,
        "Block": QtCore.Qt.PenStyle.DotLine,
        "Lab": QtCore.Qt.PenStyle.DashDotLine,
        "Topic": QtCore.Qt.PenStyle.SolidLine,
        "Unit": QtCore.Qt.PenStyle.DashLine,
        "Lesson": QtCore.Qt.PenStyle.DotLine,
        "Activity": QtCore.Qt.PenStyle.DashDotLine,
        "System": QtCore.Qt.PenStyle.SolidLine,
    }
    style = styles.get(node_type or "", QtCore.Qt.PenStyle.SolidLine)
    width = 2.0 if node_type in ("Lab", "Block") else 1.5
    return style, width


def _edge_pen(kind: str, diff_state: Optional[str]) -> QtGui.QPen:
    color = QtGui.QColor("#888")
    if kind == "pubsub":
        color = QtGui.QColor("#4c6ef5")
    elif kind == "request":
        color = QtGui.QColor("#009688")
    if diff_state == "added":
        color = QtGui.QColor("#3a7d5d")
    pen = QtGui.QPen(color, 1.4)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    if diff_state == "added":
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
    return pen


def _screen_point(event) -> QtCore.QPoint:
    pos = event.screenPos()
    if hasattr(pos, "toPoint"):
        return pos.toPoint()
    return pos


def _rail_y_offset(*, top: bool) -> float:
    rail_height = _rail_height()
    if top:
        rail_top = 1.0
    else:
        rail_top = NODE_HEIGHT - rail_height - 1.0
    return rail_top + (rail_height - _icon_size()) / 2.0


def _icon_pixmap(key: str, style: str, size: float) -> Optional[QtGui.QPixmap]:
    path = resolve_icon_path(key, style)
    if not path:
        return None
    cache_key = (str(path), size)
    cached = _ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    renderer = QtSvg.QSvgRenderer(str(path))
    side = max(1, int(size))
    pixmap = QtGui.QPixmap(side, side)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    _ICON_CACHE[cache_key] = pixmap
    return pixmap


def _badge_layer(key: str) -> Optional[str]:
    if key.startswith("state."):
        if key in ("state.crash", "state.error", "state.warn"):
            return "health"
        if key == "state.blocked":
            return "policy"
    if key in ("probe.fail", "probe.pass", "expect.value", "expect.mismatch", "expect.pass"):
        return "correctness"
    if key == "conn.offline":
        return "connectivity"
    if key == "perf.slow":
        return "perf"
    if key in ("activity.muted", "activity.active", "activity.stuck"):
        return "activity"
    return None


def _paint_diff_badge(painter: QtGui.QPainter, rect: QtCore.QRectF, state: str) -> None:
    color = QtGui.QColor("#3a7d5d") if state == "added" else QtGui.QColor("#b07d21")
    symbol = "+" if state == "added" else "I"
    size = _diff_badge_size()
    badge_rect = QtCore.QRectF(
        rect.right() - size - 4.0,
        rect.top() + 4.0,
        size,
        size,
    )
    painter.setBrush(color)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.drawEllipse(badge_rect)
    painter.setPen(QtGui.QPen(QtGui.QColor("#fff"), 1.0))
    painter.setFont(QtGui.QFont("Segoe UI", 8, QtGui.QFont.Weight.Bold))
    painter.drawText(badge_rect, QtCore.Qt.AlignmentFlag.AlignCenter, symbol)


def _icon_size() -> float:
    return float(ui_scale.scale_px(ICON_SIZE_BASE))


def _icon_spacing() -> float:
    return float(ui_scale.scale_px(ICON_SPACING_BASE))


def _rail_height() -> float:
    height = ui_scale.scale_px(RAIL_HEIGHT_BASE)
    return float(max(height, _icon_size() + 2))


def _diff_badge_size() -> float:
    return float(ui_scale.scale_px(DIFF_BADGE_SIZE_BASE))


def clear_icon_cache() -> None:
    _ICON_CACHE.clear()


def _paint_fallback_badge(
    painter: QtGui.QPainter,
    rect: QtCore.QRectF,
    badge: Badge,
    icon_style: str,
) -> None:
    color = _fallback_badge_color(badge)
    painter.setBrush(color)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.drawEllipse(rect)
    if badge.key == "activity.stuck":
        pen_color = QtGui.QColor("#111") if icon_style == "mono" else QtGui.QColor("#fff")
        painter.setPen(QtGui.QPen(pen_color, 1.2))
        left = rect.left() + rect.width() * 0.32
        right = rect.left() + rect.width() * 0.62
        top = rect.top() + rect.height() * 0.25
        bottom = rect.bottom() - rect.height() * 0.25
        painter.drawLine(QtCore.QPointF(left, top), QtCore.QPointF(left, bottom))
        painter.drawLine(QtCore.QPointF(right, top), QtCore.QPointF(right, bottom))


def _fallback_badge_color(badge: Badge) -> QtGui.QColor:
    if badge.key == "activity.active":
        return QtGui.QColor("#4c6ef5")
    if badge.key == "activity.stuck":
        return QtGui.QColor("#d68910")
    severity = badge.severity or ""
    if severity == "crash":
        return QtGui.QColor("#111")
    if severity == "error":
        return QtGui.QColor("#c0392b")
    if severity in ("failure", "probe.fail"):
        return QtGui.QColor("#7b3fb3")
    if severity == "warn":
        return QtGui.QColor("#d68910")
    return QtGui.QColor("#666")
