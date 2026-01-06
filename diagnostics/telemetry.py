from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from core_center.policy_manager import get_default_policy, resolve_policy

_METRIC_LIMIT = 256
_METRICS: Deque[Dict[str, Any]] = deque(maxlen=_METRIC_LIMIT)


def _policy_path(base_dir: Path) -> Path:
    return base_dir / "policy.json"


def _load_policy(base_dir: Optional[Path]) -> Dict[str, Any]:
    if base_dir is None:
        return resolve_policy()
    policy = get_default_policy()
    path = _policy_path(base_dir)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                policy.update(data)
        except Exception:
            pass
    return policy


def is_telemetry_enabled(base_dir: Optional[Path] = None) -> bool:
    policy = _load_policy(base_dir)
    return bool(policy.get("telemetry_enabled", False))


def emit_metric(
    name: str,
    value: float | int = 1,
    *,
    base_dir: Optional[Path] = None,
    **attrs: Any,
) -> bool:
    if not is_telemetry_enabled(base_dir):
        return False
    record = {
        "name": name,
        "value": value,
        "attrs": dict(attrs),
        "ts": time.time(),
    }
    _METRICS.append(record)
    if base_dir is not None:
        metrics_dir = base_dir / "telemetry"
    else:
        metrics_dir = Path("data/roaming/telemetry")
    metrics_dir.mkdir(parents=True, exist_ok=True)
    path = metrics_dir / "metrics.jsonl"
    try:
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    except Exception:
        pass
    return True


def get_recent_metrics() -> List[Dict[str, Any]]:
    return list(_METRICS)


def clear_metrics() -> None:
    _METRICS.clear()
