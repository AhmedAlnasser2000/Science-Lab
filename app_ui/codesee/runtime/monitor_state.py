from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, Optional, Set, Tuple

from .events import (
    CodeSeeEvent,
    EVENT_APP_CRASH,
    EVENT_APP_ERROR,
    EVENT_BUS_REPLY,
    EVENT_BUS_REQUEST,
    EVENT_SPAN_END,
    EVENT_SPAN_START,
    EVENT_SPAN_UPDATE,
)

STATE_INACTIVE = "INACTIVE"
STATE_RUNNING = "RUNNING"
STATE_DEGRADED = "DEGRADED"
STATE_FATAL = "FATAL"

_TERMINAL_KINDS = {EVENT_APP_ERROR, EVENT_APP_CRASH}
_TRACE_KINDS = {EVENT_BUS_REQUEST, EVENT_BUS_REPLY}
_SUCCESS_STATUSES = {"completed", "done", "success", "ok"}
_FAILED_STATUSES = {"failed", "error", "crash"}


@dataclass
class _SpanState:
    span_id: str
    node_id: str
    updated_ts: float
    status: str = "active"


@dataclass
class _NodeState:
    active_span_ids: Set[str] = field(default_factory=set)
    running_error_count: int = 0
    stuck: bool = False
    fatal: bool = False
    fatal_since: float = 0.0
    state: str = STATE_INACTIVE
    last_change_ts: float = 0.0


