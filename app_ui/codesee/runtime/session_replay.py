from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import session_schema
from . import session_store


@dataclass(frozen=True)
class ReplayFrame:
    seq: int
    ts_ms_epoch: int
    ts_utc: str
    ts_local: str
    record_type: str
    record: Dict[str, Any]
    keyframe_seq: Optional[int] = None
    keyframe_file: Optional[str] = None


@dataclass(frozen=True)
class ReplayTimeline:
    session_root: Path
    schema_version: int
    session_id: str
    workspace_id: str
    status: str
    started_at_ms_epoch: int
    ended_at_ms_epoch: Optional[int]
    frames: List[ReplayFrame]
    keyframes: Dict[int, Dict[str, Any]]
    keyframe_payload_by_record_seq: Dict[int, Dict[str, Any]]
    seq_index: Dict[int, ReplayFrame]
    ordered_seqs: List[int]
    ts_index: List[Tuple[int, int]]
    corrupt_lines: int
    warnings: List[str]
    meta: Dict[str, Any]


@dataclass(frozen=True)
class ReplaySeekResult:
    requested_seq: int
    resolved_seq: int
    base_keyframe_seq: Optional[int]
    base_keyframe_record_seq: int
    applied_records: int
    monitor_state: Dict[str, Dict[str, Any]]
    trace_state: Dict[str, Any]
    warnings: List[str]


REPLAY_SPEED_PRESETS: Tuple[float, ...] = (0.25, 0.5, 1.0, 1.5, 2.0, 4.0)
DEFAULT_REPLAY_JUMP_SECONDS = 5


@dataclass(frozen=True)
class ReplayControllerSnapshot:
    is_playing: bool
    speed_multiplier: float
    current_seq: int
    current_ts_ms_epoch: int
    jump_seconds: int


def load_replay_session(session_root: Path) -> ReplayTimeline:
    root = Path(session_root)
    warnings: List[str] = []

    meta = _normalize_meta(
        session_store.read_json(session_store.meta_path(root)),
        root=root,
        warnings=warnings,
    )

    rows, corrupt_lines = session_store.read_jsonl(session_store.records_path(root))
    frames_raw: List[ReplayFrame] = []
    for index, row in enumerate(rows):
        frame = _normalize_frame(row, index=index, warnings=warnings)
        if frame is None:
            continue
        frames_raw.append(frame)

    frames_sorted = sorted(frames_raw, key=lambda item: (int(item.seq), int(item.ts_ms_epoch)))

    frames: List[ReplayFrame] = []
    seq_index: Dict[int, ReplayFrame] = {}
    for frame in frames_sorted:
        if frame.seq in seq_index:
            warnings.append(f"duplicate seq skipped: seq={frame.seq}")
            continue
        seq_index[frame.seq] = frame
        frames.append(frame)

    keyframes: Dict[int, Dict[str, Any]] = {}
    keyframe_payload_by_record_seq: Dict[int, Dict[str, Any]] = {}
    for frame in frames:
        if frame.record_type != session_schema.RECORD_KEYFRAME_REF:
            continue
        payload = _load_keyframe_payload(root=root, frame=frame, warnings=warnings)
        if payload is None or frame.keyframe_seq is None:
            continue
        keyframes[int(frame.keyframe_seq)] = payload
        keyframe_payload_by_record_seq[int(frame.seq)] = payload

    if corrupt_lines > 0:
        warnings.append(f"records corrupt_lines={int(corrupt_lines)}")

    counts = meta.get("counts") if isinstance(meta.get("counts"), dict) else session_schema.default_counts()
    counts["corrupt_lines"] = max(_safe_int(counts.get("corrupt_lines")), int(corrupt_lines))
    meta["counts"] = counts

    ordered_seqs = [int(frame.seq) for frame in frames]
    ts_index = sorted((int(frame.ts_ms_epoch), int(frame.seq)) for frame in frames)

    return ReplayTimeline(
        session_root=root,
        schema_version=_safe_int(meta.get("schema_version")) or session_schema.SCHEMA_VERSION,
        session_id=str(meta.get("session_id") or session_store.sanitize_session_id(root.name)),
        workspace_id=str(meta.get("workspace_id") or _infer_workspace_id(root)),
        status=str(meta.get("status") or session_schema.SESSION_STATUS_INCOMPLETE),
        started_at_ms_epoch=_safe_int(meta.get("started_at_ms_epoch")),
        ended_at_ms_epoch=_optional_int(meta.get("ended_at_ms_epoch")),
        frames=frames,
        keyframes=keyframes,
        keyframe_payload_by_record_seq=keyframe_payload_by_record_seq,
        seq_index=seq_index,
        ordered_seqs=ordered_seqs,
        ts_index=ts_index,
        corrupt_lines=int(corrupt_lines),
        warnings=warnings,
        meta=meta,
    )


