import json
from pathlib import Path
from typing import Dict, List

from .discovery import DATA_ROOTS, compute_disk_usage


def generate_report(registry: List[Dict]) -> Dict:
    roots_usage = {
        name: compute_disk_usage(path) for name, path in DATA_ROOTS.items()
    }
    roots_usage["total"] = sum(roots_usage.values())
    components = []
    for rec in registry:
        components.append(
            {
                "id": rec.get("id"),
                "type": rec.get("type"),
                "source": rec.get("source"),
                "state": rec.get("state"),
                "disk_usage_bytes": rec.get("disk_usage_bytes"),
                "install_path": rec.get("install_path"),
            }
        )
    return {"roots": roots_usage, "components": components}


def format_report_text(report: Dict) -> str:
    lines = []
    roots = report.get("roots", {})
    lines.append("Storage Roots:")
    for name in ["store", "cache", "dumps", "roaming", "total"]:
        if name in roots:
            lines.append(f"  {name}: {roots.get(name, 0)} bytes")
    lines.append("")
    lines.append("Components:")
    comps: List[Dict] = report.get("components") or []
    if not comps:
        lines.append("  (none found)")
    else:
        for comp in comps:
            lines.append(
                f"  {comp.get('id')} [{comp.get('type')}] {comp.get('source')} "
                f"{comp.get('state')} {comp.get('disk_usage_bytes')} bytes @ {comp.get('install_path')}"
            )
    return "\n".join(lines)
