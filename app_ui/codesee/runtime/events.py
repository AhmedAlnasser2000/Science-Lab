from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


EVENT_APP_ACTIVITY = "app.activity"
EVENT_APP_ERROR = "app.error"
EVENT_APP_CRASH = "app.crash"
EVENT_JOB_UPDATE = "job.update"
EVENT_BUS_REQUEST = "bus.request"
EVENT_BUS_REPLY = "bus.reply"
EVENT_LOG_LINE = "log.line"
EVENT_EXPECT_CHECK = "expect.check"
EVENT_SPAN_START = "span.start"
EVENT_SPAN_UPDATE = "span.update"
EVENT_SPAN_END = "span.end"
EVENT_TEST_PULSE = "codesee.test_pulse"


@dataclass(frozen=True)
class CodeSeeEvent:
    ts: str
    kind: str
    severity: str
    message: str
    node_ids: List[str] = field(default_factory=list)
    detail: Optional[str] = None
    source: Optional[str] = None
    payload: Optional[dict] = None
    source_node_id: Optional[str] = None
    target_node_id: Optional[str] = None


@dataclass(frozen=True)
class SpanStart:
    span_id: str
    label: str
    node_id: Optional[str] = None
    source_id: Optional[str] = None
    severity: Optional[str] = None
    ts: float = 0.0


@dataclass(frozen=True)
class SpanUpdate:
    span_id: str
    progress: Optional[float] = None
    message: Optional[str] = None
    ts: float = 0.0


@dataclass(frozen=True)
class SpanEnd:
    span_id: str
    status: str
    ts: float = 0.0
    message: Optional[str] = None


@dataclass
class SpanRecord:
    span_id: str
    label: str
    node_id: Optional[str] = None
    source_id: Optional[str] = None
    severity: Optional[str] = None
    status: str = "active"
    started_ts: float = 0.0
    updated_ts: float = 0.0
    ended_ts: Optional[float] = None
    progress: Optional[float] = None
    message: Optional[str] = None


def span_to_dict(span: SpanRecord) -> dict:
    payload: dict = {
        "span_id": span.span_id,
        "label": span.label,
        "status": span.status,
        "started_ts": span.started_ts,
        "updated_ts": span.updated_ts,
    }
    if span.node_id:
        payload["node_id"] = span.node_id
    if span.source_id:
        payload["source_id"] = span.source_id
    if span.severity:
        payload["severity"] = span.severity
    if span.ended_ts is not None:
        payload["ended_ts"] = span.ended_ts
    if span.progress is not None:
        payload["progress"] = span.progress
    if span.message:
        payload["message"] = span.message
    return payload


def span_from_dict(data: dict) -> Optional[SpanRecord]:
    if not isinstance(data, dict):
        return None
    span_id = str(data.get("span_id") or data.get("id") or "").strip()
    if not span_id:
        return None
    label = str(data.get("label") or span_id)
    record = SpanRecord(
        span_id=span_id,
        label=label,
        node_id=_optional_str(data.get("node_id")),
        source_id=_optional_str(data.get("source_id")),
        severity=_optional_str(data.get("severity")),
        status=str(data.get("status") or "active"),
        started_ts=_optional_float(data.get("started_ts")),
        updated_ts=_optional_float(data.get("updated_ts")),
        ended_ts=_optional_float(data.get("ended_ts"), allow_none=True),
        progress=_optional_float(data.get("progress"), allow_none=True),
        message=_optional_str(data.get("message")),
    )
    if record.started_ts <= 0:
        record.started_ts = record.updated_ts
    if record.updated_ts <= 0:
        record.updated_ts = record.started_ts
    return record


def _optional_str(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value, *, allow_none: bool = False) -> Optional[float]:
    if value is None:
        return None if allow_none else 0.0
    try:
        return float(value)
    except Exception:
        return None if allow_none else 0.0
