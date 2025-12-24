from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Dict

from .discovery import DATA_ROOTS, ensure_data_roots

DEFAULT_POLICY = {
    "max_concurrent_sims": 1,
    "low_end_mode": False,
    "fps_cap": 60,
    "runs_keep_last_n": 10,
    "runs": {
        "cleanup": {
            "keep_last_per_lab": 10,
            "delete_older_than_days": 0,
            "max_total_mb": 0,
        }
    },
    "exports_enabled": False,
    "reduced_motion_enforced": False,
    "telemetry_enabled": False,
}


def _policy_path() -> Path:
    ensure_data_roots()
    roaming = DATA_ROOTS["roaming"]
    return roaming / "policy.json"


def get_default_policy() -> Dict[str, object]:
    return deepcopy(DEFAULT_POLICY)


def load_overrides() -> Dict[str, object]:
    path = _policy_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_policy() -> Dict[str, object]:
    policy = get_default_policy()
    overrides = load_overrides()
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(policy.get(key), dict):
            merged = dict(policy.get(key, {}))
            for sub_key, sub_val in value.items():
                if isinstance(sub_val, dict) and isinstance(merged.get(sub_key), dict):
                    nested = dict(merged.get(sub_key, {}))
                    nested.update(sub_val)
                    merged[sub_key] = nested
                else:
                    merged[sub_key] = sub_val
            policy[key] = merged
        else:
            policy[key] = value
    return policy
