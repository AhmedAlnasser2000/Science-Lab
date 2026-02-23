from __future__ import annotations

import os
import time
from typing import List, Optional, Tuple

from app_ui import versioning

from . import crash_io
from .expectations import build_check
from .runtime.events import (
    CodeSeeEvent,
    EVENT_APP_ACTIVITY,
    EVENT_APP_ERROR,
    EVENT_BUS_REPLY,
    EVENT_BUS_REQUEST,
    EVENT_JOB_UPDATE,
    EVENT_SPAN_START,
    SpanEnd,
    SpanStart,
    SpanUpdate,
)
from .runtime.hub import CodeSeeRuntimeHub
from .runtime.monitor_state import MonitorState, STATE_DEGRADED, STATE_FATAL, STATE_RUNNING
from .runtime.trail_focus import (
    clamp_inactive_edge_opacity,
    clamp_inactive_node_opacity,
    clamp_monitor_border_px,
    compute_trail_focus,
)

_FAKE_PACK_ENABLED = False


def is_enabled() -> bool:
    return os.getenv("PHYSICSLAB_CODESEE_HARNESS", "0") == "1"


def fake_pack_enabled() -> bool:
    return _FAKE_PACK_ENABLED


def toggle_fake_pack() -> bool:
    global _FAKE_PACK_ENABLED
    _FAKE_PACK_ENABLED = not _FAKE_PACK_ENABLED
    return _FAKE_PACK_ENABLED


def emit_test_activity(
    hub: CodeSeeRuntimeHub,
    *,
    source_id: Optional[str],
    target_id: Optional[str],
    node_ids: List[str],
) -> None:
    if not hub:
        return
    ts = time.time()
    span_id = f"harness.span.{int(ts * 1000)}"
    hub.publish_span_start(
        SpanStart(
            span_id=span_id,
            label="Harness activity",
            node_id=target_id or (node_ids[-1] if node_ids else "system:app_ui"),
            source_id=source_id or "system:app_ui",
            severity="info",
            ts=ts,
        )
    )
    hub.publish(
        CodeSeeEvent(
            ts=_ts_label(ts),
            kind=EVENT_APP_ACTIVITY,
            severity="info",
            message="Harness activity event",
            node_ids=list(node_ids),
            source="codesee.harness",
            source_node_id=source_id,
            target_node_id=target_id,
        )
    )
    if node_ids:
        hub.publish_test_pulse(node_ids=node_ids)
    hub.publish_span_update(
        SpanUpdate(
            span_id=span_id,
            progress=0.6,
            message="Harness progress",
            ts=ts + 0.1,
        )
    )
    hub.publish_span_end(
        SpanEnd(
            span_id=span_id,
            status="completed",
            message="Harness completed",
            ts=ts + 0.2,
        )
    )


def emit_mismatch(hub: CodeSeeRuntimeHub, *, node_id: str) -> None:
    if not hub:
        return
    check = build_check(
        check_id=f"harness.mismatch.{int(time.time() * 1000)}",
        node_id=node_id,
        expected={"value": 10, "mode": "exact"},
        actual={"value": 7},
        mode="exact",
        message="Harness mismatch: expected 10, got 7",
        context={"source": "codesee.harness"},
    )
    hub.publish_expect_check(check)


def write_fake_crash(workspace_id: str) -> Optional[str]:
    record = {
        "format_version": 1,
        "ts": time.time(),
        "workspace_id": workspace_id,
        "where": "harness",
        "exception_type": "HarnessCrash",
        "message": "Synthetic crash record for Code See verification.",
        "traceback": "Traceback (most recent call last):\n  <harness>\nHarnessCrash: synthetic",
        "app": {
            "python": os.sys.version.split()[0],
            "platform": os.sys.platform,
            "pid": os.getpid(),
        },
        "build": versioning.get_build_info(),
    }
    try:
        path = crash_io.write_latest_crash(workspace_id, record)
    except Exception:
        return None
    return str(path) if path else None