class MonitorState:
    """Stateful monitor model for CodeSee (UI-agnostic, deterministic)."""

    def __init__(
        self,
        *,
        span_stuck_seconds: int = 10,
        repeated_error_threshold: int = 2,
        trace_edge_limit: int = 200,
        follow_last_trace: bool = True,
        now_provider: Optional[Callable[[], float]] = None,
    ) -> None:
        self._span_stuck_seconds = max(1, int(span_stuck_seconds))
        self._repeated_error_threshold = max(1, int(repeated_error_threshold))
        self._trace_edge_limit = max(1, int(trace_edge_limit))
        self._follow_last_trace = bool(follow_last_trace)
        self._now = now_provider or time.time

        self._spans: Dict[str, _SpanState] = {}
        self._nodes: Dict[str, _NodeState] = {}

        self._trace_edges: Dict[str, Deque[Tuple[str, str]]] = {}
        self._trace_nodes: Dict[str, Set[str]] = {}
        self._last_seen_trace_id: Optional[str] = None
        self._active_trace_id: Optional[str] = None
        self._pinned_trace_id: Optional[str] = None

    def on_event(self, event: CodeSeeEvent) -> None:
        now = float(self._now())

        if event.kind == EVENT_SPAN_START:
            self._on_span_start(event, now)
        elif event.kind == EVENT_SPAN_UPDATE:
            self._on_span_update(event, now)
        elif event.kind == EVENT_SPAN_END:
            self._on_span_end(event, now)

        self._on_error_event(event, now)
        self._on_trace_event(event)
        self._recompute_states(now)

    def tick(self, now: float) -> None:
        current = float(now)
        for node in self._nodes.values():
            node.stuck = False
        for span in self._spans.values():
            node = self._nodes.get(span.node_id)
            if not node:
                continue
            if (current - float(span.updated_ts)) > float(self._span_stuck_seconds):
                node.stuck = True
        self._recompute_states(current)

    def clear(self) -> None:
        self._spans.clear()
        self._nodes.clear()
        self._trace_edges.clear()
        self._trace_nodes.clear()
        self._last_seen_trace_id = None
        self._active_trace_id = None
        self._pinned_trace_id = None

    def pin_trace(self, trace_id: str) -> None:
        trace = str(trace_id or "").strip()
        if not trace:
            return
        self._ensure_trace(trace)
        self._pinned_trace_id = trace
        self._active_trace_id = trace

    def unpin_trace(self) -> None:
        self._pinned_trace_id = None
        if self._follow_last_trace and self._last_seen_trace_id:
            self._active_trace_id = self._last_seen_trace_id

    def set_follow_last_trace(self, enabled: bool) -> None:
        self._follow_last_trace = bool(enabled)
        if self._follow_last_trace and not self._pinned_trace_id and self._last_seen_trace_id:
            self._active_trace_id = self._last_seen_trace_id

    def snapshot_states(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for node_id, node in self._nodes.items():
            out[node_id] = {
                "state": node.state,
                "active": bool(node.active_span_ids),
                "active_span_count": int(len(node.active_span_ids)),
                "stuck": bool(node.stuck),
                "fatal": bool(node.fatal),
                "error_count": int(node.running_error_count),
                "last_change_ts": float(node.last_change_ts),
            }
        return out

    def snapshot_trace(self) -> tuple[list[tuple[str, str]], set[str], Optional[str]]:
        trace_id = self._active_trace_id
        if not trace_id:
            return [], set(), None
        edges = list(self._trace_edges.get(trace_id, ()))
        nodes = set(self._trace_nodes.get(trace_id, set()))
        return edges, nodes, trace_id

    def _on_span_start(self, event: CodeSeeEvent, now: float) -> None:
        span_id = _payload_text(event, "span_id")
        node_id = _event_node_id(event)
        if not span_id or not node_id:
            return
        existing = self._spans.get(span_id)
        if existing and existing.node_id != node_id:
            previous_node = self._nodes.get(existing.node_id)
            if previous_node:
                previous_node.active_span_ids.discard(span_id)
        self._spans[span_id] = _SpanState(span_id=span_id, node_id=node_id, updated_ts=now, status="active")
        node = self._node(node_id)
        node.active_span_ids.add(span_id)
        node.running_error_count = 0
        if node.fatal:
            node.fatal = False
        node.last_change_ts = now

    def _on_span_update(self, event: CodeSeeEvent, now: float) -> None:
        span_id = _payload_text(event, "span_id")
        if not span_id:
            return
        span = self._spans.get(span_id)
        if not span:
            node_id = _event_node_id(event)
            if not node_id:
                return
            span = _SpanState(span_id=span_id, node_id=node_id, updated_ts=now, status="active")
            self._spans[span_id] = span
            self._node(node_id).active_span_ids.add(span_id)
        span.updated_ts = now
        status = _payload_text(event, "status").lower()
        if status:
            span.status = status

    def _on_span_end(self, event: CodeSeeEvent, now: float) -> None:
        span_id = _payload_text(event, "span_id")
        status = _payload_text(event, "status").lower()
        node_id = _event_node_id(event)
        span = self._spans.pop(span_id, None) if span_id else None
        if span and not node_id:
            node_id = span.node_id
        if not node_id:
            return
        node = self._node(node_id)
        if span_id:
            node.active_span_ids.discard(span_id)
        if status in _FAILED_STATUSES:
            node.fatal = True
            node.fatal_since = now
            node.last_change_ts = now
            return
        if status in _SUCCESS_STATUSES:
            node.running_error_count = 0
            if node.fatal and not node.active_span_ids and now >= node.fatal_since:
                node.fatal = False
                node.last_change_ts = now

    def _on_error_event(self, event: CodeSeeEvent, now: float) -> None:
        node_ids = _event_node_ids(event)
        if not node_ids:
            return
        if event.kind in _TERMINAL_KINDS:
            for node_id in node_ids:
                node = self._node(node_id)
                node.fatal = True
                node.fatal_since = now
                node.last_change_ts = now
            return
        if str(event.severity or "").lower() != "error":
            return
        for node_id in node_ids:
            node = self._node(node_id)
            if node.active_span_ids:
                node.running_error_count += 1
                node.last_change_ts = now

    def _on_trace_event(self, event: CodeSeeEvent) -> None:
        if event.kind not in _TRACE_KINDS or not isinstance(event.payload, dict):
            return
        trace_id = str(event.payload.get("trace_id") or "").strip()
        if not trace_id:
            return
        self._ensure_trace(trace_id)
        self._last_seen_trace_id = trace_id

        source = str(event.source_node_id or "").strip()
        target = str(event.target_node_id or "").strip()
        if source:
            self._trace_nodes[trace_id].add(source)
        if target:
            self._trace_nodes[trace_id].add(target)
        if source and target:
            self._trace_edges[trace_id].append((source, target))

        if self._pinned_trace_id:
            self._active_trace_id = self._pinned_trace_id
            return
        if self._follow_last_trace or not self._active_trace_id:
            self._active_trace_id = trace_id

    def _recompute_states(self, now: float) -> None:
        for node in self._nodes.values():
            next_state = _compute_state(
                fatal=node.fatal,
                active=bool(node.active_span_ids),
                stuck=node.stuck,
                error_count=node.running_error_count,
                repeated_error_threshold=self._repeated_error_threshold,
            )
            if next_state != node.state:
                node.state = next_state
                node.last_change_ts = now

    def _node(self, node_id: str) -> _NodeState:
        state = self._nodes.get(node_id)
        if state is None:
            state = _NodeState()
            self._nodes[node_id] = state
        return state

    def _ensure_trace(self, trace_id: str) -> None:
        if trace_id not in self._trace_edges:
            self._trace_edges[trace_id] = deque(maxlen=self._trace_edge_limit)
        if trace_id not in self._trace_nodes:
            self._trace_nodes[trace_id] = set()


def _compute_state(
    *,
    fatal: bool,
    active: bool,
    stuck: bool,
    error_count: int,
    repeated_error_threshold: int,
) -> str:
    if fatal:
        return STATE_FATAL
    if active and (stuck or error_count >= repeated_error_threshold):
        return STATE_DEGRADED
    if active:
        return STATE_RUNNING
    return STATE_INACTIVE


def _payload_text(event: CodeSeeEvent, key: str) -> str:
    if not isinstance(event.payload, dict):
        return ""
    return str(event.payload.get(key) or "").strip()


def _event_node_id(event: CodeSeeEvent) -> str:
    if event.target_node_id:
        text = str(event.target_node_id).strip()
        if text:
            return text
    for node_id in event.node_ids or []:
        text = str(node_id).strip()
        if text:
            return text
    if event.source_node_id:
        text = str(event.source_node_id).strip()
        if text:
            return text
    return ""


def _event_node_ids(event: CodeSeeEvent) -> list[str]:
    ids: list[str] = []
    for node_id in event.node_ids or []:
        text = str(node_id).strip()
        if text:
            ids.append(text)
    if event.target_node_id:
        text = str(event.target_node_id).strip()
        if text:
            ids.append(text)
    if event.source_node_id:
        text = str(event.source_node_id).strip()
        if text:
            ids.append(text)
    deduped: list[str] = []
    seen: set[str] = set()
    for node_id in ids:
        if node_id in seen:
            continue
        deduped.append(node_id)
        seen.add(node_id)
    return deduped
