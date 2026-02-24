from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import socket
import time
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from .events import CodeSeeEvent
from . import session_schema
from . import session_store


@dataclass(frozen=True)
class SessionRecorderConfig:
    workspace_id: str
    max_sessions_per_workspace: int = session_store.DEFAULT_MAX_SESSIONS_PER_WORKSPACE
    max_total_mb_per_workspace: int = session_store.DEFAULT_MAX_TOTAL_MB_PER_WORKSPACE


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
    ) -> None:
        self._config = config
        self._now = now_provider or time.time
        self._active = False
        self._session_id: Optional[str] = None
        self._session_root: Optional[Path] = None
        self._seq = 0
        self._keyframe_seq = 0
        self._counts = session_schema.default_counts()
        self._started_stamp: Optional[session_schema.SessionTimestamps] = None
        self._build_info: Dict[str, Any] = {}
        self._corrupt_lines = 0

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

    def record_keyframe(self, snapshot: dict) -> None:
        if not self._active:
            return
        if not self._session_root:
            return
        self._keyframe_seq += 1
        keyframe_file = session_store.keyframe_path(self._session_root, self._keyframe_seq)
        payload = {
            "schema_version": session_schema.SCHEMA_VERSION,
            "keyframe_seq": self._keyframe_seq,
            "snapshot": dict(snapshot or {}),
            **session_schema.capture_timestamps(self._now()).__dict__,
        }
        session_store.write_json(keyframe_file, payload)
        record = session_schema.build_keyframe_ref_record(
            seq=self._next_seq(),
            keyframe_seq=self._keyframe_seq,
            filename=keyframe_file.name,
            graph_state_ref=str((snapshot or {}).get("graph_state_ref") or ""),
            metadata={"path": str(keyframe_file)},
            now=self._now(),
        )
        self._append_record(record)
        self._counts["keyframes"] += 1

    def flush(self) -> None:
        if self._active:
            self._persist_meta(status=session_schema.SESSION_STATUS_ACTIVE)

    def is_active(self) -> bool:
        return self._active

    def session_dir(self) -> Optional[Path]:
        return self._session_root

    def _append_record(self, record: Dict[str, Any]) -> None:
        if not self._session_root:
            return
        if not session_schema.validate_record(record):
            return
        session_store.append_jsonl(session_store.records_path(self._session_root), record)
        self._counts["records"] += 1

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
