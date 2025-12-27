from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

SEVERITY_ORDER = ["crash", "error", "warn", "probe.fail", "expect.value", "normal"]


@dataclass(frozen=True)
class Badge:
    key: str
    rail: str
    title: str
    summary: str
    detail: Optional[str] = None
    severity: Optional[str] = None
    timestamp: Optional[str] = None


def sort_by_priority(badges: List[Badge]) -> List[Badge]:
    return sorted(badges, key=lambda badge: (_severity_rank(badge), badge.key))


def badge_from_key(
    key: str,
    *,
    rail: Optional[str] = None,
    detail: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Badge:
    info = BADGE_DEFS.get(key)
    if info:
        title, summary, severity, default_rail = info
    else:
        title = key
        summary = key
        severity = None
        default_rail = "top"
    return Badge(
        key=key,
        rail=rail or default_rail,
        title=title,
        summary=summary,
        detail=detail,
        severity=severity,
        timestamp=timestamp,
    )


def badges_from_keys(*, top: Optional[List[str]] = None, bottom: Optional[List[str]] = None) -> List[Badge]:
    badges: List[Badge] = []
    for key in top or []:
        badges.append(badge_from_key(key, rail="top"))
    for key in bottom or []:
        badges.append(badge_from_key(key, rail="bottom"))
    return badges


def badge_from_dict(data: Dict[str, Any]) -> Optional[Badge]:
    key = str(data.get("key") or "").strip()
    if not key:
        return None
    rail = data.get("rail")
    if rail not in ("top", "bottom"):
        rail = None
    badge = badge_from_key(
        key,
        rail=rail,
        detail=_optional_str(data.get("detail")),
        timestamp=_optional_str(data.get("timestamp")),
    )
    title = _optional_str(data.get("title")) or badge.title
    summary = _optional_str(data.get("summary")) or badge.summary
    severity = _optional_str(data.get("severity")) or badge.severity
    if title == badge.title and summary == badge.summary and severity == badge.severity:
        return badge
    return Badge(
        key=badge.key,
        rail=badge.rail,
        title=title,
        summary=summary,
        detail=badge.detail,
        severity=severity,
        timestamp=badge.timestamp,
    )


def badge_to_dict(badge: Badge) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "key": badge.key,
        "rail": badge.rail,
        "title": badge.title,
        "summary": badge.summary,
    }
    if badge.detail:
        payload["detail"] = badge.detail
    if badge.severity:
        payload["severity"] = badge.severity
    if badge.timestamp:
        payload["timestamp"] = badge.timestamp
    return payload


def severity_for_badge(badge: Badge) -> str:
    if badge.severity:
        return badge.severity
    info = BADGE_DEFS.get(badge.key)
    if info:
        return info[2]
    return "normal"


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _severity_rank(badge: Badge) -> int:
    severity = severity_for_badge(badge)
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        return SEVERITY_ORDER.index("normal")


BADGE_DEFS: Dict[str, tuple[str, str, str, str]] = {
    "state.crash": ("Crash", "System crash detected.", "crash", "top"),
    "state.error": ("Error", "Unhandled error detected.", "error", "top"),
    "state.warn": ("Warning", "Warning condition reported.", "warn", "top"),
    "state.blocked": ("Blocked", "Blocked by policy or availability.", "warn", "top"),
    "conn.offline": ("Offline", "Connection offline.", "warn", "top"),
    "perf.slow": ("Slow", "Performance degraded.", "warn", "top"),
    "activity.muted": ("Muted", "Muted activity detected.", "normal", "top"),
    "expect.value": ("Expectation", "Expectation value tracked.", "expect.value", "bottom"),
    "probe.fail": ("Probe Fail", "Probe failed.", "probe.fail", "bottom"),
    "probe.pass": ("Probe Pass", "Probe passed.", "normal", "bottom"),
}
