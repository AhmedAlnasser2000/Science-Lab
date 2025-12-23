from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import Callable


def safe_rmtree(path: Path) -> None:
    """Remove a tree with Windows-friendly permission handling."""
    path = Path(path)
    if not path.exists():
        return
    shutil.rmtree(path, onerror=_handle_remove_error)


def safe_copytree(src: Path, dst: Path) -> None:
    """Copy a tree with safe overwrite handling."""
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        safe_rmtree(dst)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _handle_remove_error(func: Callable, path: str, exc_info) -> None:
    exc = exc_info[1]
    if isinstance(exc, PermissionError) or getattr(exc, "winerror", None) == 5:
        _make_writable(Path(path))
        try:
            func(path)
            return
        except Exception:
            pass
    raise exc


def _make_writable(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
    except Exception:
        pass
    parent = path.parent
    try:
        os.chmod(parent, stat.S_IWRITE)
    except Exception:
        pass
