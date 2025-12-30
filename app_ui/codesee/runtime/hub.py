from __future__ import annotations

from collections import deque
import json
from pathlib import Path
import time
from typing import Deque, Dict, List, Optional

from PyQt6 import QtCore

from .events import (
    CodeSeeEvent,
    EVENT_EXPECT_CHECK,
    EVENT_SPAN_END,
    EVENT_SPAN_START,
    EVENT_SPAN_UPDATE,
    EVENT_TEST_PULSE,
    SpanEnd,
    SpanRecord,
    SpanStart,
    SpanUpdate,
    event_from_dict,
    event_to_dict,
    span_from_dict,
    span_to_dict,
)
from ..expectations import EVACheck, check_to_dict

_MAX_CHECKS = 200
_RECENT_CHECKS: Deque[EVACheck] = deque(maxlen=_MAX_CHECKS)
_MAX_SPANS = 200
_ACTIVE_SPANS: Dict[str, SpanRecord] = {}
_RECENT_SPANS: Deque[SpanRecord] = deque(maxlen=_MAX_SPANS)


def _record_check(check: EVACheck) -> None:
    _RECENT_CHECKS.append(check)


def recent_checks(limit: int = _MAX_CHECKS) -> List[EVACheck]:
    if limit <= 0:
        return []
    return list(_RECENT_CHECKS)[-limit:]


def active_spans() -> List[SpanRecord]:
    return list(_ACTIVE_SPANS.values())


def recent_spans(limit: int = _MAX_SPANS) -> List[SpanRecord]:
    if limit <= 0:
        return []
    return list(_RECENT_SPANS)[-limit:]


def _record_span_start(start: SpanStart) -> SpanRecord:
    ts = start.ts or time.time()
    record = SpanRecord(
        span_id=start.span_id,
        label=start.label,
        node_id=start.node_id,
        source_id=start.source_id,
        severity=start.severity,
        status="active",
        started_ts=ts,
        updated_ts=ts,
    )
    _ACTIVE_SPANS[start.span_id] = record
    return record


def _record_span_update(update: SpanUpdate) -> SpanRecord:
    ts = update.ts or time.time()
    record = _ACTIVE_SPANS.get(update.span_id)
    if not record:
        record = SpanRecord(
            span_id=update.span_id,
            label=update.span_id,
            status="active",
            started_ts=ts,
            updated_ts=ts,
        )
        _ACTIVE_SPANS[update.span_id] = record
    record.updated_ts = ts
    if update.progress is not None:
        record.progress = update.progress
    if update.message:
        record.message = update.message
    return record


def _record_span_end(end: SpanEnd) -> SpanRecord:
    ts = end.ts or time.time()
    record = _ACTIVE_SPANS.pop(end.span_id, None)
    if not record:
        record = SpanRecord(
            span_id=end.span_id,
            label=end.span_id,
            status=end.status or "completed",
            started_ts=ts,
            updated_ts=ts,
        )
    record.status = end.status or "completed"
    record.updated_ts = ts
    record.ended_ts = ts
    if end.message:
        record.message = end.message
    _RECENT_SPANS.append(record)
    return record


