from __future__ import annotations

import time
from typing import Callable, Dict, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from ..diff import DiffResult, edge_key
from ..graph_model import ArchitectureGraph
from .items import EdgeItem, NodeItem, SignalDotItem, NODE_HEIGHT, NODE_WIDTH


class GraphScene(QtWidgets.QGraphicsScene):
    def __init__(
        self,
        *,
        on_open_subgraph: Optional[Callable[[str], None]] = None,
        on_layout_changed: Optional[Callable[[], None]] = None,
        on_inspect: Optional[Callable] = None,
        icon_style: str = "color",
        node_theme: str = "neutral",
    ) -> None:
        super().__init__()
        self.on_open_subgraph = on_open_subgraph
        self.on_layout_changed = on_layout_changed
        self.on_inspect = on_inspect
        self._icon_style = icon_style
        self._node_theme = node_theme or "neutral"
        self._badge_layers: Dict[str, bool] = {}
        self._empty_message: Optional[str] = None
        self._empty_item: Optional[QtWidgets.QGraphicsTextItem] = None
        self._reduced_motion = False
        self._nodes: Dict[str, NodeItem] = {}
        self._edges: list[EdgeItem] = []
        self._signals: list[dict] = []
        self._pulses: Dict[str, dict] = {}
        self._signal_timer = QtCore.QTimer(self)
        self._signal_timer.setInterval(33)
        self._signal_timer.timeout.connect(self._tick_signals)
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
        self._signals = []
        self._pulses = {}
        if self._signal_timer.isActive():
            self._signal_timer.stop()

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
                node_theme=self._node_theme,
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

    def set_node_theme(self, theme: str) -> None:
        self._node_theme = theme or "neutral"
        for item in self._nodes.values():
            item.set_node_theme(self._node_theme)
        self.update()

    def set_badge_layers(self, layers: Dict[str, bool]) -> None:
        self._badge_layers = layers or {}
        for item in self._nodes.values():
            item.set_badge_layers(self._badge_layers)
        self.update()

    def set_reduced_motion(self, value: bool) -> None:
        self._reduced_motion = bool(value)

    def flash_node(self, node_id: str, color: Optional[QtGui.QColor] = None) -> None:
        if self._reduced_motion:
            self._queue_pulse(
                node_id,
                color=color,
                mode="arrival",
                linger_ms=200,
                fade_ms=300,
            )
            return
        self._queue_pulse(
            node_id,
            color=color,
            mode="flash",
            duration_ms=500,
        )

    def pulse_node(
        self,
        node_id: str,
        *,
        kind: str,
        color: Optional[QtGui.QColor] = None,
        duration_ms: int = 800,
    ) -> None:
        if self._reduced_motion:
            self._queue_pulse(
                node_id,
                color=color,
                mode="arrival",
                linger_ms=200,
                fade_ms=300,
            )
            return
        self._queue_pulse(
            node_id,
            color=color,
            mode="pulse",
            duration_ms=duration_ms,
        )

    def emit_signal(
        self,
        *,
        source_id: Optional[str],
        target_id: str,
        kind: str,
        color: Optional[QtGui.QColor],
        settings,
    ) -> None:
        target_item = self._nodes.get(target_id)
        if not target_item:
            return
        speed = _setting_value(settings, "travel_speed_px_per_s", 900)
        linger_ms = _setting_value(settings, "arrive_linger_ms", 300)
        fade_ms = _setting_value(settings, "fade_ms", 500)
        radius = _setting_value(settings, "pulse_radius_px", 8)
        alpha = _setting_value(settings, "pulse_alpha", 0.6)
        max_signals = _setting_value(settings, "max_concurrent_signals", 6)
        if self._reduced_motion:
            self._queue_pulse(
                target_id,
                color=color,
                mode="arrival",
                linger_ms=int(linger_ms),
                fade_ms=int(fade_ms),
            )
            return
        if not source_id or not self._edge_exists(source_id, target_id):
            self._queue_pulse(
                target_id,
                color=color,
                mode="arrival",
                linger_ms=int(linger_ms),
                fade_ms=int(fade_ms),
            )
            return
        if len(self._signals) >= int(max_signals):
            self._drop_oldest_signal()
        src_item = self._nodes.get(source_id)
        if not src_item:
            self._queue_pulse(
                target_id,
                color=color,
                mode="arrival",
                linger_ms=int(linger_ms),
                fade_ms=int(fade_ms),
            )
            return
        start = src_item.center_pos()
        end = target_item.center_pos()
        distance = max(1.0, _distance(start, end))
        duration = max(0.15, distance / max(1.0, float(speed)))
        dot = SignalDotItem(radius=float(radius), color=color, alpha=float(alpha))
        dot.setPos(start)
        self.addItem(dot)
        self._signals.append(
            {
                "dot": dot,
                "start": start,
                "end": end,
                "target": target_id,
                "t0": time.monotonic(),
                "duration": duration,
                "linger_ms": int(linger_ms),
                "fade_ms": int(fade_ms),
                "color": color,
            }
        )
        if not self._signal_timer.isActive():
            self._signal_timer.start()

    def set_empty_message(self, message: Optional[str]) -> None:
        self._empty_message = message

    def signals_active_count(self) -> int:
        return len(self._signals)

    def pulse_state_count(self) -> int:
        return len(self._pulses)

    def clear_pulses(self) -> None:
        if not self._pulses:
            return
        for node_id, item in list(self._nodes.items()):
            try:
                item.set_highlight(0.0, None)
            except RuntimeError:
                pass
        self._pulses = {}
        if not self._signals and self._signal_timer.isActive():
            self._signal_timer.stop()

    def node_positions(self) -> Dict[str, Tuple[float, float]]:
        positions: Dict[str, Tuple[float, float]] = {}
        for node_id, item in self._nodes.items():
            pos = item.pos()
            positions[node_id] = (pos.x(), pos.y())
        return positions

    def _tick_signals(self) -> None:
        now = time.monotonic()
        remaining = []
        for state in list(self._signals):
            dot = state.get("dot")
            if not isinstance(dot, SignalDotItem):
                continue
            t0 = float(state.get("t0", now))
            duration = float(state.get("duration", 0.2))
            progress = (now - t0) / max(duration, 0.001)
            if progress >= 1.0:
                self.removeItem(dot)
                target_id = str(state.get("target"))
                self._queue_pulse(
                    target_id,
                    color=state.get("color"),
                    mode="arrival",
                    linger_ms=int(state.get("linger_ms", 300)),
                    fade_ms=int(state.get("fade_ms", 500)),
                )
                continue
            start = state.get("start")
            end = state.get("end")
            if isinstance(start, QtCore.QPointF) and isinstance(end, QtCore.QPointF):
                pos = start + (end - start) * float(progress)
                dot.setPos(pos)
            remaining.append(state)
        self._signals = remaining
        self._tick_pulses(now)
        if not self._signals and not self._pulses:
            if self._signal_timer.isActive():
                self._signal_timer.stop()

    def _edge_exists(self, source_id: str, target_id: str) -> bool:
        for edge in self._edges:
            if edge.src.node.node_id == source_id and edge.dst.node.node_id == target_id:
                return True
            if edge.src.node.node_id == target_id and edge.dst.node.node_id == source_id:
                return True
        return False

    def _queue_pulse(
        self,
        node_id: str,
        *,
        color: Optional[QtGui.QColor],
        mode: str,
        duration_ms: int = 500,
        linger_ms: int = 0,
        fade_ms: int = 0,
    ) -> None:
        if node_id not in self._nodes:
            return
        self._pulses[node_id] = {
            "t0": time.monotonic(),
            "color": color,
            "mode": mode,
            "duration": max(0.05, float(duration_ms) / 1000.0),
            "linger": max(0.0, float(linger_ms) / 1000.0),
            "fade": max(0.0, float(fade_ms) / 1000.0),
        }
        if not self._signal_timer.isActive():
            self._signal_timer.start()

    def _tick_pulses(self, now: float) -> None:
        if not self._pulses:
            return
        to_remove = []
        for node_id, state in list(self._pulses.items()):
            item = self._nodes.get(node_id)
            if not item:
                to_remove.append(node_id)
                continue
            t0 = float(state.get("t0", now))
            elapsed = max(0.0, now - t0)
            strength, done = _pulse_strength(state, elapsed)
            try:
                item.set_highlight(strength, state.get("color"))
            except RuntimeError:
                to_remove.append(node_id)
                continue
            if done:
                to_remove.append(node_id)
        for node_id in to_remove:
            item = self._nodes.get(node_id)
            if item:
                try:
                    item.set_highlight(0.0, None)
                except RuntimeError:
                    pass
            self._pulses.pop(node_id, None)

    def _drop_oldest_signal(self) -> None:
        if not self._signals:
            return
        state = self._signals.pop(0)
        dot = state.get("dot")
        if isinstance(dot, SignalDotItem):
            self.removeItem(dot)


def _setting_value(settings, key: str, default):
    if settings is None:
        return default
    if isinstance(settings, dict):
        return settings.get(key, default)
    if hasattr(settings, key):
        return getattr(settings, key)
    return default


def _distance(start: QtCore.QPointF, end: QtCore.QPointF) -> float:
    dx = start.x() - end.x()
    dy = start.y() - end.y()
    return (dx * dx + dy * dy) ** 0.5


def _pulse_strength(state: dict, elapsed: float) -> Tuple[float, bool]:
    mode = state.get("mode")
    if mode == "arrival":
        linger = float(state.get("linger", 0.0))
        fade = float(state.get("fade", 0.0))
        if elapsed <= linger:
            return 1.0, False
        if fade <= 0:
            return 0.0, True
        fade_elapsed = elapsed - linger
        if fade_elapsed >= fade:
            return 0.0, True
        strength = 1.0 - (fade_elapsed / fade)
        return max(0.0, strength), False
    duration = float(state.get("duration", 0.5))
    if elapsed >= duration:
        return 0.0, True
    strength = 1.0 - (elapsed / max(duration, 0.001))
    return max(0.0, strength), False


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
