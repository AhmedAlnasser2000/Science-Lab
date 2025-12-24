from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from .discovery import DATA_ROOTS, compute_disk_usage, ensure_data_roots
from . import workspace_manager
from diagnostics.fs_ops import safe_rmtree


def get_data_roots() -> Dict[str, str]:
    """Return absolute paths for canonical data roots."""
    ensure_data_roots()
    return {name: str(path.resolve()) for name, path in DATA_ROOTS.items()}


def _runs_root() -> Path:
    try:
        paths = workspace_manager.get_active_workspace_paths()
    except Exception:
        paths = {}
    root = Path(paths.get("runs") or Path("data") / "workspaces" / "default" / "runs")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _runs_local_root() -> Path:
    try:
        paths = workspace_manager.get_active_workspace_paths()
    except Exception:
        paths = {}
    root = Path(paths.get("runs_local") or Path("data") / "workspaces" / "default" / "runs_local")
    root.mkdir(parents=True, exist_ok=True)
    return root


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


def list_runs_inventory() -> Dict[str, object]:
    runs_root = _runs_root()
    runs_local_root = _runs_local_root()
    labs: Dict[str, List[Dict[str, object]]] = {}
    _collect_runs_for_root(runs_root, "runs", labs)
    _collect_runs_for_root(runs_local_root, "runs_local", labs)
    return {
        "roots": {
            "runs": str(runs_root.resolve()),
            "runs_local": str(runs_local_root.resolve()),
        },
        "labs": labs,
    }


def delete_run(lab_id: str, run_id: str, root_kind: str) -> Dict[str, object]:
    root = _runs_root() if root_kind == "runs" else _runs_local_root()
    safe_lab = _sanitize_id(lab_id)
    target = (root / safe_lab / run_id).resolve()
    root_resolved = root.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError:
        return {"ok": False, "error": "invalid_path"}
    if not target.exists() or not target.is_dir():
        return {"ok": False, "error": "run_not_found"}
    try:
        safe_rmtree(target)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def delete_runs_many(items: List[Dict[str, object]]) -> Dict[str, object]:
    ok_count = 0
    fail_count = 0
    freed_bytes = 0
    errors: List[str] = []
    for item in items or []:
        lab_id = str(item.get("lab_id") or "")
        run_id = str(item.get("run_id") or "")
        root_kind = str(item.get("root_kind") or "runs")
        if not lab_id or not run_id:
            fail_count += 1
            errors.append("invalid_item")
            continue
        root = _runs_root() if root_kind == "runs" else _runs_local_root()
        safe_lab = _sanitize_id(lab_id)
        target = (root / safe_lab / run_id).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            fail_count += 1
            errors.append(f"{lab_id}/{run_id}: invalid_path")
            continue
        if not target.exists() or not target.is_dir():
            fail_count += 1
            errors.append(f"{lab_id}/{run_id}: not_found")
            continue
        try:
            freed_bytes += compute_disk_usage(target)
        except Exception:
            pass
        try:
            safe_rmtree(target)
            ok_count += 1
        except Exception as exc:
            fail_count += 1
            errors.append(f"{lab_id}/{run_id}: {exc}")
    return {
        "ok_count": ok_count,
        "fail_count": fail_count,
        "freed_bytes": freed_bytes,
        "errors": errors,
    }


def prune_runs(
    *,
    keep_last_per_lab: int | None,
    delete_older_than_days: int | None,
    max_total_mb: int | None,
) -> Dict[str, object]:
    summary = {"deleted_count": 0, "freed_bytes": 0, "errors": []}
    rules = {
        "keep_last_per_lab": _coerce_int(keep_last_per_lab, minimum=0),
        "delete_older_than_days": _coerce_int(delete_older_than_days, minimum=0),
        "max_total_mb": _coerce_int(max_total_mb, minimum=0),
    }
    for root_kind, root in (("runs", _runs_root()), ("runs_local", _runs_local_root())):
        result = _prune_root(root, root_kind, rules)
        summary["deleted_count"] += result.get("deleted_count", 0)
        summary["freed_bytes"] += result.get("freed_bytes", 0)
        summary["errors"].extend(result.get("errors", []))
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


