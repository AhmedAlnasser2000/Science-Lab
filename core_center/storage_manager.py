from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

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


DEFAULT_KEEP_LAST = 10


def allocate_run_dir(lab_id: str, keep_last_n: int | None = None) -> Dict[str, object]:
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
    keep = DEFAULT_KEEP_LAST if keep_last_n is None else max(1, int(keep_last_n))
    enforce_run_retention(runs_root, safe_lab, keep)
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


def enforce_run_retention(runs_root: Path, lab_id: str, keep_last_n: int) -> Dict[str, object]:
    keep = max(1, keep_last_n)
    lab_root = runs_root / lab_id
    if not lab_root.exists():
        return {"freed_bytes": 0, "removed_runs": []}
    entries = _collect_run_entries(lab_root)
    if len(entries) <= keep:
        return {"freed_bytes": 0, "removed_runs": []}
    to_remove = entries[keep:]
    removed: List[str] = []
    freed = 0
    for run_id, path in to_remove:
        if not path.exists() or not path.is_dir():
            continue
        try:
            freed += compute_disk_usage(path)
        except Exception:
            pass
        try:
            _remove_tree(path)
            removed.append(run_id)
        except Exception:
            continue
    return {"freed_bytes": freed, "removed_runs": removed}


def summarize_runs() -> Dict[str, object]:
    runs_root = _runs_root()
    summary: Dict[str, object] = {"total_bytes": 0, "labs": {}}
    if not runs_root.exists():
        return summary
    total = 0
    for lab_dir in runs_root.iterdir():
        if not lab_dir.is_dir():
            continue
        lab_id = lab_dir.name
        bytes_used = 0
        run_count = 0
        for run_dir in lab_dir.iterdir():
            if not run_dir.is_dir():
                continue
            run_count += 1
            try:
                bytes_used += compute_disk_usage(run_dir)
            except Exception:
                continue
        total += bytes_used
        summary["labs"][lab_id] = {"run_count": run_count, "bytes": bytes_used}
    summary["total_bytes"] = total
    return summary


def _sanitize_id(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name.strip() or "lab")


def _remove_tree(path: Path) -> None:
    for child in path.iterdir():
        try:
            if child.is_symlink():
                child.unlink()
                continue
            if child.is_dir():
                _remove_tree(child)
            elif child.exists():
                child.unlink()
        except Exception:
            continue
    try:
        if not path.is_symlink():
            path.rmdir()
    except Exception:
        pass


def _collect_run_entries(lab_root: Path) -> List[Tuple[str, Path]]:
    entries: List[Tuple[str, Path]] = []
    for child in lab_root.iterdir():
        if not child.is_dir() or child.is_symlink():
            continue
        meta_path = child / "run.json"
        ts_value: float | None = None
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                stamp = data.get("timestamp")
                if isinstance(stamp, str):
                    ts_value = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
            except Exception:
                ts_value = None
        if ts_value is None:
            try:
                ts_value = child.stat().st_mtime
            except OSError:
                ts_value = 0.0
        entries.append((child.name, child.resolve()))
    entries.sort(key=lambda item: _entry_sort_key(item[1]), reverse=True)
    return entries


def _entry_sort_key(path: Path) -> float:
    meta_path = path / "run.json"
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            stamp = data.get("timestamp")
            if isinstance(stamp, str):
                return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
