from __future__ import annotations

from collections import deque
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

    def publish(self, event: CodeSeeEvent) -> None:
        self._events.append(event)
        self._event_count += 1
        self._last_event_ts = event.ts
        self.event_emitted.emit(event)

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