def pick_pulse_nodes(node_ids: List[str]) -> Tuple[Optional[str], Optional[str], List[str]]:
    if not node_ids:
        return None, None, []
    preferred = ["system:app_ui", "system:runtime_bus", "system:core_center", "system:content_system"]
    source = _first_match(node_ids, preferred)
    target = _first_match(node_ids, ["system:runtime_bus", "system:app_ui"]) or source
    if not source:
        source = node_ids[0]
    if not target:
        target = node_ids[-1]
    ids = [source, target] if source and target and source != target else [source]
    return source, target, ids


def _first_match(items: List[str], preferred: List[str]) -> Optional[str]:
    for key in preferred:
        if key in items:
            return key
    return None


def _ts_label(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def build_trail_visual_self_test_events(*, trace_id: str) -> list[CodeSeeEvent]:
    trace = str(trace_id or "").strip() or "trace-self-test"
    ts = _ts_label(time.time())
    events = [
        CodeSeeEvent(
            ts=ts,
            kind=EVENT_SPAN_START,
            severity="info",
            message="Self-test span running",
            node_ids=["system:core_center"],
            source="codesee.harness",
            source_node_id="system:runtime_bus",
            target_node_id="system:core_center",
            payload={"span_id": f"{trace}.run", "status": "active"},
        ),
        CodeSeeEvent(
            ts=ts,
            kind=EVENT_SPAN_START,
            severity="info",
            message="Self-test span degraded candidate",
            node_ids=["system:component_runtime"],
            source="codesee.harness",
            source_node_id="system:runtime_bus",
            target_node_id="system:component_runtime",
            payload={"span_id": f"{trace}.degraded", "status": "active"},
        ),
        CodeSeeEvent(
            ts=ts,
            kind=EVENT_JOB_UPDATE,
            severity="error",
            message="Self-test degraded error #1",
            node_ids=["system:component_runtime"],
            source="codesee.harness",
            source_node_id="system:runtime_bus",
            target_node_id="system:component_runtime",
            payload={"self_test": "trail"},
        ),
        CodeSeeEvent(
            ts=ts,
            kind=EVENT_JOB_UPDATE,
            severity="error",
            message="Self-test degraded error #2",
            node_ids=["system:component_runtime"],
            source="codesee.harness",
            source_node_id="system:runtime_bus",
            target_node_id="system:component_runtime",
            payload={"self_test": "trail"},
        ),
        CodeSeeEvent(
            ts=ts,
            kind=EVENT_APP_ERROR,
            severity="error",
            message="Self-test fatal marker",
            node_ids=["system:content_system"],
            source="codesee.harness",
            source_node_id="system:runtime_bus",
            target_node_id="system:content_system",
            payload={"self_test": "trail"},
        ),
        CodeSeeEvent(
            ts=ts,
            kind=EVENT_BUS_REQUEST,
            severity="info",
            message="Self-test trace request 1",
            node_ids=["system:core_center"],
            source="runtime_bus",
            source_node_id="system:runtime_bus",
            target_node_id="system:core_center",
            payload={"trace_id": trace, "topic": "core.jobs.list.request", "phase": "request"},
        ),
        CodeSeeEvent(
            ts=ts,
            kind=EVENT_BUS_REPLY,
            severity="info",
            message="Self-test trace reply 1",
            node_ids=["system:component_runtime"],
            source="runtime_bus",
            source_node_id="system:core_center",
            target_node_id="system:component_runtime",
            payload={"trace_id": trace, "topic": "core.jobs.list.reply", "phase": "reply"},
        ),
        CodeSeeEvent(
            ts=ts,
            kind=EVENT_BUS_REPLY,
            severity="info",
            message="Self-test trace reply 2",
            node_ids=["system:app_ui"],
            source="runtime_bus",
            source_node_id="system:component_runtime",
            target_node_id="system:app_ui",
            payload={"trace_id": trace, "topic": "app.activity.reply", "phase": "reply"},
        ),
    ]
    return events


def evaluate_trail_visual_self_test_logic(
    *,
    inactive_node_opacity: float = 0.40,
    inactive_edge_opacity: float = 0.20,
    monitor_border_px: int = 2,
) -> dict:
    trace_id = "trace-self-test"
    events = build_trail_visual_self_test_events(trace_id=trace_id)
    monitor = MonitorState(span_stuck_seconds=10, follow_last_trace=True)
    for event in events:
        monitor.on_event(event)
    states = monitor.snapshot_states()
    trace_edges, trace_nodes, active_trace_id = monitor.snapshot_trace()
    visible_nodes = {
        "system:runtime_bus",
        "system:core_center",
        "system:component_runtime",
        "system:app_ui",
        "system:content_system",
        "system:ui_system",
    }
    visible_edges = {
        ("system:runtime_bus", "system:core_center"),
        ("system:core_center", "system:component_runtime"),
        ("system:component_runtime", "system:app_ui"),
        ("system:ui_system", "system:content_system"),
    }
    overlay = compute_trail_focus(
        visible_nodes=visible_nodes,
        visible_edges=visible_edges,
        monitor_states=states,
        trace_nodes=trace_nodes,
        trace_edges=trace_edges,
        selected_node_ids=set(),
        enabled=True,
        inactive_node_opacity=inactive_node_opacity,
        inactive_edge_opacity=inactive_edge_opacity,
    )
    checks = {
        "running_core_center": str(states.get("system:core_center", {}).get("state")) == STATE_RUNNING,
        "degraded_component_runtime": str(states.get("system:component_runtime", {}).get("state")) == STATE_DEGRADED,
        "fatal_content_system": str(states.get("system:content_system", {}).get("state")) == STATE_FATAL,
        "active_trace_set": active_trace_id == trace_id and len(trace_edges) >= 2,
        "foreground_node_opacity": float(overlay.node_opacity.get("system:core_center", 0.0)) == 1.0,
        "inactive_node_opacity": float(overlay.node_opacity.get("system:ui_system", 0.0))
        == clamp_inactive_node_opacity(inactive_node_opacity),
        "inactive_edge_opacity": float(
            overlay.edge_opacity.get(("system:ui_system", "system:content_system"), 0.0)
        )
        == clamp_inactive_edge_opacity(inactive_edge_opacity),
        "monitor_border_px_clamped": clamp_monitor_border_px(monitor_border_px) >= 1,
    }
    return {
        "ok": all(checks.values()),
        "trace_id": active_trace_id,
        "checks": checks,
        "states": {key: value.get("state") for key, value in states.items()},
        "focus_nodes": sorted(overlay.focus_nodes),
        "focus_edges": sorted(list(overlay.focus_edges)),
    }


def emit_trail_visual_self_test(hub: CodeSeeRuntimeHub, *, trace_id: str = "trace-self-test") -> dict:
    if not hub:
        return {"ok": False, "error": "runtime_hub_unavailable"}
    events = build_trail_visual_self_test_events(trace_id=trace_id)
    for event in events:
        if event.kind == EVENT_SPAN_START and isinstance(event.payload, dict):
            span_id = str(event.payload.get("span_id") or "").strip()
            if span_id and event.target_node_id:
                hub.publish_span_start(
                    SpanStart(
                        span_id=span_id,
                        label=event.message,
                        node_id=event.target_node_id,
                        source_id=event.source_node_id,
                        severity=event.severity,
                        ts=time.time(),
                    )
                )
                continue
        hub.publish(event)
    logic = evaluate_trail_visual_self_test_logic()
    return {
        "ok": bool(logic.get("ok", False)),
        "trace_id": str(trace_id),
        "event_count": len(events),
        "checks": logic.get("checks", {}),
        "summary": (
            f"Trail self-test {'PASS' if logic.get('ok', False) else 'FAIL'} "
            f"(trace={str(trace_id)[:8]})"
        ),
    }
