from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .discovery import DATA_ROOTS, ensure_data_roots


WORKSPACES_ROOT = Path("data") / "workspaces"


def _active_path() -> Path:
    ensure_data_roots()
    return DATA_ROOTS["roaming"] / "workspace.json"


def _sanitize_id(value: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
    return clean or "default"


def _workspace_root(workspace_id: str) -> Path:
    return WORKSPACES_ROOT / _sanitize_id(workspace_id)


def _ensure_workspace_dirs(workspace_id: str) -> Dict[str, str]:
    root = _workspace_root(workspace_id)
    paths = {
        "root": root,
        "runs": root / "runs",
        "runs_local": root / "runs_local",
        "cache": root / "cache",
        "store": root / "store",
        "prefs": root / "prefs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return {name: str(path.resolve()) for name, path in paths.items()}


def get_active_workspace() -> Dict[str, object]:
    ensure_data_roots()
    path = _active_path()
    workspace_id = "default"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            candidate = data.get("active_id")
            if isinstance(candidate, str) and candidate.strip():
                workspace_id = candidate.strip()
        except Exception:
            pass
    paths = _ensure_workspace_dirs(workspace_id)
    _write_active(workspace_id)
    return {"id": workspace_id, "paths": paths}


def set_active_workspace(workspace_id: str) -> Dict[str, object]:
    workspace_id = _sanitize_id(workspace_id)
    paths = _ensure_workspace_dirs(workspace_id)
    _write_active(workspace_id)
    return {"id": workspace_id, "paths": paths}


def list_workspaces() -> List[str]:
    root = WORKSPACES_ROOT
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir()])


def create_workspace(workspace_id: str) -> Dict[str, object]:
    workspace_id = _sanitize_id(workspace_id)
    paths = _ensure_workspace_dirs(workspace_id)
    return {"id": workspace_id, "paths": paths}


def get_active_workspace_paths() -> Dict[str, str]:
    info = get_active_workspace()
    return info.get("paths", {})


def _write_active(workspace_id: str) -> None:
    path = _active_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps({"active_id": workspace_id}, indent=2), encoding="utf-8")
    except Exception:
        pass
