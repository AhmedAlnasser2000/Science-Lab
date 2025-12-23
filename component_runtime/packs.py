from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path("component_repo/component_v1/packs")
STORE_ROOT = Path("component_store/component_v1/packs")


def list_repo_packs() -> List[Dict[str, Any]]:
    """List packs available in the repo."""
    return _list_packs(REPO_ROOT)


def list_installed_packs() -> List[Dict[str, Any]]:
    """List packs installed in the store."""
    return _list_packs(STORE_ROOT)


def load_installed_packs() -> List[Dict[str, Any]]:
    """Load installed pack manifests for registry registration."""
    return [{"manifest": item["manifest"], "pack_root": item["pack_root"]} for item in list_installed_packs()]


def _list_packs(root: Path) -> List[Dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    packs: List[Dict[str, Any]] = []
    for pack_dir in root.iterdir():
        if not pack_dir.is_dir():
            continue
        manifest_path = pack_dir / "component_pack_manifest.json"
        if not manifest_path.exists():
            continue
        manifest, _ = _load_json(manifest_path)
        if manifest is None:
            continue
        packs.append(
            {
                "pack_id": manifest.get("pack_id"),
                "display_name": manifest.get("display_name"),
                "version": manifest.get("version"),
                "manifest": manifest,
                "pack_root": pack_dir,
            }
        )
    return packs


def _load_json(path: Path) -> tuple[Dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "not an object"
    return data, None