def nearest_seq_for_timestamp(timeline: ReplayTimeline, ts_ms_epoch: int) -> Optional[int]:
    if not timeline.ts_index:
        return None
    target = _safe_int(ts_ms_epoch)
    ts_value, seq = min(
        timeline.ts_index,
        key=lambda item: (abs(int(item[0]) - target), int(item[1])),
    )
    del ts_value
    return int(seq)


def floor_seq_for_timestamp(timeline: ReplayTimeline, ts_ms_epoch: int) -> Optional[int]:
    if not timeline.ts_index:
        return None
    target = _safe_int(ts_ms_epoch)
    first_ts, first_seq = timeline.ts_index[0]
    if target <= int(first_ts):
        return int(first_seq)
    candidate_seq = int(first_seq)
    for ts_value, seq in timeline.ts_index:
        if int(ts_value) > target:
            break
        candidate_seq = int(seq)
    return candidate_seq


def seek_to_seq(timeline: ReplayTimeline, target_seq: int) -> ReplaySeekResult:
    requested = _safe_int(target_seq)
    base_warnings = list(timeline.warnings)

    if not timeline.ordered_seqs:
        warnings = base_warnings + ["seek skipped: timeline is empty"]
        return ReplaySeekResult(
            requested_seq=requested,
            resolved_seq=0,
            base_keyframe_seq=None,
            base_keyframe_record_seq=0,
            applied_records=0,
            monitor_state={},
            trace_state=_empty_trace_state(),
            warnings=warnings,
        )

    resolved = _resolve_target_seq(timeline.ordered_seqs, requested)

    monitor_state: Dict[str, Dict[str, Any]] = {}
    trace_state: Dict[str, Any] = _empty_trace_state()
    warnings: List[str] = []
    base_keyframe_seq: Optional[int] = None
    base_keyframe_record_seq = 0

    keyframe_record_candidates = [
        seq for seq in timeline.ordered_seqs
        if seq <= resolved and seq in timeline.keyframe_payload_by_record_seq
    ]

    for keyframe_record_seq in reversed(keyframe_record_candidates):
        payload = timeline.keyframe_payload_by_record_seq.get(keyframe_record_seq)
        if not isinstance(payload, dict):
            warnings.append(f"keyframe payload missing for record_seq={keyframe_record_seq}")
            continue
        snapshot = payload.get("snapshot")
        if not isinstance(snapshot, dict):
            warnings.append(f"keyframe snapshot missing for record_seq={keyframe_record_seq}")
            continue
        monitor_state, trace_state = _state_from_snapshot(snapshot)
        frame = timeline.seq_index.get(keyframe_record_seq)
        base_keyframe_seq = frame.keyframe_seq if frame else None
        base_keyframe_record_seq = int(keyframe_record_seq)
        break

    applied_records = 0
    for seq in timeline.ordered_seqs:
        if seq <= base_keyframe_record_seq or seq > resolved:
            continue
        frame = timeline.seq_index.get(seq)
        if frame is None:
            continue

        applied_records += 1

        if frame.record_type == session_schema.RECORD_KEYFRAME_REF:
            payload = timeline.keyframe_payload_by_record_seq.get(seq)
            if not isinstance(payload, dict):
                warnings.append(
                    f"keyframe load failed for seq={seq} file={str(frame.keyframe_file or '')}"
                )
                continue
            snapshot = payload.get("snapshot")
            if not isinstance(snapshot, dict):
                warnings.append(f"keyframe snapshot missing for seq={seq}")
                continue
            monitor_state, trace_state = _state_from_snapshot(snapshot)
            base_keyframe_record_seq = int(seq)
            if frame.keyframe_seq is not None:
                base_keyframe_seq = int(frame.keyframe_seq)
            continue

        if frame.record_type == session_schema.RECORD_DELTA:
            _apply_delta(
                frame.record,
                monitor_state=monitor_state,
                trace_state=trace_state,
            )

    return ReplaySeekResult(
        requested_seq=requested,
        resolved_seq=resolved,
        base_keyframe_seq=base_keyframe_seq,
        base_keyframe_record_seq=int(base_keyframe_record_seq),
        applied_records=int(applied_records),
        monitor_state=monitor_state,
        trace_state=trace_state,
        warnings=base_warnings + warnings,
    )


