from app_ui.codesee.runtime.events import (
    CodeSeeEvent,
    EVENT_APP_ERROR,
    EVENT_BUS_REPLY,
    EVENT_BUS_REQUEST,
    EVENT_SPAN_END,
    EVENT_SPAN_START,
)
from app_ui.codesee.runtime.monitor_state import (
    MonitorState,
    STATE_DEGRADED,
    STATE_FATAL,
    STATE_INACTIVE,
    STATE_RUNNING,
    _compute_state,
)


class _Clock:
    def __init__(self) -> None:
        self.value = 1000.0

    def now(self) -> float:
        return self.value

    def step(self, seconds: float) -> None:
        self.value += float(seconds)


def _event(
    *,
    kind: str,
    severity: str = "info",
    node_ids=None,
    payload=None,
    source_node_id=None,
    target_node_id=None,
) -> CodeSeeEvent:
    return CodeSeeEvent(
        ts="2026-02-19 12:00:00",
        kind=kind,
        severity=severity,
        message=kind,
        node_ids=list(node_ids or []),
        payload=payload,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
    )


def test_monitor_state_transitions_and_recovery() -> None:
    clock = _Clock()
    monitor = MonitorState(span_stuck_seconds=10, now_provider=clock.now)
    node = "system:app_ui"

    monitor.on_event(
        _event(
            kind=EVENT_SPAN_START,
            node_ids=[node],
            target_node_id=node,
            payload={"span_id": "s1"},
        )
    )
    states = monitor.snapshot_states()
    assert states[node]["state"] == STATE_RUNNING

    monitor.on_event(
        _event(
            kind="job.update",
            severity="error",
            node_ids=[node],
            target_node_id=node,
        )
    )
    monitor.on_event(
        _event(
            kind="job.update",
            severity="error",
            node_ids=[node],
            target_node_id=node,
        )
    )
    states = monitor.snapshot_states()
    assert states[node]["state"] == STATE_DEGRADED

    monitor.on_event(
        _event(
            kind=EVENT_APP_ERROR,
            severity="error",
            node_ids=[node],
            target_node_id=node,
        )
    )
    states = monitor.snapshot_states()
    assert states[node]["state"] == STATE_FATAL

    monitor.on_event(
        _event(
            kind=EVENT_SPAN_START,
            node_ids=[node],
            target_node_id=node,
            payload={"span_id": "s2"},
        )
    )
    states = monitor.snapshot_states()
    assert states[node]["state"] == STATE_RUNNING

    clock.step(12.0)
    monitor.tick(clock.now())
    states = monitor.snapshot_states()
    assert states[node]["state"] == STATE_DEGRADED

    monitor.on_event(
        _event(
            kind=EVENT_SPAN_END,
            node_ids=[node],
            target_node_id=node,
            payload={"span_id": "s2", "status": "completed"},
        )
    )
    states = monitor.snapshot_states()
    assert states[node]["state"] == STATE_DEGRADED

    monitor.on_event(
        _event(
            kind=EVENT_SPAN_END,
            node_ids=[node],
            target_node_id=node,
            payload={"span_id": "s1", "status": "completed"},
        )
    )
    states = monitor.snapshot_states()
    assert states[node]["state"] == STATE_INACTIVE


def test_monitor_trace_follow_and_pin_behavior() -> None:
    monitor = MonitorState(follow_last_trace=True)
    monitor.on_event(
        _event(
            kind=EVENT_BUS_REQUEST,
            payload={"trace_id": "trace-1"},
            source_node_id="system:runtime_bus",
            target_node_id="system:core_center",
        )
    )
    monitor.on_event(
        _event(
            kind=EVENT_BUS_REPLY,
            payload={"trace_id": "trace-1"},
            source_node_id="system:core_center",
            target_node_id="system:app_ui",
        )
    )
    edges, nodes, trace_id = monitor.snapshot_trace()
    assert trace_id == "trace-1"
    assert edges == [
        ("system:runtime_bus", "system:core_center"),
        ("system:core_center", "system:app_ui"),
    ]
    assert nodes == {"system:runtime_bus", "system:core_center", "system:app_ui"}

    monitor.on_event(
        _event(
            kind=EVENT_BUS_REQUEST,
            payload={"trace_id": "trace-2"},
            source_node_id="system:runtime_bus",
            target_node_id="system:content_system",
        )
    )
    _edges, _nodes, trace_id = monitor.snapshot_trace()
    assert trace_id == "trace-2"

    monitor.pin_trace("trace-1")
    monitor.on_event(
        _event(
            kind=EVENT_BUS_REPLY,
            payload={"trace_id": "trace-3"},
            source_node_id="system:content_system",
            target_node_id="system:app_ui",
        )
    )
    _edges, _nodes, trace_id = monitor.snapshot_trace()
    assert trace_id == "trace-1"

    monitor.unpin_trace()
    _edges, _nodes, trace_id = monitor.snapshot_trace()
    assert trace_id == "trace-3"


def test_monitor_state_priority_order() -> None:
    assert (
        _compute_state(
            fatal=True,
            active=True,
            stuck=True,
            error_count=5,
            repeated_error_threshold=2,
        )
        == STATE_FATAL
    )
    assert (
        _compute_state(
            fatal=False,
            active=True,
            stuck=True,
            error_count=0,
            repeated_error_threshold=2,
        )
        == STATE_DEGRADED
    )
    assert (
        _compute_state(
            fatal=False,
            active=True,
            stuck=False,
            error_count=0,
            repeated_error_threshold=2,
        )
        == STATE_RUNNING
    )
    assert (
        _compute_state(
            fatal=False,
            active=False,
            stuck=False,
            error_count=0,
            repeated_error_threshold=2,
        )
        == STATE_INACTIVE
    )
