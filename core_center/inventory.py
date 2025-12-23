from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_manifest(path: Path) -> Dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _record(
    *,
    item_id: str,
    version: str | None,
    path: Path,
    kind: str,
    ok: bool,
    error: str | None = None,
) -> Dict:
    return {
        "id": item_id,
        "kind": kind,
        "version": version,
        "path": _safe_relative(path),
        "installed": True,
        "health": {"ok": ok, "error": error},
        "last_seen": _now_iso(),
    }


def list_installed_modules() -> List[Dict]:
    results: List[Dict] = []
    root = ROOT / "content_store"
    if not root.exists():
        return results
    for manifest_path in root.rglob("module_manifest.json"):
        manifest = _load_manifest(manifest_path)
        module_id = str(manifest.get("module_id") or manifest_path.parent.name)
        version = manifest.get("content_version") or manifest.get("version")
        ok = bool(manifest.get("module_id") or manifest_path.parent.exists())
        results.append(
            _record(
                item_id=module_id,
                version=str(version) if version is not None else None,
                path=manifest_path.parent,
                kind="module",
                ok=ok,
            )
        )
    return results


def list_installed_component_packs() -> List[Dict]:
    results: List[Dict] = []
    root = ROOT / "component_store" / "component_v1" / "packs"
    if not root.exists():
        return results
    for manifest_path in root.rglob("component_pack_manifest.json"):
        manifest = _load_manifest(manifest_path)
        pack_id = str(manifest.get("pack_id") or manifest_path.parent.name)
        version = manifest.get("version")
        ok = bool(manifest.get("pack_id") or manifest_path.parent.exists())
        results.append(
            _record(
                item_id=pack_id,
                version=str(version) if version is not None else None,
                path=manifest_path.parent,
                kind="component_pack",
                ok=ok,
            )
        )
    return results


def list_installed_ui_packs() -> List[Dict]:
    results: List[Dict] = []
    root = ROOT / "ui_store" / "ui_v1" / "packs"
    if not root.exists():
        return results
    for manifest_path in root.rglob("ui_pack_manifest.json"):
        manifest = _load_manifest(manifest_path)
        pack_id = str(manifest.get("id") or manifest.get("ui_pack_id") or manifest_path.parent.name)
        version = manifest.get("version")
        ok = bool(manifest.get("id") or manifest_path.parent.exists())
        results.append(
            _record(
                item_id=pack_id,
                version=str(version) if version is not None else None,
                path=manifest_path.parent,
                kind="ui_pack",
                ok=ok,
            )
        )
    return results


def get_inventory_snapshot() -> Dict[str, List[Dict]]:
    return {
        "generated_at": _now_iso(),
        "modules": list_installed_modules(),
        "component_packs": list_installed_component_packs(),
        "ui_packs": list_installed_ui_packs(),
    }