class CodeSeeRuntimeHub(QtCore.QObject):
    event_emitted = QtCore.pyqtSignal(object)

    def __init__(self, *, max_events: int = 500) -> None:
        super().__init__()
        self._events: Deque[CodeSeeEvent] = deque(maxlen=max_events)
        self._event_count = 0
        self._last_event_ts: Optional[str] = None
        self._workspace_id: Optional[str] = None
        self._persist_timer = QtCore.QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.timeout.connect(self._persist_activity)
        self._bus_connected = False

    def set_workspace_id(self, workspace_id: str) -> None:
        safe_id = _sanitize_workspace_id(workspace_id)
        if safe_id == self._workspace_id:
            return
        if self._workspace_id:
            self._persist_activity()
        self._workspace_id = safe_id
        self._load_activity()

    def bus_connected(self) -> bool:
        return self._bus_connected

    def set_bus_connected(self, connected: bool) -> None:
        self._bus_connected = bool(connected)
        self._schedule_persist()

    def publish(self, event: CodeSeeEvent) -> None:
        self._events.append(event)
        self._event_count += 1
        self._last_event_ts = event.ts
        self.event_emitted.emit(event)
        self._schedule_persist()

    def query(self, node_id: str, limit: int = 20) -> List[CodeSeeEvent]:
        results: List[CodeSeeEvent] = []
        for event in reversed(self._events):
            if node_id in (event.node_ids or []):
                results.append(event)
                if len(results) >= limit:
                    break
        return list(reversed(results))

    def recent(self, limit: int = 50) -> List[CodeSeeEvent]:
        if limit <= 0:
            return []
        return list(self._events)[-limit:]

    def event_count(self) -> int:
        return self._event_count

    def last_event_ts(self) -> Optional[str]:
        return self._last_event_ts

    def active_span_count(self) -> int:
        return len(_ACTIVE_SPANS)

    def list_active_spans(self) -> List[SpanRecord]:
        return active_spans()

    def list_recent_spans(self, limit: int = _MAX_SPANS) -> List[SpanRecord]:
        return recent_spans(limit)

    def publish_expect_check(self, check: EVACheck) -> None:
        _record_check(check)
        severity = "failure" if not check.passed else "info"
        event = CodeSeeEvent(
            ts=str(check.ts),
            kind=EVENT_EXPECT_CHECK,
            severity=severity,
            message=check.message,
            node_ids=[check.node_id],
            detail=None,
            source="expectation",
            payload=check_to_dict(check),
        )
        self.publish(event)

    def publish_span_start(self, start: SpanStart) -> SpanRecord:
        record = _record_span_start(start)
        event = CodeSeeEvent(
            ts=_format_ts(record.started_ts),
            kind=EVENT_SPAN_START,
            severity=record.severity or "info",
            message=record.label,
            node_ids=[record.node_id] if record.node_id else [],
            detail=record.message,
            source="span",
            payload={
                "span_id": record.span_id,
                "status": record.status,
            },
            source_node_id=record.source_id,
            target_node_id=record.node_id,
        )
        self.publish(event)
        return record

    def publish_span_update(self, update: SpanUpdate) -> SpanRecord:
        record = _record_span_update(update)
        event = CodeSeeEvent(
            ts=_format_ts(record.updated_ts),
            kind=EVENT_SPAN_UPDATE,
            severity=record.severity or "info",
            message=record.message or record.label,
            node_ids=[record.node_id] if record.node_id else [],
            detail=record.message,
            source="span",
            payload={
                "span_id": record.span_id,
                "status": record.status,
                "progress": record.progress,
            },
            source_node_id=record.source_id,
            target_node_id=record.node_id,
        )
        self.publish(event)
        return record

    def publish_span_end(self, end: SpanEnd) -> SpanRecord:
        record = _record_span_end(end)
        severity = record.severity or ("error" if record.status == "failed" else "info")
        event = CodeSeeEvent(
            ts=_format_ts(record.updated_ts),
            kind=EVENT_SPAN_END,
            severity=severity,
            message=record.message or record.label,
            node_ids=[record.node_id] if record.node_id else [],
            detail=record.message,
            source="span",
            payload={
                "span_id": record.span_id,
                "status": record.status,
            },
            source_node_id=record.source_id,
            target_node_id=record.node_id,
        )
        self.publish(event)
        return record

    def publish_test_pulse(self, *, node_ids: List[str]) -> None:
        event = CodeSeeEvent(
            ts=_format_ts(time.time()),
            kind=EVENT_TEST_PULSE,
            severity="info",
            message="Test pulse",
            node_ids=list(node_ids or []),
            source="codesee",
        )
        self.publish(event)

    def flush_activity(self) -> None:
        self._persist_activity()

    def activity_path(self) -> Optional[Path]:
        if not self._workspace_id:
            return None
        return _activity_path(self._workspace_id)

    def _schedule_persist(self) -> None:
        if not self._workspace_id:
            return
        if self._persist_timer.isActive():
            return
        self._persist_timer.start(350)

    def _persist_activity(self) -> None:
        if not self._workspace_id:
            return
        path = _activity_path(self._workspace_id)
        payload = {
            "format_version": 1,
            "workspace_id": self._workspace_id,
            "updated_ts": time.time(),
            "bus_connected": bool(self._bus_connected),
            "events": [event_to_dict(event) for event in list(self._events)],
            "active_spans": [span_to_dict(span) for span in active_spans()],
            "recent_spans": [span_to_dict(span) for span in recent_spans()],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            return

    def _load_activity(self) -> None:
        if not self._workspace_id:
            return
        path = _activity_path(self._workspace_id)
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        events_raw = payload.get("events") if isinstance(payload, dict) else None
        active_raw = payload.get("active_spans") if isinstance(payload, dict) else None
        recent_raw = payload.get("recent_spans") if isinstance(payload, dict) else None
        self._events.clear()
        _ACTIVE_SPANS.clear()
        _RECENT_SPANS.clear()
        if isinstance(events_raw, list):
            for entry in events_raw:
                event = event_from_dict(entry)
                if event:
                    self._events.append(event)
        if isinstance(active_raw, list):
            for entry in active_raw:
                span = span_from_dict(entry)
                if span:
                    _ACTIVE_SPANS[span.span_id] = span
        if isinstance(recent_raw, list):
            for entry in recent_raw:
                span = span_from_dict(entry)
                if span:
                    _RECENT_SPANS.append(span)
        if self._events:
            self._event_count = len(self._events)
            self._last_event_ts = self._events[-1].ts
        else:
            self._event_count = 0
            self._last_event_ts = None


_GLOBAL_HUB: Optional[CodeSeeRuntimeHub] = None


def set_global_hub(hub: CodeSeeRuntimeHub) -> None:
    global _GLOBAL_HUB
    _GLOBAL_HUB = hub


def get_global_hub() -> Optional[CodeSeeRuntimeHub]:
    return _GLOBAL_HUB


def publish_expect_check_global(check: EVACheck) -> None:
    hub = get_global_hub()
    if hub:
        hub.publish_expect_check(check)
    else:
        _record_check(check)


def publish_span_start_global(start: SpanStart) -> Optional[SpanRecord]:
    hub = get_global_hub()
    if hub:
        return hub.publish_span_start(start)
    return _record_span_start(start)


def publish_span_update_global(update: SpanUpdate) -> Optional[SpanRecord]:
    hub = get_global_hub()
    if hub:
        return hub.publish_span_update(update)
    return _record_span_update(update)


def publish_span_end_global(end: SpanEnd) -> Optional[SpanRecord]:
    hub = get_global_hub()
    if hub:
        return hub.publish_span_end(end)
    return _record_span_end(end)


def publish_test_pulse_global(node_ids: List[str]) -> None:
    hub = get_global_hub()
    if hub:
        hub.publish_test_pulse(node_ids=node_ids)


def _format_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts or time.time()))


def _sanitize_workspace_id(workspace_id: str) -> str:
    text = str(workspace_id or "").strip()
    if not text:
        return "default"
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text) or "default"


def _activity_path(workspace_id: str) -> Path:
    safe_id = _sanitize_workspace_id(workspace_id)
    return Path("data") / "workspaces" / safe_id / "codesee" / "activity_latest.json"
