from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import socket
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from .events import CodeSeeEvent
from . import session_schema
from . import session_store

DEFAULT_KEYFRAME_EVERY_RECORDS = 25


@dataclass(frozen=True)
class SessionRecorderConfig:
    workspace_id: str
    max_sessions_per_workspace: int = session_store.DEFAULT_MAX_SESSIONS_PER_WORKSPACE
    max_total_mb_per_workspace: int = session_store.DEFAULT_MAX_TOTAL_MB_PER_WORKSPACE
    keyframe_every_records: int = DEFAULT_KEYFRAME_EVERY_RECORDS


@dataclass(frozen=True)
class SessionMeta:
    schema_version: int
    session_id: str
    workspace_id: str
    started_at_utc: str
    started_at_local: str
    started_at_ms_epoch: int
    tz_offset_minutes: int
    ended_at_utc: Optional[str]
    ended_at_local: Optional[str]
    ended_at_ms_epoch: Optional[int]
    status: str
    counts: Dict[str, int]
    build_info: Dict[str, Any]


class SessionRecorder:
    def __init__(
        self,
        config: SessionRecorderConfig,
        *,
        now_provider: Optional[Callable[[], float]] = None,
        snapshot_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        self._config = config
        self._now = now_provider or time.time
        self._snapshot_provider = snapshot_provider
        self._active = False
        self._session_id: Optional[str] = None
        self._session_root: Optional[Path] = None
        self._seq = 0
        self._keyframe_seq = 0
        self._counts = session_schema.default_counts()
        self._started_stamp: Optional[session_schema.SessionTimestamps] = None
        self._build_info: Dict[str, Any] = {}
        self._corrupt_lines = 0
        self._keyframe_every_records = max(1, int(config.keyframe_every_records))
        self._next_keyframe_at_record = self._keyframe_every_records

    def start_session(self, *, session_id: Optional[str] = None, build_info: Optional[Dict[str, Any]] = None) -> SessionMeta:
        if self._active:
            return self._session_meta(status=session_schema.SESSION_STATUS_ACTIVE)

        sid = session_store.sanitize_session_id(session_id or self._generate_session_id())
        self._session_id = sid
        self._session_root = session_store.ensure_session_layout(self._config.workspace_id, sid)
        self._seq = 0
        self._keyframe_seq = 0
        self._counts = session_schema.default_counts()
        self._build_info = dict(build_info or {})
        self._started_stamp = session_schema.capture_timestamps(self._now())
        self._corrupt_lines = 0
        self._next_keyframe_at_record = self._keyframe_every_records
        self._write_lock()
        self._active = True

        self._persist_meta(status=session_schema.SESSION_STATUS_ACTIVE)
        return self._session_meta(status=session_schema.SESSION_STATUS_ACTIVE)

    def stop_session(self, *, status: str = session_schema.SESSION_STATUS_COMPLETE) -> SessionMeta:
        if not self._active:
            if self._session_id and self._started_stamp:
                return self._session_meta(status=status)
            stamp = session_schema.capture_timestamps(self._now())
            return SessionMeta(
                schema_version=session_schema.SCHEMA_VERSION,
                session_id="",
                workspace_id=session_store.sanitize_workspace_id(self._config.workspace_id),
                started_at_utc=stamp.ts_utc,
                started_at_local=stamp.ts_local,
                started_at_ms_epoch=stamp.ts_ms_epoch,
                tz_offset_minutes=stamp.tz_offset_minutes,
                ended_at_utc=stamp.ts_utc,
                ended_at_local=stamp.ts_local,
                ended_at_ms_epoch=stamp.ts_ms_epoch,
                status=session_schema.SESSION_STATUS_INCOMPLETE,
                counts=session_schema.default_counts(),
                build_info=dict(self._build_info),
            )

        terminal = status if status in {
            session_schema.SESSION_STATUS_COMPLETE,
            session_schema.SESSION_STATUS_INCOMPLETE,
        } else session_schema.SESSION_STATUS_COMPLETE
        try:
            self.record_keyframe(self._capture_snapshot(), reason="session.stop")
        except Exception:
            pass
        self._persist_meta(status=terminal, include_end=True)
        self._remove_lock()
        self._active = False

        session_store.prune_sessions(
            self._config.workspace_id,
            max_sessions_per_workspace=self._config.max_sessions_per_workspace,
            max_total_mb_per_workspace=self._config.max_total_mb_per_workspace,
            active_session_id=None,
        )
        return self._session_meta(status=terminal)

    def record_event(self, event: CodeSeeEvent) -> None:
        if not self._active:
            return
        record = session_schema.build_event_record(seq=self._next_seq(), event=event, now=self._now())
        self._append_record(record)
        self._counts["events"] += 1

    def record_state_delta(self, delta: dict) -> None:
        if not self._active:
            return
        payload = dict(delta or {})
        record = session_schema.build_delta_record(
            seq=self._next_seq(),
            delta_type=str(payload.get("delta_type") or "state.delta"),
            node_id=payload.get("node_id"),
            before_ref=payload.get("before_ref"),
            after_ref=payload.get("after_ref"),
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else payload,
            now=self._now(),
        )
        self._append_record(record)
        self._counts["deltas"] += 1

    def record_keyframe(self, snapshot: dict, *, reason: str = "manual") -> None:
        if not self._active:
            return
        if not self._session_root:
            return
        payload_snapshot = dict(snapshot or {})
        self._keyframe_seq += 1
        keyframe_file = session_store.keyframe_path(self._session_root, self._keyframe_seq)
        payload = {
            "schema_version": session_schema.SCHEMA_VERSION,
            "keyframe_seq": self._keyframe_seq,
            "snapshot": payload_snapshot,
            "reason": str(reason or "manual"),
            **session_schema.capture_timestamps(self._now()).__dict__,
        }
        session_store.write_json(keyframe_file, payload)
        record = session_schema.build_keyframe_ref_record(
            seq=self._next_seq(),
            keyframe_seq=self._keyframe_seq,
            filename=keyframe_file.name,
            graph_state_ref=str(payload_snapshot.get("graph_state_ref") or ""),
            metadata={"path": str(keyframe_file), "reason": str(reason or "manual")},
            now=self._now(),
        )
        self._append_record(record, allow_auto_keyframe=False)
        self._counts["keyframes"] += 1

    def flush(self) -> None:
        if self._active:
            self._persist_meta(status=session_schema.SESSION_STATUS_ACTIVE)

    def is_active(self) -> bool:
        return self._active

    def session_dir(self) -> Optional[Path]:
        return self._session_root

    def _append_record(self, record: Dict[str, Any], *, allow_auto_keyframe: bool = True) -> None:
        if not self._session_root:
            return
        if not session_schema.validate_record(record):
            return
        session_store.append_jsonl(session_store.records_path(self._session_root), record)
        self._counts["records"] += 1
        if allow_auto_keyframe:
            self._maybe_record_cadence_keyframe(trigger_record_type=str(record.get("type") or ""))

    def _persist_meta(self, *, status: str, include_end: bool = False) -> None:
        if not self._session_root or not self._started_stamp or not self._session_id:
            return
        end_stamp = session_schema.capture_timestamps(self._now()) if include_end else None
        payload: Dict[str, Any] = {
            "schema_version": session_schema.SCHEMA_VERSION,
            "session_id": self._session_id,
            "workspace_id": session_store.sanitize_workspace_id(self._config.workspace_id),
            "started_at_utc": self._started_stamp.ts_utc,
            "started_at_local": self._started_stamp.ts_local,
            "started_at_ms_epoch": self._started_stamp.ts_ms_epoch,
            "tz_offset_minutes": self._started_stamp.tz_offset_minutes,
            "status": status,
            "counts": session_schema.merge_counts(self._counts, {"corrupt_lines": self._corrupt_lines}),
            "build_info": dict(self._build_info),
            "session_dir": str(self._session_root),
        }
        if end_stamp is not None:
            payload["ended_at_utc"] = end_stamp.ts_utc
            payload["ended_at_local"] = end_stamp.ts_local
            payload["ended_at_ms_epoch"] = end_stamp.ts_ms_epoch
        session_store.write_json(session_store.meta_path(self._session_root), payload)

    def _session_meta(self, *, status: str) -> SessionMeta:
        assert self._started_stamp is not None
        assert self._session_id is not None
        ended_utc: Optional[str] = None
        ended_local: Optional[str] = None
        ended_epoch: Optional[int] = None
        if status != session_schema.SESSION_STATUS_ACTIVE:
            end_stamp = session_schema.capture_timestamps(self._now())
            ended_utc = end_stamp.ts_utc
            ended_local = end_stamp.ts_local
            ended_epoch = end_stamp.ts_ms_epoch
        return SessionMeta(
            schema_version=session_schema.SCHEMA_VERSION,
            session_id=self._session_id,
            workspace_id=session_store.sanitize_workspace_id(self._config.workspace_id),
            started_at_utc=self._started_stamp.ts_utc,
            started_at_local=self._started_stamp.ts_local,
            started_at_ms_epoch=self._started_stamp.ts_ms_epoch,
            tz_offset_minutes=self._started_stamp.tz_offset_minutes,
            ended_at_utc=ended_utc,
            ended_at_local=ended_local,
            ended_at_ms_epoch=ended_epoch,
            status=status,
            counts=session_schema.merge_counts(self._counts, {"corrupt_lines": self._corrupt_lines}),
            build_info=dict(self._build_info),
        )

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _maybe_record_cadence_keyframe(self, *, trigger_record_type: str) -> None:
        if not self._active:
            return
        if trigger_record_type == session_schema.RECORD_KEYFRAME_REF:
            return
        while self._counts.get("records", 0) >= self._next_keyframe_at_record:
            self._next_keyframe_at_record += self._keyframe_every_records
            self.record_keyframe(self._capture_snapshot(), reason="cadence")

    def _capture_snapshot(self) -> Dict[str, Any]:
        if self._snapshot_provider is None:
            return {}
        try:
            snapshot = self._snapshot_provider()
        except Exception:
            return {}
        return dict(snapshot) if isinstance(snapshot, dict) else {}

    def _generate_session_id(self) -> str:
        stamp = session_schema.capture_timestamps(self._now())
        return f"{stamp.ts_ms_epoch}_{uuid4().hex[:8]}"

    def _write_lock(self) -> None:
        if not self._session_root or not self._started_stamp:
            return
        payload = {
            "pid": int(os.getpid()),
            "host": socket.gethostname(),
            "started_at_ms_epoch": self._started_stamp.ts_ms_epoch,
            "started_at_utc": self._started_stamp.ts_utc,
            "workspace_id": session_store.sanitize_workspace_id(self._config.workspace_id),
            "session_id": self._session_id,
        }
        session_store.write_json(session_store.lock_path(self._session_root), payload)

    def _remove_lock(self) -> None:
        if not self._session_root:
            return
        path = session_store.lock_path(self._session_root)
        try:
            if path.exists():
                path.unlink()
        except Exception:
            return


def reconstruct_terminal_state(session_root: Path) -> Dict[str, Any]:
    root = Path(session_root)
    rows, corrupt_lines = session_store.read_jsonl(session_store.records_path(root))
    ordered_rows = sorted(
        [
            row
            for row in rows
            if isinstance(row, dict)
            and isinstance(row.get("seq"), int)
            and int(row.get("seq") or 0) > 0
            and isinstance(row.get("type"), str)
        ],
        key=lambda row: int(row.get("seq") or 0),
    )

    monitor_state: Dict[str, Dict[str, Any]] = {}
    trace_state: Dict[str, Any] = _empty_trace_state()
    warnings: List[str] = []
    base_keyframe_seq: Optional[int] = None
    base_keyframe_record_seq = 0

    keyframe_rows = [
        row for row in ordered_rows
        if str(row.get("type") or "") == session_schema.RECORD_KEYFRAME_REF
    ]
    for row in reversed(keyframe_rows):
        keyframe_payload = _load_keyframe_payload(root, row)
        if keyframe_payload is None:
            warnings.append(
                f"keyframe load failed for seq={int(row.get('seq') or 0)} "
                f"file={str(row.get('filename') or '')}"
            )
            continue
        snapshot = keyframe_payload.get("snapshot")
        if not isinstance(snapshot, dict):
            warnings.append(f"keyframe snapshot missing for seq={int(row.get('seq') or 0)}")
            continue
        monitor_state, trace_state = _state_from_snapshot(snapshot)
        base_keyframe_seq = int(row.get("keyframe_seq") or 0) or None
        base_keyframe_record_seq = int(row.get("seq") or 0)
        break

    applied_records = 0
    for row in ordered_rows:
        seq = int(row.get("seq") or 0)
        if seq <= base_keyframe_record_seq:
            continue
        applied_records += 1
        record_type = str(row.get("type") or "")
        if record_type == session_schema.RECORD_KEYFRAME_REF:
            keyframe_payload = _load_keyframe_payload(root, row)
            if keyframe_payload is None:
                warnings.append(
                    f"keyframe load failed for seq={seq} "
                    f"file={str(row.get('filename') or '')}"
                )
                continue
            snapshot = keyframe_payload.get("snapshot")
            if not isinstance(snapshot, dict):
                warnings.append(f"keyframe snapshot missing for seq={seq}")
                continue
            monitor_state, trace_state = _state_from_snapshot(snapshot)
            base_keyframe_seq = int(row.get("keyframe_seq") or 0) or base_keyframe_seq
            base_keyframe_record_seq = seq
            continue
        if record_type == session_schema.RECORD_DELTA:
            _apply_delta(row, monitor_state=monitor_state, trace_state=trace_state)

    return {
        "monitor_state": monitor_state,
        "trace_state": trace_state,
        "base_keyframe_seq": base_keyframe_seq,
        "base_keyframe_record_seq": int(base_keyframe_record_seq),
        "applied_records": int(applied_records),
        "corrupt_lines": int(corrupt_lines),
        "warnings": warnings,
    }


def _load_keyframe_payload(root: Path, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    filename = str(record.get("filename") or "").strip()
    metadata = record.get("metadata")
    path_from_meta = str(metadata.get("path") or "").strip() if isinstance(metadata, dict) else ""

    candidates: List[Path] = []
    if filename:
        candidates.append(root / "keyframes" / filename)
    if path_from_meta:
        candidates.append(Path(path_from_meta))

    for candidate in candidates:
        payload = session_store.read_json(candidate)
        if isinstance(payload, dict):
            return payload
    return None


def _state_from_snapshot(snapshot: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    monitor_state = _normalize_monitor_state(snapshot.get("monitor_state"))
    trace_state = _normalize_trace_state(snapshot.get("trace_state"))
    return monitor_state, trace_state


def _normalize_monitor_state(raw: Any) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(raw, dict):
        return out
    for node_id, item in raw.items():
        key = str(node_id).strip()
        if not key:
            continue
        if isinstance(item, dict):
            out[key] = {
                "state": str(item.get("state") or "INACTIVE"),
                "active": bool(item.get("active", False)),
                "stuck": bool(item.get("stuck", False)),
                "fatal": bool(item.get("fatal", False)),
                "error_count": _safe_int(item.get("error_count")),
                "active_span_count": _safe_int(item.get("active_span_count")),
                "latched_count": _safe_int(item.get("latched_count")),
                "last_change_ts": _safe_float(item.get("last_change_ts")),
            }
            continue
        out[key] = {
            "state": str(item or "INACTIVE"),
            "active": False,
            "stuck": False,
            "fatal": False,
            "error_count": 0,
            "active_span_count": 0,
            "latched_count": 0,
            "last_change_ts": 0.0,
        }
    return out


def _normalize_trace_state(raw: Any) -> Dict[str, Any]:
    out = _empty_trace_state()
    if not isinstance(raw, dict):
        return out
    active_trace_id = raw.get("active_trace_id")
    if active_trace_id not in (None, "", "none"):
        out["active_trace_id"] = str(active_trace_id)
    edges = _normalize_trace_edges(raw.get("edges"))
    nodes = _normalize_trace_nodes(raw.get("nodes"))
    if edges:
        out["edges"] = edges
    if nodes:
        out["nodes"] = nodes
    if edges:
        out["edge_count"] = len(edges)
    else:
        out["edge_count"] = _safe_int(raw.get("edge_count"))
    if nodes:
        out["node_count"] = len(nodes)
    else:
        out["node_count"] = _safe_int(raw.get("node_count"))
    return out


def _apply_delta(
    row: Dict[str, Any],
    *,
    monitor_state: Dict[str, Dict[str, Any]],
    trace_state: Dict[str, Any],
) -> None:
    delta_type = str(row.get("delta_type") or "")
    metadata = row.get("metadata")
    metadata_dict = metadata if isinstance(metadata, dict) else {}

    if delta_type == "monitor.state.transition":
        node_id = str(row.get("node_id") or "").strip()
        if not node_id:
            return
        state = dict(monitor_state.get(node_id) or _default_monitor_entry())
        after = metadata_dict.get("after")
        after_state = str(row.get("after_ref") or "").strip()
        if isinstance(after, dict):
            state["state"] = str(after.get("state") or after_state or state.get("state") or "INACTIVE")
            if "active" in after:
                state["active"] = bool(after.get("active"))
            if "stuck" in after:
                state["stuck"] = bool(after.get("stuck"))
            if "fatal" in after:
                state["fatal"] = bool(after.get("fatal"))
            if "error_count" in after:
                state["error_count"] = _safe_int(after.get("error_count"))
            if "active_span_count" in after:
                state["active_span_count"] = _safe_int(after.get("active_span_count"))
            if "latched_count" in after:
                state["latched_count"] = _safe_int(after.get("latched_count"))
            if "last_change_ts" in after:
                state["last_change_ts"] = _safe_float(after.get("last_change_ts"))
        elif after_state:
            state["state"] = after_state
        monitor_state[node_id] = state
        return

    if delta_type == "trace.state.transition":
        after = metadata_dict.get("after")
        after_ref = str(row.get("after_ref") or "").strip()
        if isinstance(after, dict):
            trace_id = after.get("active_trace_id")
            trace_state["active_trace_id"] = _normalize_trace_id(trace_id)
            if "edge_count" in after:
                trace_state["edge_count"] = _safe_int(after.get("edge_count"))
            if "node_count" in after:
                trace_state["node_count"] = _safe_int(after.get("node_count"))
            edges = _normalize_trace_edges(after.get("edges"))
            nodes = _normalize_trace_nodes(after.get("nodes"))
            if edges:
                trace_state["edges"] = edges
                trace_state["edge_count"] = len(edges)
            if nodes:
                trace_state["nodes"] = nodes
                trace_state["node_count"] = len(nodes)
            return
        trace_state["active_trace_id"] = _normalize_trace_id(after_ref)


def _default_monitor_entry() -> Dict[str, Any]:
    return {
        "state": "INACTIVE",
        "active": False,
        "stuck": False,
        "fatal": False,
        "error_count": 0,
        "active_span_count": 0,
        "latched_count": 0,
        "last_change_ts": 0.0,
    }


def _normalize_trace_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", "none", "None"):
        return None
    return text


def _normalize_trace_edges(raw: Any) -> List[Tuple[str, str]]:
    if not isinstance(raw, list):
        return []
    out: List[Tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        src = str(item[0]).strip()
        dst = str(item[1]).strip()
        if not src or not dst:
            continue
        out.append((src, dst))
    return out


def _normalize_trace_nodes(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    seen = set()
    for item in raw:
        node_id = str(item).strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        out.append(node_id)
    out.sort()
    return out


def _empty_trace_state() -> Dict[str, Any]:
    return {
        "active_trace_id": None,
        "edges": [],
        "nodes": [],
        "edge_count": 0,
        "node_count": 0,
    }


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0