class ReplayController:
    def __init__(
        self,
        timeline: ReplayTimeline,
        *,
        speed_multiplier: float = 1.0,
        jump_seconds: int = DEFAULT_REPLAY_JUMP_SECONDS,
    ) -> None:
        self.timeline = timeline
        self._speed_multiplier = _normalize_speed_preset(speed_multiplier)
        self._jump_seconds = _normalize_jump_seconds(jump_seconds)
        self._is_playing = False

        if timeline.ordered_seqs:
            initial_seq = int(timeline.ordered_seqs[0])
            initial_frame = timeline.seq_index.get(initial_seq)
            self._current_seq = initial_seq
            if initial_frame is not None:
                self._current_ts_ms_epoch = int(initial_frame.ts_ms_epoch)
            else:
                self._current_ts_ms_epoch = int(timeline.ts_index[0][0])
        else:
            self._current_seq = 0
            self._current_ts_ms_epoch = 0
        self._playhead_ts_ms_epoch = int(self._current_ts_ms_epoch)

        self._last_seek_result = seek_to_seq(self.timeline, self._current_seq)

    @property
    def speed_presets(self) -> Tuple[float, ...]:
        return REPLAY_SPEED_PRESETS

    @property
    def snapshot(self) -> ReplayControllerSnapshot:
        return ReplayControllerSnapshot(
            is_playing=bool(self._is_playing),
            speed_multiplier=float(self._speed_multiplier),
            current_seq=int(self._current_seq),
            current_ts_ms_epoch=int(self._current_ts_ms_epoch),
            jump_seconds=int(self._jump_seconds),
        )

    @property
    def current_seek_result(self) -> ReplaySeekResult:
        return self._last_seek_result

    def play(self) -> ReplaySeekResult:
        if not self.timeline.ordered_seqs:
            self._is_playing = False
            return self._last_seek_result
        first_seq = int(self.timeline.ordered_seqs[0])
        last_seq = int(self.timeline.ordered_seqs[-1])
        if self._current_seq >= last_seq:
            self.scrub_to_seq(first_seq)
        self._is_playing = True
        return self._last_seek_result

    def pause(self) -> ReplaySeekResult:
        self._is_playing = False
        return self._last_seek_result

    def set_speed(self, multiplier: float) -> float:
        self._speed_multiplier = _normalize_speed_preset(multiplier)
        return self._speed_multiplier

    def set_jump_seconds(self, seconds: int) -> int:
        self._jump_seconds = _normalize_jump_seconds(seconds)
        return self._jump_seconds

    def scrub_to_seq(self, target_seq: int) -> ReplaySeekResult:
        result = seek_to_seq(self.timeline, target_seq)
        self._last_seek_result = result
        self._sync_playhead_from_seq(result.resolved_seq)
        return result

    def scrub_to_timestamp(self, ts_ms_epoch: int) -> ReplaySeekResult:
        seq = nearest_seq_for_timestamp(self.timeline, ts_ms_epoch)
        if seq is None:
            return self.scrub_to_seq(0)
        return self.scrub_to_seq(seq)

    def jump_seconds(self, delta_seconds: int) -> ReplaySeekResult:
        try:
            delta = int(delta_seconds)
        except Exception:
            delta = 0
        if delta == 0:
            return self._last_seek_result
        target_ts = int(self._current_ts_ms_epoch) + int(delta) * 1000
        return self.scrub_to_timestamp(target_ts)

    def jump_forward(self, seconds: Optional[int] = None) -> ReplaySeekResult:
        step = self._jump_seconds if seconds is None else _normalize_jump_seconds(seconds)
        return self.jump_seconds(step)

    def jump_backward(self, seconds: Optional[int] = None) -> ReplaySeekResult:
        step = self._jump_seconds if seconds is None else _normalize_jump_seconds(seconds)
        return self.jump_seconds(-step)

    def tick(self, elapsed_ms: int) -> ReplaySeekResult:
        if not self._is_playing or not self.timeline.ordered_seqs:
            return self._last_seek_result
        elapsed = _safe_int(elapsed_ms)
        if elapsed <= 0:
            return self._last_seek_result
        advance_ms = _scale_elapsed_ms(elapsed, self._speed_multiplier)
        if advance_ms <= 0:
            return self._last_seek_result
        last_ts = int(self.timeline.ts_index[-1][0]) if self.timeline.ts_index else int(self._playhead_ts_ms_epoch)
        target_ts = min(last_ts, int(self._playhead_ts_ms_epoch) + int(advance_ms))
        seq = floor_seq_for_timestamp(self.timeline, target_ts)
        if seq is None:
            return self._last_seek_result
        result = seek_to_seq(self.timeline, seq)
        self._last_seek_result = result
        self._current_seq = int(result.resolved_seq)
        self._playhead_ts_ms_epoch = int(target_ts)
        self._current_ts_ms_epoch = int(target_ts)
        if result.resolved_seq >= int(self.timeline.ordered_seqs[-1]):
            self._is_playing = False
        return result

    def _sync_playhead_from_seq(self, seq: int) -> None:
        self._current_seq = int(seq)
        frame = self.timeline.seq_index.get(self._current_seq)
        if frame is not None:
            self._current_ts_ms_epoch = int(frame.ts_ms_epoch)
            self._playhead_ts_ms_epoch = int(self._current_ts_ms_epoch)
            return
        if self.timeline.ts_index:
            self._current_ts_ms_epoch = int(self.timeline.ts_index[-1][0])
            self._playhead_ts_ms_epoch = int(self._current_ts_ms_epoch)
            return
        self._current_ts_ms_epoch = 0
        self._playhead_ts_ms_epoch = 0


