from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .discovery import DATA_ROOTS, ensure_data_roots
from diagnostics.fs_ops import safe_rmtree


WORKSPACES_ROOT = Path("data") / "workspaces"
TEMPLATES_ROOT = Path("workspace_repo") / "templates"
WORKSPACE_META_FILENAME = "workspace.json"
TEMPLATE_META_FILENAME = "template.json"
TEMPLATE_SEED_FILES = (
    "workspace_config.json",
    "lab_prefs.json",
    "policy_overrides.json",
    "pins.json",
)


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


def _meta_path(workspace_id: str) -> Path:
    return _workspace_root(workspace_id) / WORKSPACE_META_FILENAME


def _load_workspace_meta(workspace_id: str) -> Dict[str, object]:
    path = _meta_path(workspace_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_workspace_meta(workspace_id: str, meta: Dict[str, object]) -> None:
    path = _meta_path(workspace_id)
    try:
        path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception:
        pass


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
    if not _workspace_root(workspace_id).exists():
        info = create_workspace(workspace_id)
        workspace_id = info.get("id") or workspace_id
        paths = info.get("paths") or _ensure_workspace_dirs(workspace_id)
    else:
        paths = _ensure_workspace_dirs(workspace_id)
    _write_active(workspace_id)
    meta = _load_workspace_meta(workspace_id)
    if not meta:
        meta = _default_workspace_meta(workspace_id)
        _write_workspace_meta(workspace_id, meta)
    return {"id": workspace_id, "paths": paths, **meta}


def set_active_workspace(workspace_id: str) -> Dict[str, object]:
    workspace_id = _sanitize_id(workspace_id)
    if not _workspace_root(workspace_id).exists():
        raise FileNotFoundError("workspace_not_found")
    paths = _ensure_workspace_dirs(workspace_id)
    _write_active(workspace_id)
    meta = _load_workspace_meta(workspace_id)
    return {"id": workspace_id, "paths": paths, **meta}


def list_workspaces() -> List[Dict[str, object]]:
    root = WORKSPACES_ROOT
    if not root.exists():
        return []
    active_id = get_active_workspace().get("id")
    items: List[Dict[str, object]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        workspace_id = child.name
        meta = _load_workspace_meta(workspace_id)
        if not meta:
            meta = _default_workspace_meta(workspace_id)
            _write_workspace_meta(workspace_id, meta)
        items.append(
            {
                "id": workspace_id,
                "name": meta.get("name") or workspace_id,
                "created_at": meta.get("created_at"),
                "template_id": meta.get("template_id"),
                "path": str(child.resolve()),
                "active": workspace_id == active_id,
            }
        )
    items.sort(key=lambda item: item.get("id") or "")
    return items


def create_workspace(
    workspace_id: str,
    *,
    name: Optional[str] = None,
    template_id: Optional[str] = None,
) -> Dict[str, object]:
    workspace_id = _sanitize_id(workspace_id)
    paths = _ensure_workspace_dirs(workspace_id)
    meta = _default_workspace_meta(workspace_id)
    if name:
        meta["name"] = name
    if template_id:
        meta["template_id"] = template_id
    _write_workspace_meta(workspace_id, meta)
    if template_id:
        _apply_template(workspace_id, template_id)
    return {"id": workspace_id, "paths": paths, **meta}


def get_active_workspace_paths() -> Dict[str, str]:
    info = get_active_workspace()
    return info.get("paths", {})


def list_templates() -> List[Dict[str, object]]:
    root = TEMPLATES_ROOT
    if not root.exists():
        return []
    templates: List[Dict[str, object]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        meta_path = child / TEMPLATE_META_FILENAME
        if not meta_path.exists():
            continue
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        template_id = data.get("template_id") or child.name
        templates.append(
            {
                "template_id": template_id,
                "name": data.get("name") or template_id,
                "description": data.get("description") or "",
                "path": str(child.resolve()),
            }
        )
    templates.sort(key=lambda item: item.get("template_id") or "")
    return templates


def delete_workspace(workspace_id: str, *, force: bool = False) -> Dict[str, object]:
    workspace_id = _sanitize_id(workspace_id)
    active_id = get_active_workspace().get("id")
    if workspace_id == active_id and not force:
        return {"ok": False, "error": "cannot_delete_active"}
    root = _workspace_root(workspace_id)
    if not root.exists():
        return {"ok": False, "error": "workspace_not_found"}
    try:
        safe_rmtree(root)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def _write_active(workspace_id: str) -> None:
    path = _active_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps({"active_id": workspace_id}, indent=2), encoding="utf-8")
    except Exception:
        pass


def _default_workspace_meta(workspace_id: str) -> Dict[str, object]:
    return {
        "id": workspace_id,
        "name": workspace_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "template_id": None,
    }


def _apply_template(workspace_id: str, template_id: str) -> None:
    template_root = TEMPLATES_ROOT / _sanitize_id(template_id)
    if not template_root.exists():
        return
    prefs_root = _workspace_root(workspace_id) / "prefs"
    prefs_root.mkdir(parents=True, exist_ok=True)
    for name in TEMPLATE_SEED_FILES:
        src = template_root / name
        if not src.exists():
            continue
        dst = prefs_root / name
        try:
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            continue
