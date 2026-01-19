from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Dict

APP_VERSION = "5.2.0-dev"


def get_app_version() -> str:
    return compute_app_version()


def detect_git_available() -> bool:
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return False
    return result.returncode == 0


def get_latest_milestone_from_git_log(limit: int = 50) -> str | None:
    repo_root = Path(__file__).resolve().parent.parent
    if not detect_git_available():
        return None
    try:
        result = subprocess.run(
            ["git", "log", f"-n{limit}", "--pretty=%s"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    pattern = re.compile(r"\bV\d+\.\d+[A-Za-z0-9.]*\b")
    for line in (result.stdout or "").splitlines():
        match = pattern.search(line)
        if match:
            return match.group(0)
    return None


def compute_app_version() -> str:
    env_version = os.environ.get("PHYSICSLAB_APP_VERSION", "").strip()
    if env_version:
        return env_version
    milestone = get_latest_milestone_from_git_log()
    if milestone:
        return f"{milestone}-dev"
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
        "app_version": compute_app_version(),
        "build_id": get_build_id(),
    }
