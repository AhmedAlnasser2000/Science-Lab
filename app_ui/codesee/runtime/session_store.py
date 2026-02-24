from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import session_schema

DEFAULT_MAX_SESSIONS_PER_WORKSPACE = 20
DEFAULT_MAX_TOTAL_MB_PER_WORKSPACE = 1024


def sanitize_workspace_id(workspace_id: str) -> str:
    text = str(workspace_id or "").strip()
    if not text:
        return "default"
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text) or "default"


def sanitize_session_id(session_id: str) -> str:
    text = str(session_id or "").strip()
    if not text:
        return "session"
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in text) or "session"


def workspace_sessions_root(workspace_id: str) -> Path:
    safe = sanitize_workspace_id(workspace_id)
    return Path("data") / "workspaces" / safe / "codesee" / "sessions"


def session_dir(workspace_id: str, session_id: str) -> Path:
    return workspace_sessions_root(workspace_id) / sanitize_session_id(session_id)


def ensure_session_layout(workspace_id: str, session_id: str) -> Path:
    root = session_dir(workspace_id, session_id)
    (root / "keyframes").mkdir(parents=True, exist_ok=True)
    return root


def meta_path(root: Path) -> Path:
    return root / "session_meta.json"


def records_path(root: Path) -> Path:
    return root / "records.jsonl"


def keyframe_path(root: Path, keyframe_seq: int) -> Path:
    return root / "keyframes" / f"{int(keyframe_seq):06d}.json"


def lock_path(root: Path) -> Path:
    return root / "session.lock"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> Tuple[List[Dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    rows: List[Dict[str, Any]] = []
    corrupt = 0
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            text = raw.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except Exception:
                corrupt += 1
                continue
            if isinstance(item, dict):
                rows.append(item)
            else:
                corrupt += 1
    return rows, corrupt


def session_size_bytes(root: Path) -> int:
    total = 0
    if not root.exists():
        return 0
    for path in root.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except Exception:
                continue
    return total


def list_sessions(workspace_id: str) -> List[Dict[str, Any]]:
    root = workspace_sessions_root(workspace_id)
    if not root.exists():
        return []
    sessions: List[Dict[str, Any]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        raw_meta = read_json(meta_path(child))
        meta = _normalized_session_meta(
            raw_meta,
            session_id=child.name,
            workspace_id=workspace_id,
            session_root=child,
        )
        started = int(meta.get("started_at_ms_epoch") or 0)
        has_lock = lock_path(child).exists()
        sessions.append(
            {
                "session_id": child.name,
                "path": child,
                "meta": meta,
                "status": str(meta.get("status") or session_schema.SESSION_STATUS_INCOMPLETE),
                "started_at_ms_epoch": started,
                "size_bytes": session_size_bytes(child),
                "has_lock": has_lock,
            }
        )
    sessions.sort(key=lambda item: item.get("started_at_ms_epoch", 0), reverse=True)
    return sessions


def prune_sessions(
    workspace_id: str,
    *,
    max_sessions_per_workspace: int = DEFAULT_MAX_SESSIONS_PER_WORKSPACE,
    max_total_mb_per_workspace: int = DEFAULT_MAX_TOTAL_MB_PER_WORKSPACE,
    active_session_id: Optional[str] = None,
) -> Dict[str, Any]:
    max_sessions = max(1, int(max_sessions_per_workspace))
    max_total_bytes = max(1, int(max_total_mb_per_workspace)) * 1024 * 1024

    sessions = list_sessions(workspace_id)
    if not sessions:
        return {"pruned": [], "remaining": 0, "remaining_bytes": 0}

    oldest_first = list(reversed(sessions))

    def _is_prunable(entry: Dict[str, Any]) -> bool:
        sid = str(entry.get("session_id") or "")
        if active_session_id and sid == active_session_id:
            return False
        if bool(entry.get("has_lock")):
            return False
        return str(entry.get("status") or "") == session_schema.SESSION_STATUS_COMPLETE

    total_bytes = sum(int(entry.get("size_bytes") or 0) for entry in sessions)
    current_count = len(sessions)
    pruned: List[str] = []

    for entry in oldest_first:
        if current_count <= max_sessions and total_bytes <= max_total_bytes:
            break
        if not _is_prunable(entry):
            continue
        path = entry.get("path")
        if not isinstance(path, Path):
            continue
        try:
            shutil.rmtree(path)
        except Exception:
            continue
        sid = str(entry.get("session_id") or "")
        pruned.append(sid)
        total_bytes -= int(entry.get("size_bytes") or 0)
        current_count -= 1

    return {
        "pruned": pruned,
        "remaining": max(0, current_count),
        "remaining_bytes": max(0, total_bytes),
    }


def _normalized_session_meta(
    raw_meta: Optional[Dict[str, Any]],
    *,
    session_id: str,
    workspace_id: str,
    session_root: Path,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = dict(raw_meta or {})
    counts = _normalized_counts(meta.get("counts"))
    _, corrupt_lines = read_jsonl(records_path(session_root))
    if corrupt_lines > counts.get("corrupt_lines", 0):
        counts["corrupt_lines"] = int(corrupt_lines)

    is_valid = session_schema.validate_session_meta(meta)
    status = str(meta.get("status") or "")
    if not is_valid:
        status = session_schema.SESSION_STATUS_INCOMPLETE
    elif status not in {
        session_schema.SESSION_STATUS_ACTIVE,
        session_schema.SESSION_STATUS_COMPLETE,
        session_schema.SESSION_STATUS_INCOMPLETE,
    }:
        status = session_schema.SESSION_STATUS_INCOMPLETE

    meta["session_id"] = str(meta.get("session_id") or session_id)
    meta["workspace_id"] = str(meta.get("workspace_id") or sanitize_workspace_id(workspace_id))
    meta["status"] = status
    meta["counts"] = counts
    try:
        meta["started_at_ms_epoch"] = int(meta.get("started_at_ms_epoch") or 0)
    except Exception:
        meta["started_at_ms_epoch"] = 0

    # Persist repaired counts/status when a metadata file exists.
    if raw_meta is not None and raw_meta != meta:
        try:
            write_json(meta_path(session_root), meta)
        except Exception:
            pass

    return meta


def _normalized_counts(raw_counts: Any) -> Dict[str, int]:
    out = session_schema.default_counts()
    if not isinstance(raw_counts, dict):
        return out
    for key in out:
        out[key] = _safe_int(raw_counts.get(key))
    return out


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return 0
