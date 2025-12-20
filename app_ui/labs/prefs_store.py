from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict

from .context import LabUserPrefs

PREFS_PATH = Path("data/roaming/lab_prefs.json")


def load_prefs() -> Dict[str, object]:
    if not PREFS_PATH.exists():
        return {"labs": {}}
    try:
        data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"labs": {}}
    if not isinstance(data, dict):
        return {"labs": {}}
    if "labs" not in data or not isinstance(data.get("labs"), dict):
        data["labs"] = {}
    return data


def get_lab_prefs(lab_id: str) -> LabUserPrefs:
    data = load_prefs()
    labs = data.get("labs", {})
    entry = labs.get(lab_id, {}) if isinstance(labs, dict) else {}
    if not isinstance(entry, dict):
        entry = {}
    return LabUserPrefs(
        show_grid=bool(entry.get("show_grid", True)),
        show_axes=bool(entry.get("show_axes", True)),
    )


def save_lab_prefs(lab_id: str, prefs: LabUserPrefs) -> None:
    data = load_prefs()
    labs = data.setdefault("labs", {})
    if isinstance(labs, dict):
        labs[lab_id] = asdict(prefs)
    try:
        PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PREFS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass
