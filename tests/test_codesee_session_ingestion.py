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
from app_ui.codesee.runtime.session_deltas import (
    monitor_transition_deltas,
    trace_transition_delta,
)
from app_ui.codesee.runtime.session_recording import SessionRecorder, SessionRecorderConfig
from app_ui.codesee.runtime import session_schema, session_store


class _Clock:
    def __init__(self, value: float = 1700002000.0) -> None:
        self.value = value

    def now(self) -> float:
        return self.value

    def step(self, seconds: float = 1.0) -> None:
        self.value += float(seconds)


def _event(
    kind: str,
    *,
    node_ids: list[str] | None = None,
    payload: dict | None = None,
    source_node_id: str | None = None,
    target_node_id: str | None = None,
    severity: str = "info",
) -> CodeSeeEvent:
    return CodeSeeEvent(
        ts="2026-02-24 12:00:00",
        kind=kind,
        severity=severity,
        message=kind,
        node_ids=list(node_ids or []),
        payload=dict(payload or {}),
        source_node_id=source_node_id,
        target_node_id=target_node_id,
    )


def _record_runtime_transition(
    recorder: SessionRecorder,
    monitor: MonitorState,
    event: CodeSeeEvent,
) -> None:
    before_states = monitor.snapshot_states()
    before_trace = monitor.snapshot_trace()

    recorder.record_event(event)
    monitor.on_event(event)

    deltas = monitor_transition_deltas(
        before_states,
        monitor.snapshot_states(),
        reason=f"runtime.event:{event.kind}",
    )
    trace_delta = trace_transition_delta(
        before_trace,
        monitor.snapshot_trace(),
        reason=f"runtime.event:{event.kind}",
    )
    if trace_delta:
        deltas.append(trace_delta)

    for delta in deltas:
        recorder.record_state_delta(delta)


def test_monitor_transition_deltas_detect_state_change() -> None:
    before = {}
    after = {
        "system:core_center": {
            "state": "RUNNING",
            "active": True,
            "stuck": False,
            "fatal": False,
        }
    }

    deltas = monitor_transition_deltas(before, after, reason="unit")
    assert len(deltas) == 1
    assert deltas[0]["delta_type"] == "monitor.state.transition"
    assert deltas[0]["before_ref"] == "INACTIVE"
    assert deltas[0]["after_ref"] == "RUNNING"


def test_trace_transition_delta_only_when_changed() -> None:
    same = trace_transition_delta(([], set(), None), ([], set(), None), reason="unit")
    assert same is None

    changed = trace_transition_delta(([], set(), None), ([ ("a", "b") ], {"a", "b"}, "t1"), reason="unit")
    assert changed is not None
    assert changed["delta_type"] == "trace.state.transition"
    assert changed["after_ref"] == "t1"


def test_session_ingestion_records_events_and_deltas_in_order(tmp_path: Path) -> None:
    os.chdir(tmp_path)

    clock = _Clock()
    recorder = SessionRecorder(SessionRecorderConfig(workspace_id="default"), now_provider=clock.now)
    monitor = MonitorState(now_provider=clock.now)

    recorder.start_session(session_id="e3")

    _record_runtime_transition(
        recorder,
        monitor,
        _event(
            EVENT_SPAN_START,
            node_ids=["system:core_center"],
            payload={"span_id": "span-1"},
            target_node_id="system:core_center",
        ),
    )
    clock.step(0.25)

    _record_runtime_transition(
        recorder,
        monitor,
        _event(
            EVENT_BUS_REQUEST,
            node_ids=["system:runtime_bus", "system:core_center"],
            payload={"trace_id": "trace-1"},
            source_node_id="system:runtime_bus",
            target_node_id="system:core_center",
        ),
    )
    clock.step(0.25)

    _record_runtime_transition(
        recorder,
        monitor,
        _event(
            EVENT_BUS_REPLY,
            node_ids=["system:core_center", "system:app_ui"],
            payload={"trace_id": "trace-1"},
            source_node_id="system:core_center",
            target_node_id="system:app_ui",
        ),
    )
    clock.step(0.25)

    _record_runtime_transition(
        recorder,
        monitor,
        _event(
            EVENT_SPAN_END,
            node_ids=["system:core_center"],
            payload={"span_id": "span-1", "status": "completed"},
            target_node_id="system:core_center",
        ),
    )
    clock.step(0.25)

    recorder.stop_session(status=session_schema.SESSION_STATUS_COMPLETE)

    session_root = recorder.session_dir()
    assert session_root is not None
    rows, corrupt = session_store.read_jsonl(session_store.records_path(session_root))
    assert corrupt == 0

    event_rows = [row for row in rows if row["type"] == session_schema.RECORD_EVENT]
    delta_rows = [row for row in rows if row["type"] == session_schema.RECORD_DELTA]

    assert len(event_rows) == 4
    assert len(delta_rows) >= 3
    assert any(row["delta_type"] == "trace.state.transition" for row in delta_rows)
    assert any(
        row["delta_type"] == "monitor.state.transition" and row["after_ref"] == "RUNNING"
        for row in delta_rows
    )
    assert any(
        row["delta_type"] == "monitor.state.transition" and row["after_ref"] == "INACTIVE"
        for row in delta_rows
    )

    assert [row["seq"] for row in rows] == list(range(1, len(rows) + 1))
