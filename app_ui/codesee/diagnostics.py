from __future__ import annotations

from typing import Any, Dict, List, Optional
import os
import time


def _safe_env(key: str, default: str = "") -> str:
    try:
        return os.environ.get(key, default)
    except Exception:
        return default


def _safe_str(value: object, fallback: str = "N/A") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value or fallback
    try:
        return str(value)
    except Exception:
        return fallback


def _normalize_query(query: str) -> str:
    return query.strip().lower()


def _filter_entries(query: str, entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    needle = _normalize_query(query)
    if not needle:
        return list(entries)
    filtered: List[Dict[str, str]] = []
    for entry in entries:
        title = (entry.get("title") or "").lower()
        entry_id = (entry.get("id") or "").lower()
        if needle in title or needle in entry_id:
            filtered.append(entry)
    return filtered


def codesee_diagnostics_snapshot(screen: Optional[object]) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}
    disabled_env = _safe_env("PHYSICSLAB_CODESEE_DISABLE", "0") == "1"
    snapshot["codesee_enabled"] = not disabled_env
    snapshot["codesee_disabled_reason"] = "Disabled by env" if disabled_env else "N/A"

    build_info = {}
    if screen is not None:
        build_info = getattr(screen, "_build_info", {}) or {}
    if not build_info:
        try:
            from app_ui import versioning

            build_info = versioning.get_build_info() or {}
        except Exception:
            build_info = {}
    snapshot["build_version"] = _safe_str(build_info.get("app_version"))
    snapshot["build_id"] = _safe_str(build_info.get("build_id"))

    lens_id = _safe_str(getattr(screen, "_lens", None)) if screen else "N/A"
    lens_label = lens_id
    lens_map = getattr(screen, "_lens_map", None) if screen else None
    if lens_map and lens_id in lens_map:
        lens_label = _safe_str(getattr(lens_map[lens_id], "title", lens_id))
    snapshot["lens"] = lens_label
    snapshot["lens_id"] = lens_id
    snapshot["source"] = _safe_str(getattr(screen, "_source", None)) if screen else "N/A"

    current_graph = getattr(screen, "_current_graph", None) if screen else None
    try:
        snapshot["node_count"] = len(current_graph.nodes) if current_graph else "N/A"
        snapshot["edge_count"] = len(current_graph.edges) if current_graph else "N/A"
    except Exception:
        snapshot["node_count"] = "N/A"
        snapshot["edge_count"] = "N/A"

    snapshot["live_mode"] = _safe_str(getattr(screen, "_live_enabled", None)) if screen else "N/A"

    runtime_hub = getattr(screen, "_runtime_hub", None) if screen else None
    if runtime_hub:
        try:
            snapshot["bus_connected"] = "Yes" if runtime_hub.bus_connected() else "No"
        except Exception:
            snapshot["bus_connected"] = "N/A"
        try:
            last_ts = runtime_hub.last_event_ts()
            snapshot["last_activity"] = _safe_str(last_ts)
        except Exception:
            snapshot["last_activity"] = "N/A"
    else:
        snapshot["bus_connected"] = "N/A"
        snapshot["last_activity"] = "N/A"

    palette = getattr(screen, "_lens_palette", None) if screen else None
    snapshot["palette_pinned"] = _safe_str(getattr(screen, "_lens_palette_pinned", None)) if screen else "N/A"
    snapshot["palette_visible"] = _safe_str(getattr(screen, "_lens_palette_visible", None)) if screen else "N/A"
    dock = getattr(screen, "_lens_palette_dock", None) if screen else None
    if dock:
        try:
            snapshot["palette_floating"] = "Yes" if dock.isFloating() else "No"
        except Exception:
            snapshot["palette_floating"] = "N/A"
    else:
        snapshot["palette_floating"] = "N/A"

    query = ""
    entries: List[Dict[str, str]] = []
    if palette is not None:
        try:
            query = palette._search.text() if getattr(palette, "_search", None) else ""
        except Exception:
            query = ""
        try:
            entries = palette._lens_entries() if hasattr(palette, "_lens_entries") else []
        except Exception:
            entries = []
    filtered = _filter_entries(query, entries)
    snapshot["palette_query"] = query or ""
    snapshot["palette_matches"] = len(filtered) if entries else "N/A"
    snapshot["palette_total"] = len(entries) if entries else "N/A"
    recent = getattr(screen, "_lens_palette_recent", None) if screen else None
    snapshot["palette_recent_count"] = len(recent) if isinstance(recent, list) else "N/A"
    return snapshot


def format_codesee_diagnostics_status(snapshot: Dict[str, Any]) -> str:
    lines = [
        "CodeSee Diagnostics",
        "",
        f"Build: {snapshot.get('build_version', 'N/A')} ({snapshot.get('build_id', 'N/A')})",
        f"CodeSee Enabled: {snapshot.get('codesee_enabled', 'N/A')}",
        f"Disable Reason: {snapshot.get('codesee_disabled_reason', 'N/A')}",
        f"Lens: {snapshot.get('lens', 'N/A')} (id: {snapshot.get('lens_id', 'N/A')})",
        f"Source: {snapshot.get('source', 'N/A')}",
        f"Nodes: {snapshot.get('node_count', 'N/A')}",
        f"Edges: {snapshot.get('edge_count', 'N/A')}",
        f"Live Mode: {snapshot.get('live_mode', 'N/A')}",
        f"Bus Connected: {snapshot.get('bus_connected', 'N/A')}",
        f"Last Activity: {snapshot.get('last_activity', 'N/A')}",
        "",
        "Palette:",
        f"  Pinned: {snapshot.get('palette_pinned', 'N/A')}",
        f"  Visible: {snapshot.get('palette_visible', 'N/A')}",
        f"  Floating: {snapshot.get('palette_floating', 'N/A')}",
        f"  Query: {snapshot.get('palette_query', '')}",
        f"  Matches: {snapshot.get('palette_matches', 'N/A')} / {snapshot.get('palette_total', 'N/A')}",
        f"  Recent count: {snapshot.get('palette_recent_count', 'N/A')}",
    ]
    return "\n".join(lines)


def format_codesee_diagnostics(snapshot: Dict[str, Any], logs: List[str]) -> str:
    status = format_codesee_diagnostics_status(snapshot)
    log_block = "\n".join(logs) if logs else "No logs yet."
    return f"{status}\n\nLogs:\n{log_block}"
