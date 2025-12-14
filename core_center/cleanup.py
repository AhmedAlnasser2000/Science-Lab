import shutil
import time
from pathlib import Path
from typing import Dict, List


def purge_cache(root: Path = Path("data/cache")) -> Dict:
    removed: List[str] = []
    if not root.exists():
        return {"removed": removed, "bytes_freed": 0}
    total = 0
    for child in root.iterdir():
        try:
            if child.is_file():
                total += child.stat().st_size
                child.unlink()
                removed.append(str(child))
            elif child.is_dir():
                total += _dir_size(child)
                shutil.rmtree(child, ignore_errors=True)
                removed.append(str(child))
        except Exception:
            continue
    return {"removed": removed, "bytes_freed": total}


def prune_dumps(
    root: Path = Path("data/dumps"),
    max_age_days: int | None = None,
    max_total_bytes: int | None = None,
) -> Dict:
    removed: List[str] = []
    if not root.exists():
        return {"removed": removed, "bytes_freed": 0}

    now = time.time()
    total_bytes = 0
    entries: List[Path] = []
    for path in root.rglob("*"):
        if path.is_file():
            try:
                size = path.stat().st_size
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                continue
            entries.append(path)
            total_bytes += size
            if max_age_days is not None:
                age_days = (now - mtime) / 86400
                if age_days > max_age_days:
                    total_bytes -= size
                    _remove_file(path, removed)

    if max_total_bytes is not None:
        # Remove oldest files until under limit
        remaining_files = [p for p in entries if p.exists()]
        remaining_files.sort(key=lambda p: p.stat().st_mtime)
        current_total = sum(p.stat().st_size for p in remaining_files)
        for path in remaining_files:
            if current_total <= max_total_bytes:
                break
            sz = path.stat().st_size
            _remove_file(path, removed)
            current_total -= sz

    bytes_freed = sum(_safe_size(Path(p)) for p in removed)
    return {"removed": removed, "bytes_freed": bytes_freed}


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except FileNotFoundError:
            continue
    return total


def _remove_file(path: Path, removed: List[str]) -> None:
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        size = 0
    try:
        path.unlink()
        removed.append(str(path))
    except Exception:
        return


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except Exception:
        return 0
