from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app_ui.codesee.runtime import session_store as runtime_session_store

BOOKMARKS_SCHEMA_VERSION = 1


def bookmarks_path(root: Path) -> Path:
    return Path(root) / "bookmarks.json"


def read_bookmarks(
    root: Path,
    *,
    session_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> Dict[str, Any]:
    session_root = Path(root)
    payload = runtime_session_store.read_json(bookmarks_path(session_root))
    return _normalize_bookmarks_payload(
        payload,
        session_id=session_id or session_root.name,
        workspace_id=workspace_id or _infer_workspace_id(session_root),
    )


def write_bookmarks(
    root: Path,
    payload: Dict[str, Any],
    *,
    session_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> Dict[str, Any]:
    session_root = Path(root)
    normalized = _normalize_bookmarks_payload(
        payload,
        session_id=session_id or session_root.name,
        workspace_id=workspace_id or _infer_workspace_id(session_root),
    )
    normalized["updated_at_ms_epoch"] = int(round(time.time() * 1000.0))
    runtime_session_store.write_json(bookmarks_path(session_root), normalized)
    return normalized


def _normalize_bookmarks_payload(
    raw: Any,
    *,
    session_id: str,
    workspace_id: str,
) -> Dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    out: Dict[str, Any] = {
        "schema_version": BOOKMARKS_SCHEMA_VERSION,
        "session_id": runtime_session_store.sanitize_session_id(session_id),
        "workspace_id": runtime_session_store.sanitize_workspace_id(workspace_id),
        "updated_at_ms_epoch": _safe_int(source.get("updated_at_ms_epoch")),
        "bookmarks": _normalize_bookmark_list(source.get("bookmarks")),
    }
    return out


def _normalize_bookmark_list(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    items: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        seq = _safe_int(entry.get("seq"))
        if seq <= 0:
            continue
        bookmark_id = _sanitize_bookmark_id(entry.get("bookmark_id"))
        if not bookmark_id:
            bookmark_id = f"bookmark_{index + 1}"
        if bookmark_id in seen_ids:
            continue
        seen_ids.add(bookmark_id)
        label = str(entry.get("label") or "").strip() or f"Bookmark {len(items) + 1}"
        ts_ms_epoch = _safe_int(entry.get("ts_ms_epoch"))
        created_at = _safe_int(entry.get("created_at_ms_epoch")) or ts_ms_epoch
        note = str(entry.get("note") or "").strip()
        item: Dict[str, Any] = {
            "bookmark_id": bookmark_id,
            "label": label,
            "seq": seq,
            "ts_ms_epoch": ts_ms_epoch,
            "created_at_ms_epoch": created_at,
        }
        if note:
            item["note"] = note
        items.append(item)
    items.sort(key=lambda item: (int(item.get("seq") or 0), str(item.get("bookmark_id") or "")))
    return items


def _sanitize_bookmark_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in text)


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return 0


def _infer_workspace_id(root: Path) -> str:
    parts = list(Path(root).parts)
    for index, part in enumerate(parts):
        if str(part).lower() != "workspaces":
            continue
        if index + 1 < len(parts):
            return runtime_session_store.sanitize_workspace_id(str(parts[index + 1]))
        break
    return "default"
