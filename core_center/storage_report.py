import json
from pathlib import Path
from typing import Dict, List

from .discovery import DATA_ROOTS, compute_disk_usage
from .registry import summarize_registry
from .storage_manager import summarize_runs


def generate_report(registry: List[Dict]) -> Dict:
    roots_usage = {
        name: compute_disk_usage(path) for name, path in DATA_ROOTS.items()
    }
    roots_usage["total"] = sum(roots_usage.values())
    runs_summary = summarize_runs()
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
    registry_summary = summarize_registry(registry)
    return {
        "roots": roots_usage,
        "components": components,
        "runs": runs_summary,
        "registry_summary": registry_summary,
    }


def report_json(registry: List[Dict]) -> Dict:
    return generate_report(registry)


def format_report_text(report: Dict) -> str:
    lines = []
    roots = report.get("roots", {})
    lines.append("Storage Roots:")
    for name in ["store", "cache", "dumps", "roaming", "total"]:
        if name in roots:
            lines.append(f"  {name}: {roots.get(name, 0)} bytes")
    lines.append("")
    runs = report.get("runs") or {}
    total_runs_bytes = runs.get("total_bytes")
    if total_runs_bytes is not None:
        lines.append(f"Runs storage: {total_runs_bytes} bytes")
        labs = runs.get("labs") or {}
        if labs:
            lines.append("  Runs per lab:")
            for lab_id, info in sorted(labs.items()):
                lines.append(f"    - {lab_id}: {info.get('run_count', 0)} runs")
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


def report_text(registry: List[Dict]) -> str:
    return format_report_text(generate_report(registry))
    summary = report.get("registry_summary") or {}
    if summary:
        lines.append("")
        lines.append(f"Registry total entries: {summary.get('total', 0)}")
        by_type = summary.get("by_type") or {}
        if by_type:
            lines.append("  By type:")
            for key, value in sorted(by_type.items()):
                lines.append(f"    - {key}: {value}")
