from __future__ import annotations

import os
from pathlib import Path

from app_ui.codesee.runtime.events import (
    CodeSeeEvent,
    EVENT_BUS_REPLY,
    EVENT_BUS_REQUEST,
    EVENT_SPAN_END,
    EVENT_SPAN_START,
)
from app_ui.codesee.runtime.monitor_state import MonitorState
from app_ui.codesee.runtime.session_deltas import monitor_transition_deltas, trace_transition_delta
from app_ui.codesee.runtime.session_recording import (
    SessionRecorder,
    SessionRecorderConfig,
    reconstruct_terminal_state,
)
from app_ui.codesee.runtime import session_schema, session_store


class _Clock:
    def __init__(self, value: float = 1700003000.0) -> None:
        self.value = value

    def now(self) -> float:
        return self.value

    def step(self, seconds: float = 0.25) -> None:
        self.value += float(seconds)


def _event(
    kind: str,
    *,
    node_ids: list[str] | None = None,
    payload: dict | None = None,
    source_node_id: str | None = None,
    target_node_id: str | None = None,
) -> CodeSeeEvent:
    return CodeSeeEvent(
        ts="2026-02-24 13:00:00",
        kind=kind,
        severity="info",
        message=kind,
        node_ids=list(node_ids or []),
        payload=dict(payload or {}),
        source_node_id=source_node_id,
        target_node_id=target_node_id,
    )


def _record_transition(recorder: SessionRecorder, monitor: MonitorState, event: CodeSeeEvent) -> None:
    before_states = monitor.snapshot_states()
    before_trace = monitor.snapshot_trace()
    recorder.record_event(event)
    monitor.on_event(event)
    deltas = monitor_transition_deltas(before_states, monitor.snapshot_states(), reason=f"runtime.event:{event.kind}")
    trace_delta = trace_transition_delta(before_trace, monitor.snapshot_trace(), reason=f"runtime.event:{event.kind}")
    if trace_delta:
        deltas.append(trace_delta)
    for delta in deltas:
        recorder.record_state_delta(delta)


def test_reconstruct_terminal_state_from_nearest_keyframe(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    clock = _Clock()
    monitor = MonitorState(now_provider=clock.now)

    def _snapshot() -> dict:
        edges, nodes, trace_id = monitor.snapshot_trace()
        return {
            "graph_state_ref": "graph:runtime",
            "monitor_state": monitor.snapshot_states(),
            "trace_state": {
                "active_trace_id": trace_id,
                "edges": [[src, dst] for src, dst in edges],
                "nodes": sorted(str(node_id) for node_id in nodes),
                "edge_count": len(edges),
                "node_count": len(nodes),
            },
        }

    recorder = SessionRecorder(
        SessionRecorderConfig(workspace_id="default", keyframe_every_records=2),
        now_provider=clock.now,
        snapshot_provider=_snapshot,
    )
    recorder.start_session(session_id="rebuild-ok")

    _record_transition(
        recorder,
        monitor,
        _event(
            EVENT_SPAN_START,
            node_ids=["system:app_ui"],
            payload={"span_id": "s1"},
            target_node_id="system:app_ui",
        ),
    )
    clock.step()
    _record_transition(
        recorder,
        monitor,
        _event(
            EVENT_BUS_REQUEST,
            node_ids=["system:runtime_bus", "system:app_ui"],
            payload={"trace_id": "trace-z"},
            source_node_id="system:runtime_bus",
            target_node_id="system:app_ui",
        ),
    )
    clock.step()
    _record_transition(
        recorder,
        monitor,
        _event(
            EVENT_BUS_REPLY,
            node_ids=["system:app_ui", "system:runtime_bus"],
            payload={"trace_id": "trace-z"},
            source_node_id="system:app_ui",
            target_node_id="system:runtime_bus",
        ),
    )
    clock.step()
    _record_transition(
        recorder,
        monitor,
        _event(
            EVENT_SPAN_END,
            node_ids=["system:app_ui"],
            payload={"span_id": "s1", "status": "completed"},
            target_node_id="system:app_ui",
        ),
    )
    clock.step()
    recorder.stop_session(status=session_schema.SESSION_STATUS_COMPLETE)

    session_root = recorder.session_dir()
    assert session_root is not None
    rebuilt = reconstruct_terminal_state(session_root)

    expected_monitor = monitor.snapshot_states()
    expected_edges, expected_nodes, expected_trace_id = monitor.snapshot_trace()
    expected_trace = {
        "active_trace_id": expected_trace_id,
        "edges": expected_edges,
        "nodes": sorted(str(node_id) for node_id in expected_nodes),
        "edge_count": len(expected_edges),
        "node_count": len(expected_nodes),
    }
    assert rebuilt["monitor_state"] == expected_monitor
    assert rebuilt["trace_state"] == expected_trace
    assert rebuilt["warnings"] == []


def test_reconstruct_terminal_state_fallback_when_stop_keyframe_corrupt(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    clock = _Clock()
    monitor = MonitorState(now_provider=clock.now)

    recorder = SessionRecorder(
        SessionRecorderConfig(workspace_id="default", keyframe_every_records=100),
        now_provider=clock.now,
        snapshot_provider=lambda: {"monitor_state": monitor.snapshot_states()},
    )
    recorder.start_session(session_id="rebuild-fallback")

    _record_transition(
        recorder,
        monitor,
        _event(
            EVENT_SPAN_START,
            node_ids=["system:app_ui"],
            payload={"span_id": "s2"},
            target_node_id="system:app_ui",
        ),
    )
    clock.step()
    _record_transition(
        recorder,
        monitor,
        _event(
            EVENT_BUS_REQUEST,
            node_ids=["system:runtime_bus", "system:app_ui"],
            payload={"trace_id": "trace-fallback"},
            source_node_id="system:runtime_bus",
            target_node_id="system:app_ui",
        ),
    )
    clock.step()
    _record_transition(
        recorder,
        monitor,
        _event(
            EVENT_SPAN_END,
            node_ids=["system:app_ui"],
            payload={"span_id": "s2", "status": "completed"},
            target_node_id="system:app_ui",
        ),
    )
    recorder.stop_session(status=session_schema.SESSION_STATUS_COMPLETE)

    session_root = recorder.session_dir()
    assert session_root is not None

    rows, _ = session_store.read_jsonl(session_store.records_path(session_root))
    keyframe_rows = [row for row in rows if row.get("type") == session_schema.RECORD_KEYFRAME_REF]
    assert keyframe_rows
    bad_keyframe = session_root / "keyframes" / str(keyframe_rows[-1]["filename"])
    bad_keyframe.write_text("{not-json", encoding="utf-8")

    rebuilt = reconstruct_terminal_state(session_root)
    node_state = rebuilt["monitor_state"].get("system:app_ui") or {}
    assert node_state.get("state") == "INACTIVE"
    assert bool(node_state.get("active")) is False
    assert rebuilt["trace_state"]["active_trace_id"] == "trace-fallback"
    assert rebuilt["warnings"]
