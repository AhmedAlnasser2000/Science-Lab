import json
import sys
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


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _record_from_manifest(path: Path, source: str, comp_type: str) -> Dict:
    manifest = _load_manifest(path)
    install_root = path.parent
    version = manifest.get("content_version") or manifest.get("version")
    identifier = (
        manifest.get("module_id")
        or manifest.get("ui_pack_id")
        or manifest.get("lab_id")
        or install_root.name
    )
    return {
        "id": str(identifier),
        "type": comp_type,
        "version": version if version is None or isinstance(version, str) else str(version),
        "source": source,
        "state": "present",
        "install_path": _safe_relative(install_root),
        "last_seen": _now_iso(),
        "disk_usage_bytes": compute_disk_usage(install_root),
    }


def discover_components() -> List[Dict]:
    components: List[Dict] = []
    scans = [
        (ROOT / "content_repo", "module_manifest.json", "module", "repo"),
        (ROOT / "content_store", "module_manifest.json", "module", "store"),
        (ROOT / "ui_repo", "ui_pack_manifest.json", "ui_pack", "repo"),
        (ROOT / "ui_store", "ui_pack_manifest.json", "ui_pack", "store"),
    ]
    for base, manifest_name, comp_type, source in scans:
        if not base.exists():
            continue
        for path in base.rglob(manifest_name):
            components.append(_record_from_manifest(path, source, comp_type))
    components.extend(_discover_labs())
    return components


def _discover_labs() -> List[Dict]:
    try:
        from app_ui.labs import registry as lab_registry
    except Exception:
        return []
    labs: List[Dict] = []
    lab_map = lab_registry.list_labs()
    for lab_id, plugin in lab_map.items():
        module_name = plugin.__class__.__module__
        module = sys.modules.get(module_name)
        file_path = None
        if module and hasattr(module, "__file__"):
            file_path = Path(module.__file__).resolve()
        install_path = _safe_relative(file_path.parent if file_path else ROOT / "app_ui" / "labs")
        disk_usage = 0
        if file_path and file_path.exists():
            try:
                disk_usage = file_path.stat().st_size
            except OSError:
                disk_usage = 0
        labs.append(
            {
                "id": lab_id,
                "type": "lab",
                "version": getattr(plugin, "version", None),
                "source": "app",
                "state": "present",
                "install_path": install_path,
                "last_seen": _now_iso(),
                "disk_usage_bytes": disk_usage,
            }
        )
    return labs


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