def _normalize_meta(
    raw_meta: Optional[Dict[str, Any]],
    *,
    root: Path,
    warnings: List[str],
) -> Dict[str, Any]:
    inferred_workspace = _infer_workspace_id(root)
    inferred_session = session_store.sanitize_session_id(root.name)

    if raw_meta is None:
        warnings.append("session_meta missing; using defaults")
    elif not session_schema.validate_session_meta(raw_meta):
        warnings.append("session_meta invalid/partial; normalized for replay")

    meta = dict(raw_meta or {})
    status = str(meta.get("status") or session_schema.SESSION_STATUS_INCOMPLETE)
    if status not in {
        session_schema.SESSION_STATUS_ACTIVE,
        session_schema.SESSION_STATUS_COMPLETE,
        session_schema.SESSION_STATUS_INCOMPLETE,
    }:
        status = session_schema.SESSION_STATUS_INCOMPLETE

    normalized: Dict[str, Any] = {
        "schema_version": _safe_int(meta.get("schema_version")) or session_schema.SCHEMA_VERSION,
        "session_id": str(meta.get("session_id") or inferred_session),
        "workspace_id": str(meta.get("workspace_id") or inferred_workspace),
        "status": status,
        "started_at_ms_epoch": _safe_int(meta.get("started_at_ms_epoch")),
        "ended_at_ms_epoch": _optional_int(meta.get("ended_at_ms_epoch")),
        "counts": _normalize_counts(meta.get("counts")),
    }

    for key in (
        "started_at_utc",
        "started_at_local",
        "ended_at_utc",
        "ended_at_local",
        "tz_offset_minutes",
        "build_info",
    ):
        if key in meta:
            normalized[key] = meta.get(key)

    return normalized


