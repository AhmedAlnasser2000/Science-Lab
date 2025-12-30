from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict

APP_VERSION = "5.2.0-dev"


def get_app_version() -> str:
    return APP_VERSION


def get_build_id() -> str:
    repo_root = Path(__file__).resolve().parent.parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except Exception:
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    value = (result.stdout or "").strip()
    return value or "unknown"


def get_build_info() -> Dict[str, str]:
    return {
        "app_version": get_app_version(),
        "build_id": get_build_id(),
    }
