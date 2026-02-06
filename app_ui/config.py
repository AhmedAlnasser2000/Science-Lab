# =============================================================================
# NAV INDEX (search these tags)
# [NAV-00] Imports / constants
# [NAV-10] Config loading (defaults/roaming/policy)
# [NAV-20] Public getters
# [NAV-90] Helpers
# [NAV-99] End
# =============================================================================

# === [NAV-00] Imports / constants ============================================
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

CONFIG_PATH = Path("data/roaming/ui_config.json")
PROFILE_PATH = Path("data/roaming/experience_profile.json")
EXPERIENCE_PROFILES = ["Learner", "Educator", "Explorer"]
_DEFAULT_UI_CONFIG = {"active_pack_id": "default", "reduced_motion": False}


# === [NAV-10] Config loading (defaults/roaming/policy) =======================
def load_ui_config() -> Dict:
    path = CONFIG_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_DEFAULT_UI_CONFIG, indent=2), encoding="utf-8")
        return _DEFAULT_UI_CONFIG.copy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _DEFAULT_UI_CONFIG.copy()
    for key, value in _DEFAULT_UI_CONFIG.items():
        data.setdefault(key, value)
    return data


def save_ui_config(data: Dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_experience_profile() -> str:
    default = EXPERIENCE_PROFILES[0]
    if not PROFILE_PATH.exists():
        return default
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        profile = data.get("profile")
        if profile in EXPERIENCE_PROFILES:
            return profile
    except Exception:
        return default
    return default


def save_experience_profile(profile: str) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps({"profile": profile}, indent=2), encoding="utf-8")


# === [NAV-20] Public getters ==================================================
def get_reduced_motion() -> bool:
    config = load_ui_config()
    return bool(config.get("reduced_motion", False))


# === [NAV-99] End =============================================================
__all__ = [
    "CONFIG_PATH",
    "PROFILE_PATH",
    "EXPERIENCE_PROFILES",
    "load_ui_config",
    "save_ui_config",
    "load_experience_profile",
    "save_experience_profile",
    "get_reduced_motion",
]