def _normalize_frame(
    raw: Any,
    *,
    index: int,
    warnings: List[str],
) -> Optional[ReplayFrame]:
    if not isinstance(raw, dict):
        warnings.append(f"record[{index}] skipped: not an object")
        return None

    seq = _safe_int(raw.get("seq"))
    if seq <= 0:
        warnings.append(f"record[{index}] skipped: invalid seq")
        return None

    record_type = str(raw.get("type") or "").strip()
    if not record_type:
        warnings.append(f"record[{index}] skipped: missing type")
        return None

    keyframe_seq: Optional[int] = None
    keyframe_file: Optional[str] = None
    if record_type == session_schema.RECORD_KEYFRAME_REF:
        keyframe_seq = _positive_optional_int(raw.get("keyframe_seq"))
        keyframe_file = str(raw.get("filename") or "").strip() or None
        if keyframe_seq is None:
            warnings.append(f"record[{index}] keyframe_ref missing keyframe_seq")
        if keyframe_file is None:
            warnings.append(f"record[{index}] keyframe_ref missing filename")

    return ReplayFrame(
        seq=seq,
        ts_ms_epoch=_safe_int(raw.get("ts_ms_epoch")),
        ts_utc=str(raw.get("ts_utc") or ""),
        ts_local=str(raw.get("ts_local") or ""),
        record_type=record_type,
        record=dict(raw),
        keyframe_seq=keyframe_seq,
        keyframe_file=keyframe_file,
    )


def _load_keyframe_payload(
    *,
    root: Path,
    frame: ReplayFrame,
    warnings: List[str],
) -> Optional[Dict[str, Any]]:
    candidates: List[Path] = []

    if frame.keyframe_file:
        candidates.append(root / "keyframes" / frame.keyframe_file)

    metadata = frame.record.get("metadata")
    if isinstance(metadata, dict):
        raw_path = str(metadata.get("path") or "").strip()
        if raw_path:
            path_obj = Path(raw_path)
            if path_obj.is_absolute():
                candidates.append(path_obj)
            else:
                candidates.append(root / path_obj)

    seen: set[str] = set()
    deduped: List[Path] = []
    for candidate in candidates:
        marker = str(candidate)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(candidate)

    for candidate in deduped:
        payload = session_store.read_json(candidate)
        if payload is not None:
            return payload

    warnings.append(
        f"keyframe load failed for seq={frame.seq} "
        f"file={str(frame.keyframe_file or '')}"
    )
    return None


def _resolve_target_seq(ordered_seqs: List[int], requested_seq: int) -> int:
    if not ordered_seqs:
        return 0
    requested = _safe_int(requested_seq)
    if requested <= ordered_seqs[0]:
        return int(ordered_seqs[0])
    if requested >= ordered_seqs[-1]:
        return int(ordered_seqs[-1])
    for seq in reversed(ordered_seqs):
        if int(seq) <= requested:
            return int(seq)
    return int(ordered_seqs[0])


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


def _normalize_counts(raw_counts: Any) -> Dict[str, int]:
    out = session_schema.default_counts()
    if not isinstance(raw_counts, dict):
        return out
    for key in out:
        out[key] = _safe_int(raw_counts.get(key))
    return out


def _infer_workspace_id(root: Path) -> str:
    parts = list(root.parts)
    for index, part in enumerate(parts):
        if str(part).lower() != "workspaces":
            continue
        if index + 1 < len(parts):
            return session_store.sanitize_workspace_id(str(parts[index + 1]))
        break
    return "default"


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


def _normalize_speed_preset(multiplier: float) -> float:
    try:
        value = float(multiplier)
    except Exception as exc:
        raise ValueError("speed multiplier must be numeric") from exc
    for preset in REPLAY_SPEED_PRESETS:
        if abs(float(preset) - value) < 1e-9:
            return float(preset)
    raise ValueError(f"unsupported replay speed: {multiplier}; expected one of {REPLAY_SPEED_PRESETS}")


def _normalize_jump_seconds(seconds: int) -> int:
    try:
        parsed = int(seconds)
    except Exception as exc:
        raise ValueError("jump seconds must be an integer") from exc
    if parsed <= 0:
        raise ValueError("jump seconds must be > 0")
    return parsed


def _speed_ratio(multiplier: float) -> Tuple[int, int]:
    speed = _normalize_speed_preset(multiplier)
    if speed == 0.25:
        return (1, 4)
    if speed == 0.5:
        return (1, 2)
    if speed == 1.0:
        return (1, 1)
    if speed == 1.5:
        return (3, 2)
    if speed == 2.0:
        return (2, 1)
    if speed == 4.0:
        return (4, 1)
    return (1, 1)


def _scale_elapsed_ms(elapsed_ms: int, multiplier: float) -> int:
    elapsed = _safe_int(elapsed_ms)
    if elapsed <= 0:
        return 0
    numerator, denominator = _speed_ratio(multiplier)
    return int((int(elapsed) * int(numerator)) // int(denominator))


def _optional_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def _positive_optional_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None
