from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import time
from typing import Any, Dict, Iterable, Optional

from .events import CodeSeeEvent

SCHEMA_VERSION = 1

RECORD_EVENT = "event"
RECORD_DELTA = "delta"
RECORD_KEYFRAME_REF = "keyframe_ref"

SESSION_STATUS_ACTIVE = "ACTIVE"
SESSION_STATUS_COMPLETE = "COMPLETE"
SESSION_STATUS_INCOMPLETE = "INCOMPLETE"

_RECORD_TYPES = {RECORD_EVENT, RECORD_DELTA, RECORD_KEYFRAME_REF}
_SESSION_STATUSES = {SESSION_STATUS_ACTIVE, SESSION_STATUS_COMPLETE, SESSION_STATUS_INCOMPLETE}


@dataclass(frozen=True)
class SessionTimestamps:
    ts_utc: str
    ts_ms_epoch: int
    tz_offset_minutes: int
    ts_local: str


def capture_timestamps(now: Optional[float] = None) -> SessionTimestamps:
    ts = float(now if now is not None else time.time())
    epoch_ms = int(round(ts * 1000.0))
    local_dt = datetime.fromtimestamp(ts).astimezone()
    utc_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    offset = local_dt.utcoffset() or local_dt.utcoffset()
    offset_minutes = int((offset.total_seconds() if offset else 0.0) / 60.0)
    return SessionTimestamps(
        ts_utc=utc_dt.isoformat().replace("+00:00", "Z"),
        ts_ms_epoch=epoch_ms,
        tz_offset_minutes=offset_minutes,
        ts_local=local_dt.strftime("%Y-%m-%d %H:%M:%S"),
    )


def build_event_record(*, seq: int, event: CodeSeeEvent, now: Optional[float] = None) -> Dict[str, Any]:
    stamp = capture_timestamps(now)
    return {
        "seq": int(seq),
        "type": RECORD_EVENT,
        **asdict(stamp),
        "kind": str(event.kind),
        "severity": str(event.severity),
        "message": str(event.message),
        "node_ids": [str(node_id) for node_id in list(event.node_ids or [])],
        "source_node_id": _optional_text(event.source_node_id),
        "target_node_id": _optional_text(event.target_node_id),
        "payload": _payload_or_none(event.payload),
    }


def build_delta_record(
    *,
    seq: int,
    delta_type: str,
    node_id: Optional[str] = None,
    before_ref: Optional[str] = None,
    after_ref: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    stamp = capture_timestamps(now)
    return {
        "seq": int(seq),
        "type": RECORD_DELTA,
        **asdict(stamp),
        "delta_type": str(delta_type or "unknown"),
        "node_id": _optional_text(node_id),
        "before_ref": _optional_text(before_ref),
        "after_ref": _optional_text(after_ref),
        "metadata": dict(metadata or {}),
    }


def build_keyframe_ref_record(
    *,
    seq: int,
    keyframe_seq: int,
    filename: str,
    graph_state_ref: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    stamp = capture_timestamps(now)
    return {
        "seq": int(seq),
        "type": RECORD_KEYFRAME_REF,
        **asdict(stamp),
        "keyframe_seq": int(keyframe_seq),
        "filename": str(filename),
        "graph_state_ref": _optional_text(graph_state_ref),
        "metadata": dict(metadata or {}),
    }


def validate_record(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if not _is_positive_int(data.get("seq")):
        return False
    record_type = data.get("type")
    if record_type not in _RECORD_TYPES:
        return False
    if not _is_text(data.get("ts_utc")):
        return False
    if not isinstance(data.get("ts_ms_epoch"), int):
        return False
    if not isinstance(data.get("tz_offset_minutes"), int):
        return False
    if not _is_text(data.get("ts_local")):
        return False

    if record_type == RECORD_EVENT:
        return _is_text(data.get("kind")) and _is_text(data.get("severity")) and _is_text(data.get("message"))
    if record_type == RECORD_DELTA:
        return _is_text(data.get("delta_type")) and isinstance(data.get("metadata"), dict)
    if record_type == RECORD_KEYFRAME_REF:
        return _is_positive_int(data.get("keyframe_seq")) and _is_text(data.get("filename"))
    return False


def validate_session_meta(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    required_text = [
        "session_id",
        "workspace_id",
        "started_at_utc",
        "started_at_local",
    ]
    for key in required_text:
        if not _is_text(data.get(key)):
            return False
    if data.get("schema_version") != SCHEMA_VERSION:
        return False
    if data.get("status") not in _SESSION_STATUSES:
        return False
    if not isinstance(data.get("started_at_ms_epoch"), int):
        return False
    if not isinstance(data.get("tz_offset_minutes"), int):
        return False
    counts = data.get("counts")
    if not isinstance(counts, dict):
        return False
    for key in ("records", "events", "deltas", "keyframes", "corrupt_lines"):
        value = counts.get(key)
        if not isinstance(value, int) or value < 0:
            return False
    return True


def default_counts() -> Dict[str, int]:
    return {
        "records": 0,
        "events": 0,
        "deltas": 0,
        "keyframes": 0,
        "corrupt_lines": 0,
    }


def merge_counts(base: Dict[str, int], updates: Dict[str, int]) -> Dict[str, int]:
    out = dict(base)
    for key, value in updates.items():
        try:
            out[key] = max(0, int(value))
        except Exception:
            continue
    return out


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and value > 0


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _payload_or_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
