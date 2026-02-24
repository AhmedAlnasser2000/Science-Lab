from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    corrupt_lines: int
    warnings: List[str]
    meta: Dict[str, Any]


def load_replay_session(session_root: Path) -> ReplayTimeline:
    root = Path(session_root)
    warnings: List[str] = []

    meta = _normalize_meta(
        session_store.read_json(session_store.meta_path(root)),
        root=root,
        warnings=warnings,
    )

    rows, corrupt_lines = session_store.read_jsonl(session_store.records_path(root))
    frames: List[ReplayFrame] = []
    for index, row in enumerate(rows):
        frame = _normalize_frame(row, index=index, warnings=warnings)
        if frame is None:
            continue
        frames.append(frame)

    # Replay contract baseline is deterministic seq order.
    frames.sort(key=lambda item: (int(item.seq), int(item.ts_ms_epoch)))

    keyframes: Dict[int, Dict[str, Any]] = {}
    for frame in frames:
        if frame.record_type != session_schema.RECORD_KEYFRAME_REF:
            continue
        payload = _load_keyframe_payload(root=root, frame=frame, warnings=warnings)
        if payload is None or frame.keyframe_seq is None:
            continue
        keyframes[int(frame.keyframe_seq)] = payload

    if corrupt_lines > 0:
        warnings.append(f"records corrupt_lines={int(corrupt_lines)}")

    counts = meta.get("counts") if isinstance(meta.get("counts"), dict) else session_schema.default_counts()
    counts["corrupt_lines"] = max(_safe_int(counts.get("corrupt_lines")), int(corrupt_lines))
    meta["counts"] = counts

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
        corrupt_lines=int(corrupt_lines),
        warnings=warnings,
        meta=meta,
    )


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
