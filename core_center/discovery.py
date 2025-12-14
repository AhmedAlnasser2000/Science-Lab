import json
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent

DATA_ROOTS = {
    "store": ROOT / "data" / "store",
    "cache": ROOT / "data" / "cache",
    "dumps": ROOT / "data" / "dumps",
    "roaming": ROOT / "data" / "roaming",
}


def _load_manifest(path: Path) -> Dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _component_from_manifest(path: Path, source: str, comp_type: str) -> Dict:
    manifest = _load_manifest(path)
    return {
        "id": manifest.get("module_id") or manifest.get("ui_pack_id") or "unknown",
        "type": comp_type,
        "version": manifest.get("content_version") or manifest.get("version") or "0.0.0",
        "source": source,
        "state": "present",
        "install_path": str(path.parent.relative_to(ROOT)),
        "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "disk_usage_bytes": compute_disk_usage(path.parent),
    }


def discover_components() -> List[Dict]:
    components: List[Dict] = []
    scans = [
        (ROOT / "content_repo", "module_manifest.json", "module", "content_repo"),
        (ROOT / "content_store", "module_manifest.json", "module", "content_store"),
        (ROOT / "ui_repo", "ui_pack_manifest.json", "ui_pack", "ui_repo"),
        (ROOT / "ui_store", "ui_pack_manifest.json", "ui_pack", "ui_store"),
    ]
    for base, manifest_name, comp_type, source in scans:
        if not base.exists():
            continue
        for path in base.rglob(manifest_name):
            components.append(_component_from_manifest(path, source, comp_type))
    return components


def ensure_data_roots() -> None:
    for path in DATA_ROOTS.values():
        path.mkdir(parents=True, exist_ok=True)


def compute_disk_usage(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except FileNotFoundError:
            continue
    return total
