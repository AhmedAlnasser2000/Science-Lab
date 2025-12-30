from __future__ import annotations

import os
import time
from typing import List, Optional, Tuple

from app_ui import versioning

from . import crash_io
from .expectations import build_check
from .runtime.events import CodeSeeEvent, EVENT_APP_ACTIVITY, SpanEnd, SpanStart, SpanUpdate
from .runtime.hub import CodeSeeRuntimeHub

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