def _collect_runs_for_root(runs_root: Path, root_kind: str, labs: Dict[str, List[Dict[str, object]]]) -> None:
    if not runs_root.exists():
        return
    for lab_dir in runs_root.iterdir():
        if not lab_dir.is_dir() or lab_dir.is_symlink():
            continue
        lab_id = lab_dir.name
        runs = labs.setdefault(lab_id, [])
        for run_dir in lab_dir.iterdir():
            if not run_dir.is_dir() or run_dir.is_symlink():
                continue
            created_at, ts = _run_created_at(run_dir)
            try:
                size_bytes = compute_disk_usage(run_dir)
            except Exception:
                size_bytes = 0
            runs.append(
                {
                    "run_id": run_dir.name,
                    "path": str(run_dir.resolve()),
                    "created_at": created_at,
                    "timestamp": ts,
                    "size_bytes": size_bytes,
                    "root_kind": root_kind,
                }
            )
        runs.sort(key=lambda item: item.get("timestamp") or 0.0, reverse=True)


def _run_created_at(run_dir: Path) -> Tuple[str | None, float]:
    meta_path = run_dir / "run.json"
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            stamp = data.get("timestamp")
            if isinstance(stamp, str):
                ts = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
                return stamp, ts
        except Exception:
            pass
    try:
        ts = run_dir.stat().st_mtime
        created_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        return created_at, ts
    except Exception:
        return None, 0.0


def _prune_root(runs_root: Path, root_kind: str, rules: Dict[str, int]) -> Dict[str, object]:
    keep_last = rules.get("keep_last_per_lab") or 0
    older_than_days = rules.get("delete_older_than_days") or 0
    max_total_mb = rules.get("max_total_mb") or 0
    max_total_bytes = max_total_mb * 1024 * 1024 if max_total_mb else 0
    summary = {"deleted_count": 0, "freed_bytes": 0, "errors": []}
    if not runs_root.exists():
        return summary
    now = time.time()
    all_runs: List[Tuple[float, Path, str]] = []
    for lab_dir in runs_root.iterdir():
        if not lab_dir.is_dir() or lab_dir.is_symlink():
            continue
        entries = _collect_run_entries(lab_dir)
        if keep_last > 0 and len(entries) > keep_last:
            for run_id, path in entries[keep_last:]:
                all_runs.append((_entry_sort_key(path), path, run_id))
        for run_id, path in entries:
            if older_than_days <= 0:
                continue
            age_days = (now - _entry_sort_key(path)) / 86400.0
            if age_days >= older_than_days:
                all_runs.append((_entry_sort_key(path), path, run_id))
    # De-duplicate by path
    seen = set()
    candidates: List[Tuple[float, Path, str]] = []
    for ts, path, run_id in all_runs:
        if path in seen:
            continue
        seen.add(path)
        candidates.append((ts, path, run_id))
    # Apply max total size across runs_root (oldest first)
    if max_total_bytes > 0:
        total_bytes = 0
        run_sizes: List[Tuple[float, Path, str, int]] = []
        for lab_dir in runs_root.iterdir():
            if not lab_dir.is_dir() or lab_dir.is_symlink():
                continue
            for run_dir in lab_dir.iterdir():
                if not run_dir.is_dir() or run_dir.is_symlink():
                    continue
                try:
                    size = compute_disk_usage(run_dir)
                except Exception:
                    size = 0
                total_bytes += size
                run_sizes.append((_entry_sort_key(run_dir), run_dir, run_dir.name, size))
        if total_bytes > max_total_bytes:
            run_sizes.sort(key=lambda item: item[0])  # oldest first
            bytes_to_free = total_bytes - max_total_bytes
            freed = 0
            for _, path, run_id, size in run_sizes:
                if freed >= bytes_to_free:
                    break
                if path in seen:
                    continue
                seen.add(path)
                candidates.append((_entry_sort_key(path), path, run_id))
                freed += size
    # Delete candidates (oldest first)
    candidates.sort(key=lambda item: item[0])
    root_resolved = runs_root.resolve()
    for _, path, run_id in candidates:
        try:
            path_resolved = path.resolve()
            path_resolved.relative_to(root_resolved)
        except ValueError:
            summary["errors"].append(f"{root_kind}:{run_id}: invalid_path")
            continue
        try:
            summary["freed_bytes"] += compute_disk_usage(path)
        except Exception:
            pass
        try:
            safe_rmtree(path)
            summary["deleted_count"] += 1
        except Exception as exc:
            summary["errors"].append(f"{root_kind}:{run_id}: {exc}")
    return summary


def _coerce_int(value: object, minimum: int = 0) -> int:
    try:
        num = int(value) if value is not None else 0
    except Exception:
        num = 0
    if num < minimum:
        return minimum
    return num


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
