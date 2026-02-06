# =============================================================================
# NAV INDEX (search these tags)
# [NAV-00] Imports / constants
# [NAV-10] Public API
# [NAV-99] end
# =============================================================================

# === [NAV-00] Imports / constants ============================================
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


# === [NAV-10] Public API ======================================================
def load_index(workspace_id: str) -> Dict[str, Any]:
    path = _index_path(workspace_id)
    if not path.exists():
        return {"snapshots": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"snapshots": []}
    if not isinstance(data, dict):
        return {"snapshots": []}
    if not isinstance(data.get("snapshots"), list):
        data["snapshots"] = []
    return data


def save_index(workspace_id: str, index: Dict[str, Any]) -> None:
    path = _index_path(workspace_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    except Exception:
        return


def register_snapshot(path: Path, metadata: Dict[str, Any]) -> None:
    workspace_id = _workspace_id_from_metadata(metadata) or _workspace_id_from_path(path) or "default"
    index = load_index(workspace_id)
    snapshots = index.get("snapshots")
    if not isinstance(snapshots, list):
        snapshots = []
        index["snapshots"] = snapshots

    entry = {
        "path": str(path),
        "filename": path.name,
        "timestamp": _timestamp_from_metadata(metadata) or _timestamp_from_name(path.name),
        "source": metadata.get("source"),
        "graph_id": metadata.get("graph_id"),
        "lens_id": metadata.get("lens_id"),
    }
    existing = _find_entry(snapshots, entry["path"])
    if existing:
        existing.update({k: v for k, v in entry.items() if v})
    else:
        snapshots.append(entry)
    save_index(workspace_id, index)


def list_snapshots_sorted(workspace_id: str) -> List[Dict[str, Any]]:
    index = load_index(workspace_id)
    snapshots = index.get("snapshots")
    if not isinstance(snapshots, list):
        return []
    return sorted(snapshots, key=lambda item: str(item.get("timestamp") or item.get("filename") or ""))


def _index_path(workspace_id: str) -> Path:
    safe_id = str(workspace_id or "default").strip() or "default"
    return Path("data") / "workspaces" / safe_id / "codesee" / "snapshots" / "index.json"


def _find_entry(entries: List[Dict[str, Any]], path_value: str) -> Optional[Dict[str, Any]]:
    for entry in entries:
        if entry.get("path") == path_value:
            return entry
    return None


def _timestamp_from_metadata(metadata: Dict[str, Any]) -> Optional[str]:
    value = metadata.get("timestamp")
    if isinstance(value, str) and value:
        return value
    return None


def _timestamp_from_name(name: str) -> Optional[str]:
    if not isinstance(name, str):
        return None
    if "_" not in name:
        return None
    parts = name.split("_", 2)
    if len(parts) >= 2:
        stamp = f"{parts[0]}_{parts[1]}"
        return stamp if stamp.strip() else None
    return None


def _workspace_id_from_metadata(metadata: Dict[str, Any]) -> Optional[str]:
    value = metadata.get("workspace_id")
    if isinstance(value, str) and value:
        return value
    return None


def _workspace_id_from_path(path: Path) -> Optional[str]:
    try:
        parts = [part.lower() for part in path.parts]
    except Exception:
        return None
    if "data" not in parts or "workspaces" not in parts:
        return None
    try:
        idx = parts.index("workspaces")
        workspace_id = path.parts[idx + 1]
        return str(workspace_id)
    except Exception:
        return None


# === [NAV-99] end =============================================================
