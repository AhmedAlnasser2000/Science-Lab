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
STATUS_BADGE_SIZE_BASE = 10
STATUS_BADGE_SPACING_BASE = 4
STATUS_BADGE_MARGIN = 6.0
STATUS_BADGE_PILL_PAD_X = 4.0
STATUS_BADGE_PILL_PAD_Y = 2.0
STATUS_BADGE_MAX = 4
RAIL_BADGE_MAX = 4
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

    def geometry_path(self) -> QtGui.QPainterPath:
        path = self.path()
        if path.isEmpty():
            self.update_path()
            path = self.path()
        return path


class NodeItem(QtWidgets.QGraphicsItem):
    def __init__(
        self,
        node: Node,
        *,
        on_open_subgraph: Optional[Callable[[str], None]] = None,
        on_layout_changed: Optional[Callable[[], None]] = None,
        on_inspect: Optional[Callable[[Node, Optional[Badge]], None]] = None,
        on_status_badges: Optional[Callable[[Node, list, QtCore.QPoint], None]] = None,
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
        self._on_status_badges = on_status_badges
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
        self._activity_alpha = 0.0
        self._activity_color = QtGui.QColor("#4c6ef5")
        self._context_active = False
        self._context_color = QtGui.QColor("#2f9e44")
        self._status_badges: List[dict] = []

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

    def set_activity(self, alpha: float, color: Optional[QtGui.QColor] = None) -> None:
        if color is not None:
            self._activity_color = color
        self._activity_alpha = max(0.0, min(1.0, float(alpha)))
        self.update()

    def set_context_active(self, active: bool, color: Optional[QtGui.QColor] = None) -> None:
        if color is not None:
            self._context_color = color
        self._context_active = bool(active)
        self.update()

    def set_status_badges(self, badges: List[dict]) -> None:
        self._status_badges = badges or []
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

        if self._context_active:
            color = QtGui.QColor(self._context_color)
            color.setAlphaF(0.9)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(color, 3.0))
            painter.drawRoundedRect(rect.adjusted(1.0, 1.0, -1.0, -1.0), NODE_RADIUS, NODE_RADIUS)

        if self._activity_alpha > 0.0:
            color = QtGui.QColor(self._activity_color)
            color.setAlphaF(min(0.8, max(0.2, self._activity_alpha)))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(color, 2.0))
            painter.drawRoundedRect(rect.adjusted(2.0, 2.0, -2.0, -2.0), NODE_RADIUS - 1.0, NODE_RADIUS - 1.0)

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
        self._paint_rail_badges(painter, top_rail, top=True)
        self._paint_rail_badges(painter, bottom_rail, top=False)

        self._paint_status_badges(painter, rect)

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
        if self._ellipsis_tooltip(event.pos()):
            QtWidgets.QToolTip.showText(_screen_point(event), "More status items — open dropdown")
            self._last_badge_key = None
            super().hoverMoveEvent(event)
            return
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

    def _ellipsis_tooltip(self, pos: QtCore.QPointF) -> bool:
        rect = self.boundingRect()
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
        for top, rail_rect in ((True, top_rail), (False, bottom_rail)):
            badges = [
                badge
                for badge in self.node.badges_for_rail("top" if top else "bottom")
                if self._badge_visible(badge)
            ]
            if not badges:
                continue
            _rects, _overflow, ellipsis = self._rail_layout(badges, rail_rect)
            if ellipsis and ellipsis.contains(pos):
                return True
        if self._status_badges:
            _rects, _overflow, ellipsis = self._status_badge_layout(rect)
            if ellipsis and ellipsis.contains(pos):
                return True
        return False

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
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._on_status_badges:
                overflow_items = self._badge_overflow_items(event.pos())
                if overflow_items:
                    self._on_status_badges(self.node, overflow_items, _screen_point(event))
                    event.accept()
                    return
            if self._on_status_badges and self._status_badges and self._status_badge_hit(event.pos()):
                self._on_status_badges(self.node, self._collect_status_menu_items(), _screen_point(event))
                event.accept()
                return
            if self.on_inspect:
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
        rects.extend(self._rail_badge_rects(top=True))
        rects.extend(self._rail_badge_rects(top=False))
        return rects

    def _rail_badge_rects(self, *, top: bool) -> List[Tuple[QtCore.QRectF, Badge]]:
        badges = [badge for badge in self.node.badges_for_rail("top" if top else "bottom") if self._badge_visible(badge)]
        if not badges:
            return []
        rect = self.boundingRect()
        rail_height = _rail_height()
        rail_rect = QtCore.QRectF(
            rect.left() + 1.0,
            rect.top() + 1.0 if top else rect.bottom() - rail_height - 1.0,
            rect.width() - 2.0,
            rail_height,
        )
        rects, _overflow, _ellipsis = self._rail_layout(badges, rail_rect)
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

    def _dedupe_status_badges(self) -> List[dict]:
        seen: Dict[str, dict] = {}
        for badge in self._status_badges:
            key = str(badge.get("key") or "")
            if not key:
                continue
            entry = seen.get(key)
            if not entry:
                seen[key] = dict(badge)
                continue
            entry["count"] = int(entry.get("count", 1)) + int(badge.get("count", 1))
        return list(seen.values())

    def _collect_status_menu_items(self) -> list[dict]:
        items: list[dict] = []

        def _merge(entry: dict) -> None:
            key = str(entry.get("key") or "")
            if not key:
                items.append(dict(entry))
                return
            for existing in items:
                if str(existing.get("key") or "") == key:
                    existing["count"] = int(existing.get("count", 1)) + int(entry.get("count", 1))
                    if not existing.get("detail") and entry.get("detail"):
                        existing["detail"] = entry.get("detail")
                    last_seen = entry.get("last_seen")
                    if isinstance(last_seen, (int, float)):
                        current = existing.get("last_seen")
                        if current is None or float(last_seen) < float(current):
                            existing["last_seen"] = float(last_seen)
                    return
            items.append(dict(entry))

        rail_badges: List[Badge] = []
        for top in (True, False):
            rail_badges.extend(
                badge
                for badge in self.node.badges_for_rail("top" if top else "bottom")
                if self._badge_visible(badge)
            )
        for entry in _aggregate_badges(rail_badges):
            _merge(entry)
        for entry in self._dedupe_status_badges():
            _merge(entry)
        return items

    def _badge_overflow_items(self, pos: QtCore.QPointF) -> Optional[list[dict]]:
        rect = self.boundingRect()
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
        for top, rail_rect in ((True, top_rail), (False, bottom_rail)):
            badges = [
                badge
                for badge in self.node.badges_for_rail("top" if top else "bottom")
                if self._badge_visible(badge)
            ]
            if not badges:
                continue
            rects, overflow, ellipsis = self._rail_layout(badges, rail_rect)
            if (overflow and overflow[0].contains(pos)) or (ellipsis and ellipsis.contains(pos)):
                return self._collect_status_menu_items()
        return None

    def _paint_rail_badges(self, painter: QtGui.QPainter, rail_rect: QtCore.QRectF, *, top: bool) -> None:
        badges = [
            badge
            for badge in self.node.badges_for_rail("top" if top else "bottom")
            if self._badge_visible(badge)
        ]
        if not badges:
            return
        rects, overflow, ellipsis = self._rail_layout(badges, rail_rect)
        painter.save()
        painter.setClipRect(rail_rect)
        for badge_rect, badge in rects:
            pixmap = _icon_pixmap(badge.key, self._icon_style, _icon_size())
            if pixmap is None:
                _paint_fallback_badge(painter, badge_rect, badge, self._icon_style)
            else:
                painter.drawPixmap(badge_rect.toRect(), pixmap)
        if ellipsis:
            painter.setPen(QtGui.QPen(QtGui.QColor("#666"), 1.0))
            painter.setFont(_status_badge_font())
            painter.drawText(ellipsis, QtCore.Qt.AlignmentFlag.AlignCenter, "\u2026")
        if overflow:
            # Draw last to keep pill label intact.
            overflow_rect, label = overflow
            painter.setBrush(QtGui.QColor("#555"))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawRoundedRect(
                overflow_rect,
                overflow_rect.height() / 2.0,
                overflow_rect.height() / 2.0,
            )
            painter.setPen(QtGui.QPen(QtGui.QColor("#fff"), 1.0))
            painter.setFont(_status_badge_font())
            painter.drawText(overflow_rect, QtCore.Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def _rail_layout(
        self, badges: List[Badge], rail_rect: QtCore.QRectF
    ) -> Tuple[
        List[Tuple[QtCore.QRectF, Badge]],
        Optional[Tuple[QtCore.QRectF, str]],
        Optional[QtCore.QRectF],
    ]:
        summaries = _summarize_badges(badges)
        size = _icon_size()
        spacing = _icon_spacing()
        max_slots = max(1, RAIL_BADGE_MAX)
        total_count = sum(summary["count"] for summary in summaries)
        x_right = rail_rect.right() - STATUS_BADGE_MARGIN
        overflow_rect = None
        overflow_label = ""
        if total_count >= 5:
            overflow_label = format_overflow(total_count)
            if overflow_label:
                metrics = QtGui.QFontMetrics(_status_badge_font())
                pill_width = max(size, metrics.horizontalAdvance(overflow_label) + (2 * STATUS_BADGE_PILL_PAD_X))
                overflow_rect = QtCore.QRectF(x_right - pill_width, rail_rect.top() + (rail_rect.height() - size) / 2.0, pill_width, size)
                x_right = overflow_rect.left() - spacing
        available = max(0.0, x_right - (rail_rect.left() + STATUS_BADGE_MARGIN))
        max_fit = int(max(0.0, (available + spacing) // (size + spacing)))
        max_visible = min(max_slots, max_fit)
        visible_summaries = summaries[:max_visible]
        hidden_types = max(0, len(summaries) - len(visible_summaries))
        ellipsis_rect = None
        if hidden_types > 0:
            ellipsis_rect = QtCore.QRectF(x_right - size, rail_rect.top() + (rail_rect.height() - size) / 2.0, size, size)
            x_right = ellipsis_rect.left() - spacing
            available = max(0.0, x_right - (rail_rect.left() + STATUS_BADGE_MARGIN))
            max_fit = int(max(0.0, (available + spacing) // (size + spacing)))
            max_visible = min(max_slots, max_fit)
            visible_summaries = summaries[:max_visible]
        rects: List[Tuple[QtCore.QRectF, Badge]] = []
        x = x_right
        y = rail_rect.top() + (rail_rect.height() - size) / 2.0
        for summary in reversed(visible_summaries):
            x -= size
            rects.append((QtCore.QRectF(x, y, size, size), summary["badge"]))
            x -= spacing
        rects.reverse()
        overflow = (overflow_rect, overflow_label) if overflow_rect and overflow_label else None
        return rects, overflow, ellipsis_rect

    def _paint_status_badges(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        if not self._status_badges:
            return
        badge_rects, overflow, ellipsis = self._status_badge_layout(rect)
        if not badge_rects and not overflow and not ellipsis:
            return
        badge_strip = QtCore.QRectF(
            rect.left() + 1.0,
            rect.top() + 1.0,
            rect.width() - 2.0,
            _rail_height(),
        )
        painter.save()
        painter.setFont(_status_badge_font())
        painter.setClipRect(badge_strip)
        for badge_rect, badge in badge_rects:
            color = _status_badge_color(badge)
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawEllipse(badge_rect)
            painter.setPen(QtGui.QPen(QtGui.QColor("#fff"), 1.0))
            painter.drawText(badge_rect, QtCore.Qt.AlignmentFlag.AlignCenter, _status_badge_label(badge))
        if ellipsis:
            ellipsis_rect = ellipsis
            painter.setPen(QtGui.QPen(QtGui.QColor("#666"), 1.0))
            painter.drawText(ellipsis_rect, QtCore.Qt.AlignmentFlag.AlignCenter, "\u2026")
        if overflow:
            # Draw last so the pill label can't be overwritten by badge letters.
            overflow_rect, label = overflow
            painter.setBrush(QtGui.QColor("#555"))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawRoundedRect(
                overflow_rect,
                overflow_rect.height() / 2.0,
                overflow_rect.height() / 2.0,
            )
            painter.setPen(QtGui.QPen(QtGui.QColor("#fff"), 1.0))
            painter.drawText(overflow_rect, QtCore.Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def _status_badge_layout(
        self, rect: QtCore.QRectF
    ) -> Tuple[
        List[Tuple[QtCore.QRectF, dict]],
        Optional[Tuple[QtCore.QRectF, str]],
        Optional[QtCore.QRectF],
    ]:
        badges = self._dedupe_status_badges()
        if not badges:
            return [], None, None
        max_slots = max(1, STATUS_BADGE_MAX)
        size = _status_badge_size()
        spacing = _status_badge_spacing()
        y = rect.top() + 1.0 + (_rail_height() - size) / 2.0
        total_count = sum(int(badge.get("count", 1)) for badge in badges)
        x_left = rect.left() + STATUS_BADGE_MARGIN
        x_right = rect.right() - STATUS_BADGE_MARGIN
        overflow_rect = None
        overflow_label = ""
        pill_width = 0.0
        if total_count >= 5:
            overflow_label = format_overflow(total_count)
            if overflow_label:
                metrics = QtGui.QFontMetrics(_status_badge_font())
                pill_width = max(size, metrics.horizontalAdvance(overflow_label) + (2 * STATUS_BADGE_PILL_PAD_X))
        ellipsis_rect = None
        reserved = (pill_width + spacing) if overflow_label else 0.0
        available = max(0.0, x_right - x_left - reserved)
        max_fit = int(max(0.0, (available + spacing) // (size + spacing)))
        max_visible = min(max_slots, max_fit)
        visible = badges[:max_visible]
        hidden_types = max(0, len(badges) - len(visible))
        if hidden_types > 0:
            reserved = (size + spacing) + ((pill_width + spacing) if overflow_label else 0.0)
            available = max(0.0, x_right - x_left - reserved)
            max_fit = int(max(0.0, (available + spacing) // (size + spacing)))
            max_visible = min(max_slots, max_fit)
            visible = badges[:max_visible]
            hidden_types = max(0, len(badges) - len(visible))
        rects: List[Tuple[QtCore.QRectF, dict]] = []
        x = x_left
        for badge in visible:
            rects.append((QtCore.QRectF(x, y, size, size), badge))
            x += size + spacing
        if hidden_types > 0:
            ellipsis_rect = QtCore.QRectF(x, y, size, size)
            x += size + spacing
        if overflow_label:
            overflow_rect = QtCore.QRectF(x, y, pill_width, size)
        overflow = (overflow_rect, overflow_label) if overflow_rect and overflow_label else None
        return rects, overflow, ellipsis_rect

    def _status_badge_hit(self, pos: QtCore.QPointF) -> bool:
        if not self._status_badges:
            return False
        rects, overflow, ellipsis = self._status_badge_layout(self.boundingRect())
        for rect, _badge in rects:
            if rect.contains(pos):
                return True
        if overflow and overflow[0].contains(pos):
            return True
        if ellipsis and ellipsis.contains(pos):
            return True
        return False


class SignalDotItem(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, *, radius: float, color: Optional[QtGui.QColor], alpha: float) -> None:
        radius = max(5.0, float(radius))
        super().__init__(-radius, -radius, radius * 2.0, radius * 2.0)
        tint = QtGui.QColor(color) if isinstance(color, QtGui.QColor) else QtGui.QColor("#4c6ef5")
        tint.setAlphaF(max(0.3, min(1.0, float(alpha))))
        self.setBrush(tint)
        outline = QtGui.QColor("#111")
        outline.setAlphaF(0.45)
        self.setPen(QtGui.QPen(outline, 1.2))
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


def _status_badge_size() -> float:
    return float(ui_scale.scale_px(STATUS_BADGE_SIZE_BASE))


def _status_badge_spacing() -> float:
    return float(ui_scale.scale_px(STATUS_BADGE_SPACING_BASE))


def _status_badge_font() -> QtGui.QFont:
    return QtGui.QFont("Segoe UI", 7, QtGui.QFont.Weight.DemiBold)


def _status_badge_label(badge: dict) -> str:
    key = str(badge.get("key") or "")
    mapping = {
        "context": "C",
        "activity": "A",
        "pulse": "P",
        "signal": "S",
        "error": "!",
    }
    if key in mapping:
        return mapping[key]
    if key:
        return key[:1].upper()
    return "?"


def _status_badge_color(badge: dict) -> QtGui.QColor:
    color = badge.get("color")
    if isinstance(color, QtGui.QColor):
        return color
    if isinstance(color, str) and color:
        return QtGui.QColor(color)
    return QtGui.QColor("#666")


def format_overflow(total: int) -> str:
    total = int(total)
    if total >= 99:
        return "99+"
    if total >= 5:
        return f"{total}+"
    return ""


def _aggregate_badges(badges: List[Badge]) -> list[dict]:
    counts: Dict[str, dict] = {}
    for badge in badges:
        entry = counts.get(badge.key)
        if not entry:
            counts[badge.key] = {
                "key": badge.key,
                "label": _badge_label(badge.key),
                "count": 1,
                "color": _fallback_badge_color(badge),
                "last_seen": None,
            }
        else:
            entry["count"] = int(entry.get("count", 1)) + 1
    return list(counts.values())


def _summarize_badges(badges: List[Badge]) -> list[dict]:
    summaries: Dict[str, dict] = {}
    ordered: list[str] = []
    for badge in badges:
        key = badge.key
        entry = summaries.get(key)
        if not entry:
            summaries[key] = {"badge": badge, "count": 1}
            ordered.append(key)
        else:
            entry["count"] = int(entry.get("count", 1)) + 1
    return [summaries[key] for key in ordered]


def _badge_label(key: str) -> str:
    return {
        "state.error": "Error",
        "state.warn": "Warning",
        "state.crash": "Crash",
        "activity.muted": "Muted activity",
        "activity.active": "Activity",
        "activity.stuck": "Stuck activity",
        "probe.fail": "Probe failed",
        "probe.pass": "Probe passed",
        "expect.value": "Expectation",
        "expect.mismatch": "Expectation mismatch",
        "conn.offline": "Offline",
        "perf.slow": "Performance slow",
    }.get(key, key)


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
