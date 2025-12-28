from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def _safe_workspace_id(workspace_id: Optional[str]) -> str:
    value = str(workspace_id or "").strip()
    return value or "default"


def _crash_root(workspace_id: Optional[str]) -> Path:
    safe_id = _safe_workspace_id(workspace_id)
    return Path("data") / "workspaces" / safe_id / "codesee" / "crash"


def write_latest_crash(workspace_id: Optional[str], record: Dict[str, Any]) -> Path:
    root = _crash_root(workspace_id)
    root.mkdir(parents=True, exist_ok=True)
    record = dict(record or {})
    record.setdefault("format_version", 1)
    record["workspace_id"] = _safe_workspace_id(workspace_id)
    path = root / "latest.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


def write_history_crash(workspace_id: Optional[str], record: Dict[str, Any]) -> Optional[Path]:
    root = _crash_root(workspace_id) / "history"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    ts = str(record.get("ts") or "0")
    exc_type = str(record.get("exception_type") or "crash").replace(" ", "_")
    name = f"{ts}_{exc_type}.json"
    path = root / name
    try:
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return path
    except Exception:
        return None


def read_latest_crash(workspace_id: Optional[str]) -> Optional[Dict[str, Any]]:
    path = _crash_root(workspace_id) / "latest.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("format_version") != 1:
        return None
    return data


def best_effort_workspace_id() -> str:
    root = Path("data") / "workspaces"
    if not root.exists():
        return "default"
    dirs = [entry.name for entry in root.iterdir() if entry.is_dir()]
    if not dirs:
        return "default"
    if "default" in dirs:
        return "default"
    if len(dirs) == 1:
        return dirs[0]
    return "default"
