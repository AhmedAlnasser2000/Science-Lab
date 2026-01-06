from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


def get_crash_dir(base_dir: Optional[Path] = None) -> Path:
    root = base_dir or Path("data/roaming")
    crash_dir = root / "crashes"
    crash_dir.mkdir(parents=True, exist_ok=True)
    return crash_dir


def write_crash_marker(exc: BaseException, context: Dict[str, Any] | None = None) -> Path:
    crash_dir = get_crash_dir()
    payload = {
        "ts": time.time(),
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "context": context or {},
    }
    path = crash_dir / f"crash_marker_{int(time.time())}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
