from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


STORE_ROOT = Path("component_store/component_v1/packs")


def load_installed_packs() -> List[Dict[str, Any]]:
    """Load installed component pack manifests from the store."""
    manifests: List[Dict[str, Any]] = []
    if not STORE_ROOT.exists():
        return manifests
    for pack_dir in STORE_ROOT.iterdir():
        if not pack_dir.is_dir():
            continue
        manifest_path = pack_dir / "component_pack_manifest.json"
        if not manifest_path.exists():
            continue
        manifest, err = _load_json(manifest_path)
        if manifest is None:
            continue
        manifests.append({"manifest": manifest, "pack_root": pack_dir})
    return manifests


def _load_json(path: Path) -> tuple[Dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "not an object"
    return data, None
