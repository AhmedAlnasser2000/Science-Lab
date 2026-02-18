from __future__ import annotations

import time
from bisect import bisect_right
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
        on_peek: Optional[Callable] = None,
        on_toggle_peek: Optional[Callable] = None,
        peek_menu_state: Optional[Callable] = None,
        on_status_badges: Optional[Callable] = None,
        icon_style: str = "color",
        node_theme: str = "neutral",
    ) -> None:
        super().__init__()
        self.on_open_subgraph = on_open_subgraph
        self.on_layout_changed = on_layout_changed
        self.on_inspect = on_inspect
        self.on_peek = on_peek
        self.on_toggle_peek = on_toggle_peek
        self.peek_menu_state = peek_menu_state
        self._on_status_badges = on_status_badges
        self._icon_style = icon_style
        self._node_theme = node_theme or "neutral"
        self._badge_layers: Dict[str, bool] = {}
        self._empty_message: Optional[str] = None
        self._empty_item: Optional[QtWidgets.QGraphicsTextItem] = None
        self._reduced_motion = False
        self._nodes: Dict[str, NodeItem] = {}
        self._edges: list[EdgeItem] = []
        self._edge_index: Dict[Tuple[str, str], EdgeItem] = {}
        self._signals: list[dict] = []
        self._pulses: Dict[str, dict] = {}
        self._span_tints: Dict[str, dict] = {}
        self._activity_glow: Dict[str, dict] = {}
        self._node_activity_ts: Dict[str, float] = {}
        self._node_activity_color: Dict[str, QtGui.QColor] = {}
        self._activity_fade_s = 2.0
        # Status semantics:
        # - active_count reflects current concurrent/visible states (decay/cap applies).
        # - total_count reflects session occurrences (monotonic while CodeSee is open).
        self._status_totals: Dict[str, Dict[str, int]] = {}
        self._context_nodes: set[str] = set()
        self._context_label: Optional[str] = None
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
        self._edge_index = {}
        self._empty_item = None
        self._signals = []
        self._pulses = {}
        self._activity_glow = {}
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
                on_peek=self.on_peek,
                on_toggle_peek=self.on_toggle_peek,
                peek_menu_state=self.peek_menu_state,
                on_status_badges=self._on_status_badges,
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

        if self._node_activity_ts:
            self._node_activity_ts = {
                node_id: ts for node_id, ts in self._node_activity_ts.items() if node_id in self._nodes
            }
            self._node_activity_color = {
                node_id: color
                for node_id, color in self._node_activity_color.items()
                if node_id in self._node_activity_ts
            }
        if self._status_totals:
            self._status_totals = {
                node_id: totals for node_id, totals in self._status_totals.items() if node_id in self._nodes
            }

        self._apply_tints()
        self._apply_context()
        self._update_node_statuses()

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
            self._edge_index[(edge.src_node_id, edge.dst_node_id)] = edge_item

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

    def set_context_nodes(self, node_ids: Optional[set[str]], *, label: Optional[str] = None) -> None:
        self._context_nodes = set(node_ids or [])
        self._context_label = label
        for node_id in self._context_nodes:
            self._bump_status_total(node_id, "context", 1)
        self._apply_context()
        self._update_node_statuses()

    def set_span_tints(
        self,
        node_ids: list[str],
        *,
        color: Optional[QtGui.QColor],
        strength: float,
    ) -> None:
        self._span_tints = {}
        for node_id in node_ids:
            self._span_tints[str(node_id)] = {"color": color, "strength": strength}
        self._apply_tints()

    def bump_activity(
        self,
        node_id: str,
        *,
        color: Optional[QtGui.QColor],
        strength: float,
        linger_ms: int,
        fade_ms: int,
    ) -> None:
        if node_id not in self._nodes:
            return
        self._record_activity(node_id, color)
        self._activity_glow[node_id] = {
            "t0": time.monotonic(),
            "linger": max(0.0, float(linger_ms) / 1000.0),
            "fade": max(0.0, float(fade_ms) / 1000.0),
            "strength": max(0.05, min(1.0, float(strength))),
            "color": color,
        }
        if not self._signal_timer.isActive():
            self._signal_timer.start()

    def flash_node(self, node_id: str, color: Optional[QtGui.QColor] = None) -> None:
        self.flash_node_with_settings(node_id, color=color, settings=None)

    def flash_node_with_settings(
        self,
        node_id: str,
        *,
        color: Optional[QtGui.QColor],
        settings,
    ) -> None:
        linger_ms = _setting_value(settings, "arrive_linger_ms", 300)
        fade_ms = _setting_value(settings, "fade_ms", 500)
        duration_ms = _setting_value(settings, "pulse_duration_ms", 650)
        min_alpha = _setting_value(settings, "pulse_min_alpha", 0.18)
        intensity = _setting_value(settings, "intensity_multiplier", 1.0)
        curve = _setting_value(settings, "fade_curve", "linear")
        if self._reduced_motion:
            self._queue_pulse(
                node_id,
                color=color,
                mode="arrival",
                linger_ms=int(linger_ms),
                fade_ms=int(fade_ms),
                min_alpha=float(min_alpha),
                intensity=float(intensity),
                fade_curve=str(curve),
            )
            return
        self._queue_pulse(
            node_id,
            color=color,
            mode="flash",
            duration_ms=int(duration_ms),
            min_alpha=float(min_alpha),
            intensity=float(intensity),
            fade_curve=str(curve),
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
        self._record_activity(target_id, color)
        self._bump_status_total(target_id, "signal", 1)
        speed = _setting_value(settings, "travel_speed_px_per_s", 900)
        travel_duration_ms = _setting_value(settings, "travel_duration_ms", 0)
        linger_ms = _setting_value(settings, "arrive_linger_ms", 300)
        fade_ms = _setting_value(settings, "fade_ms", 500)
        radius = max(5.0, float(_setting_value(settings, "pulse_radius_px", 10)))
        alpha = _setting_value(settings, "pulse_alpha", 0.7)
        min_alpha = _setting_value(settings, "pulse_min_alpha", 0.18)
        intensity = _setting_value(settings, "intensity_multiplier", 1.0)
        curve = _setting_value(settings, "fade_curve", "linear")
        max_signals = _setting_value(settings, "max_concurrent_signals", 6)
        trail_length = int(_setting_value(settings, "trail_length", 3))
        trail_spacing_ms = int(_setting_value(settings, "trail_spacing_ms", 70))
        if self._reduced_motion:
            self._queue_pulse(
                target_id,
                color=color,
                mode="arrival",
                linger_ms=int(linger_ms),
                fade_ms=int(fade_ms),
                min_alpha=float(min_alpha),
                intensity=float(intensity),
                fade_curve=str(curve),
            )
            return
        edge_item, reverse = self._find_edge(source_id, target_id)
        if not source_id or not edge_item:
            self._queue_pulse(
                target_id,
                color=color,
                mode="arrival",
                linger_ms=int(linger_ms),
                fade_ms=int(fade_ms),
                min_alpha=float(min_alpha),
                intensity=float(intensity),
                fade_curve=str(curve),
            )
            return
        trail_length = max(1, trail_length)
        max_signals = max(1, int(max_signals))
        while len(self._signals) + trail_length > max_signals:
            self._drop_oldest_signal()
        src_item = self._nodes.get(source_id)
        if not src_item:
            self._queue_pulse(
                target_id,
                color=color,
                mode="arrival",
                linger_ms=int(linger_ms),
                fade_ms=int(fade_ms),
                intensity=float(intensity),
            )
            return
        path = edge_item.geometry_path()
        start_percent = 1.0 if reverse else 0.0
        start = path.pointAtPercent(start_percent)
        if travel_duration_ms:
            duration = max(0.15, float(travel_duration_ms) / 1000.0)
        else:
            distance = max(1.0, float(path.length()))
            duration = max(0.15, distance / max(1.0, float(speed)))
        intensity = max(0.1, float(intensity))
        alpha = min(1.0, max(0.25, float(alpha) * intensity))
        now = time.monotonic()
        for index in range(trail_length):
            offset_s = (trail_spacing_ms * index) / 1000.0
            decay = 1.0 - (0.18 * index)
            dot_alpha = max(0.25, float(alpha) * float(intensity) * decay)
            dot = SignalDotItem(radius=float(radius), color=color, alpha=float(dot_alpha))
            dot.setPos(start)
            self.addItem(dot)
            self._signals.append(
                {
                    "dot": dot,
                    "edge": edge_item,
                    "reverse": reverse,
                    "target": target_id,
                    "t0": now + offset_s,
                    "duration": duration,
                    "linger_ms": int(linger_ms),
                    "fade_ms": int(fade_ms),
                    "color": color,
                    "min_alpha": float(min_alpha),
                    "intensity": float(intensity),
                    "fade_curve": str(curve),
                    "arrival": index == (trail_length - 1),
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

    def active_pulse_count(self) -> int:
        return len(self._signals) + len(self._pulses)

    def clear_pulses(self) -> None:
        if self._pulses:
            for node_id, item in list(self._nodes.items()):
                try:
                    item.set_highlight(0.0, None)
                except RuntimeError:
                    pass
            self._pulses = {}
        if self._signals:
            for state in list(self._signals):
                dot = state.get("dot")
                if isinstance(dot, SignalDotItem):
                    try:
                        self.removeItem(dot)
                    except RuntimeError:
                        pass
            self._signals = []
        if self._node_activity_ts:
            for node_id, item in list(self._nodes.items()):
                try:
                    item.set_activity(0.0, None)
                except RuntimeError:
                    pass
            self._node_activity_ts = {}
            self._node_activity_color = {}
        if (
            not self._signals
            and not self._pulses
            and not self._activity_glow
            and not self._node_activity_ts
            and self._signal_timer.isActive()
        ):
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
            if progress < 0.0:
                dot.setVisible(False)
                remaining.append(state)
                continue
            if not dot.isVisible():
                dot.setVisible(True)
            if progress >= 1.0:
                self.removeItem(dot)
                target_id = str(state.get("target"))
                if state.get("arrival", True):
                    self._queue_pulse(
                        target_id,
                        color=state.get("color"),
                        mode="arrival",
                        linger_ms=int(state.get("linger_ms", 300)),
                        fade_ms=int(state.get("fade_ms", 500)),
                        min_alpha=float(state.get("min_alpha", 0.1)),
                        intensity=float(state.get("intensity", 1.0)),
                        fade_curve=str(state.get("fade_curve", "linear")),
                    )
                continue
            edge_item = state.get("edge")
            if isinstance(edge_item, EdgeItem):
                reverse = bool(state.get("reverse", False))
                percent = _edge_progress(progress, reverse)
                path = edge_item.geometry_path()
                pos = path.pointAtPercent(percent)
                dot.setPos(pos)
            remaining.append(state)
        self._signals = remaining
        self._tick_pulses(now)
        self._tick_activity(now)
        self._tick_node_activity(now)
        self._update_node_statuses()
        if not self._signals and not self._pulses and not self._activity_glow and not self._node_activity_ts:
            if self._signal_timer.isActive():
                self._signal_timer.stop()

    def _find_edge(self, source_id: Optional[str], target_id: Optional[str]) -> Tuple[Optional[EdgeItem], bool]:
        if not source_id or not target_id:
            return None, False
        direct = self._edge_index.get((source_id, target_id))
        if direct:
            return direct, False
        reverse = self._edge_index.get((target_id, source_id))
        if reverse:
            return reverse, True
        return None, False

    def _queue_pulse(
        self,
        node_id: str,
        *,
        color: Optional[QtGui.QColor],
        mode: str,
        duration_ms: int = 500,
        linger_ms: int = 0,
        fade_ms: int = 0,
        min_alpha: float = 0.0,
        intensity: float = 1.0,
        fade_curve: str = "linear",
    ) -> None:
        if node_id not in self._nodes:
            return
        self._record_activity(node_id, color)
        self._bump_status_total(node_id, "pulse", 1)
        self._pulses[node_id] = {
            "t0": time.monotonic(),
            "color": color,
            "mode": mode,
            "duration": max(0.05, float(duration_ms) / 1000.0),
            "linger": max(0.0, float(linger_ms) / 1000.0),
            "fade": max(0.0, float(fade_ms) / 1000.0),
            "min_alpha": max(0.0, min(1.0, float(min_alpha))),
            "intensity": max(0.1, float(intensity)),
            "curve": str(fade_curve or "linear"),
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

    def _tick_activity(self, now: float) -> None:
        if not self._activity_glow:
            return
        remove_ids = []
        for node_id, state in list(self._activity_glow.items()):
            t0 = float(state.get("t0", now))
            linger = float(state.get("linger", 0.0))
            fade = float(state.get("fade", 0.0))
            strength = float(state.get("strength", 0.2))
            elapsed = max(0.0, now - t0)
            if elapsed <= linger:
                state["current"] = strength
                continue
            if fade <= 0.0:
                remove_ids.append(node_id)
                continue
            progress = (elapsed - linger) / fade
            if progress >= 1.0:
                remove_ids.append(node_id)
                continue
            state["current"] = max(0.0, strength * (1.0 - progress))
        for node_id in remove_ids:
            self._activity_glow.pop(node_id, None)
        self._apply_tints()

    def _apply_tints(self) -> None:
        if not self._nodes:
            return
        for node_id, item in self._nodes.items():
            base = self._span_tints.get(node_id)
            active = self._activity_glow.get(node_id)
            base_strength = float(base.get("strength", 0.0)) if base else 0.0
            active_strength = float(active.get("current", 0.0)) if active else 0.0
            if active and active_strength >= base_strength:
                item.set_tint(active_strength, active.get("color"))
            elif base and base_strength > 0.0:
                item.set_tint(base_strength, base.get("color"))
            else:
                item.set_tint(0.0, None)

    def _apply_context(self) -> None:
        if not self._nodes:
            return
        color = QtGui.QColor("#2f9e44")
        for node_id, item in self._nodes.items():
            item.set_context_active(node_id in self._context_nodes, color)

    def _record_activity(self, node_id: str, color: Optional[QtGui.QColor]) -> None:
        self._node_activity_ts[node_id] = time.monotonic()
        if isinstance(color, QtGui.QColor):
            self._node_activity_color[node_id] = color
        self._bump_status_total(node_id, "activity", 1)
        if not self._signal_timer.isActive():
            self._signal_timer.start()

    def _tick_node_activity(self, now: float) -> None:
        if not self._node_activity_ts:
            return
        remove_ids = []
        for node_id, ts in list(self._node_activity_ts.items()):
            age = max(0.0, now - float(ts))
            alpha = activity_alpha(age, self._activity_fade_s, self._reduced_motion)
            item = self._nodes.get(node_id)
            color = self._node_activity_color.get(node_id)
            if not item:
                remove_ids.append(node_id)
                continue
            if alpha <= 0.0:
                remove_ids.append(node_id)
                if item:
                    try:
                        item.set_activity(0.0, None)
                    except RuntimeError:
                        pass
                continue
            if item:
                try:
                    item.set_activity(alpha, color)
                except RuntimeError:
                    remove_ids.append(node_id)
        for node_id in remove_ids:
            self._node_activity_ts.pop(node_id, None)
            self._node_activity_color.pop(node_id, None)

    def _update_node_statuses(self) -> None:
        if not self._nodes:
            return
        now = time.monotonic()
        for node_id, item in self._nodes.items():
            totals = self._status_totals.get(node_id, {})
            statuses: list[dict] = []
            if node_id in self._context_nodes:
                statuses.append(
                    {
                        "key": "context",
                        "label": "Current screen context",
                        "detail": self._context_label,
                        "color": "#2f9e44",
                        "active_count": 1,
                        "total_count": int(totals.get("context", 1)),
                    }
                )
            ts = self._node_activity_ts.get(node_id)
            if ts is not None:
                age = max(0.0, now - float(ts))
                if activity_alpha(age, self._activity_fade_s, self._reduced_motion) > 0.0:
                    statuses.append(
                        {
                            "key": "activity",
                            "label": "Recent activity",
                            "last_seen": age,
                            "color": "#4c6ef5",
                            "active_count": 1,
                            "total_count": int(totals.get("activity", 0)),
                        }
                    )
            if node_id in self._pulses:
                statuses.append(
                    {
                        "key": "pulse",
                        "label": "Pulse active",
                        "color": "#845ef7",
                        "active_count": 1,
                        "total_count": int(totals.get("pulse", 0)),
                    }
                )
            signal_count = sum(1 for state in self._signals if state.get("target") == node_id)
            if signal_count:
                statuses.append(
                    {
                        "key": "signal",
                        "label": "Signals",
                        "count": signal_count,
                        "color": "#2b8a3e",
                        "active_count": int(signal_count),
                        "total_count": int(totals.get("signal", 0)),
                    }
                )
            item.set_status_badges(statuses)

    def _bump_status_total(self, node_id: str, key: str, delta: int) -> None:
        totals = self._status_totals.get(node_id)
        if totals is None:
            totals = {}
            self._status_totals[node_id] = totals
        totals[key] = int(totals.get(key, 0)) + int(delta)

    def _apply_span_tints(self) -> None:
        self._apply_tints()


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


def _build_cumdist(points: list[tuple[float, float]]) -> tuple[list[float], float]:
    if not points:
        return [0.0], 0.0
    cumdist = [0.0]
    total = 0.0
    for idx in range(1, len(points)):
        x0, y0 = points[idx - 1]
        x1, y1 = points[idx]
        dx = x1 - x0
        dy = y1 - y0
        total += (dx * dx + dy * dy) ** 0.5
        cumdist.append(total)
    return cumdist, total


def _distance_to_percent(cumdist: list[float], total: float, distance: float) -> float:
    if total <= 0.0:
        return 0.0
    distance = max(0.0, min(float(distance), float(total)))
    idx = max(0, bisect_right(cumdist, distance) - 1)
    if idx >= len(cumdist) - 1:
        return 1.0
    seg_start = cumdist[idx]
    seg_end = cumdist[idx + 1]
    seg_len = max(1e-9, seg_end - seg_start)
    t = (distance - seg_start) / seg_len
    p0 = idx / max(1.0, (len(cumdist) - 1))
    p1 = (idx + 1) / max(1.0, (len(cumdist) - 1))
    return p0 + (p1 - p0) * t


def _pulse_strength(state: dict, elapsed: float) -> Tuple[float, bool]:
    mode = state.get("mode")
    curve = str(state.get("curve") or "linear")
    min_alpha = max(0.0, min(1.0, float(state.get("min_alpha", 0.0))))
    intensity = max(0.1, float(state.get("intensity", 1.0)))
    if mode == "arrival":
        linger = float(state.get("linger", 0.0))
        fade = float(state.get("fade", 0.0))
        if elapsed <= linger:
            return max(1.0, min_alpha) * intensity, False
        if fade <= 0:
            return 0.0, True
        fade_elapsed = elapsed - linger
        if fade_elapsed >= fade:
            return 0.0, True
        progress = fade_elapsed / fade
        strength = 1.0 - progress
        if curve == "ease":
            strength = strength * strength
        strength = max(min_alpha, strength) * intensity
        return max(0.0, strength), False
    duration = float(state.get("duration", 0.5))
    if elapsed >= duration:
        return 0.0, True
    progress = elapsed / max(duration, 0.001)
    strength = 1.0 - progress
    if curve == "ease":
        strength = strength * strength
    strength = max(min_alpha, strength) * intensity
    return max(0.0, strength), False


def _edge_progress(progress: float, reverse: bool) -> float:
    clamped = max(0.0, min(1.0, float(progress)))
    return 1.0 - clamped if reverse else clamped


def activity_alpha(age_s: float, fade_s: float = 2.0, reduced_motion: bool = False) -> float:
    if reduced_motion:
        return 1.0 if age_s <= 1.0 else 0.0
    if fade_s <= 0.0:
        return 0.0
    return max(0.0, 1.0 - (age_s / fade_s))


def _node_diff_state(node_id: str, diff_result: Optional[DiffResult]) -> Optional[str]:
    if not diff_result:
        return None
    if node_id in diff_result.nodes_added:
        return "added"
    if node_id in diff_result.nodes_removed:
        return "removed"
    if node_id in diff_result.nodes_changed:
        return "changed"
    return None


def _edge_diff_state(edge, diff_result: Optional[DiffResult]) -> Optional[str]:
    if not diff_result:
        return None
    if edge_key(edge) in diff_result.edges_added:
        return "added"
    return None
