from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from .discovery import DATA_ROOTS, compute_disk_usage, ensure_data_roots


def get_data_roots() -> Dict[str, str]:
    """Return absolute paths for canonical data roots."""
    ensure_data_roots()
    return {name: str(path.resolve()) for name, path in DATA_ROOTS.items()}


def _runs_root() -> Path:
    ensure_data_roots()
    store_root = DATA_ROOTS["store"]
    runs = store_root / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    return runs


def allocate_run_dir(lab_id: str) -> Dict[str, object]:
    """Allocate a dedicated run directory for the provided lab."""
    if not lab_id:
        return {"ok": False, "error": "lab_id_required"}
    safe_lab = _sanitize_id(lab_id)
    runs_root = _runs_root()
    lab_root = runs_root / safe_lab
    lab_root.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    run_dir = lab_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "lab_id": lab_id,
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        (run_dir / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except OSError:
        return {"ok": False, "error": "write_failed"}
    return {"ok": True, "lab_id": lab_id, "run_id": run_id, "run_dir": str(run_dir.resolve())}


def list_runs(lab_id: str) -> List[Dict[str, object]]:
    safe_lab = _sanitize_id(lab_id)
    lab_root = _runs_root() / safe_lab
    if not lab_root.exists():
        return []
    runs: List[Dict[str, object]] = []
    for child in sorted(lab_root.iterdir()):
        if not child.is_dir():
            continue
        meta_path = child / "run.json"
        meta = {
            "lab_id": lab_id,
            "run_id": child.name,
            "timestamp": None,
            "path": str(child.resolve()),
        }
        if meta_path.exists():
            try:
                meta.update(json.loads(meta_path.read_text(encoding="utf-8")))
            except Exception:
                meta["timestamp"] = None
        runs.append(meta)
    runs.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    return runs


def prune_runs(lab_id: str, keep_last_n: int = 5) -> Dict[str, object]:
    safe_lab = _sanitize_id(lab_id)
    lab_root = _runs_root() / safe_lab
    if keep_last_n <= 0:
        keep_last_n = 0
    runs = list_runs(lab_id)
    if keep_last_n >= len(runs):
        return {"freed_bytes": 0, "removed_runs": []}
    to_remove = runs[keep_last_n:]
    removed: List[str] = []
    freed = 0
    for run in to_remove:
        path = Path(run.get("path") or lab_root / (run.get("run_id") or ""))
        if not path.exists() or not path.is_dir():
            continue
        try:
            freed += compute_disk_usage(path)
        except Exception:
            pass
        try:
            _remove_tree(path)
            removed.append(str(path))
        except Exception:
            continue
    return {"freed_bytes": freed, "removed_runs": removed}


def summarize_runs() -> Dict[str, object]:
    runs_root = _runs_root()
    summary: Dict[str, object] = {"total_bytes": compute_disk_usage(runs_root), "labs": {}}
    if not runs_root.exists():
        return summary
    for lab_dir in runs_root.iterdir():
        if not lab_dir.is_dir():
            continue
        lab_id = lab_dir.name
        run_count = sum(1 for child in lab_dir.iterdir() if child.is_dir())
        summary["labs"][lab_id] = {"run_count": run_count}
    return summary


def _sanitize_id(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name.strip() or "lab")


def _remove_tree(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir():
            _remove_tree(child)
        else:
            try:
                child.unlink()
            except Exception:
                pass
    try:
        path.rmdir()
    except Exception:
        pass
