from app_ui.codesee import harness
from app_ui.codesee.runtime.events import (
    EVENT_APP_ERROR,
    EVENT_BUS_REPLY,
    EVENT_BUS_REQUEST,
    EVENT_JOB_UPDATE,
    EVENT_SPAN_START,
)


class _FakeHub:
    def __init__(self) -> None:
        self.span_starts = []
        self.events = []

    def publish_span_start(self, start) -> None:
        self.span_starts.append(start)

    def publish(self, event) -> None:
        self.events.append(event)


def test_build_trail_visual_self_test_events_contains_expected_kinds() -> None:
    events = harness.build_trail_visual_self_test_events(trace_id="trace-unit")
    kinds = [event.kind for event in events]
    assert kinds.count(EVENT_SPAN_START) == 2
    assert kinds.count(EVENT_JOB_UPDATE) == 2
    assert kinds.count(EVENT_APP_ERROR) == 1
    assert kinds.count(EVENT_BUS_REQUEST) == 1
    assert kinds.count(EVENT_BUS_REPLY) >= 2
    assert all((event.payload or {}).get("trace_id", "trace-unit") in ("trace-unit", "") for event in events)


def test_evaluate_trail_visual_self_test_logic_passes() -> None:
    result = harness.evaluate_trail_visual_self_test_logic(
        inactive_node_opacity=0.4,
        inactive_edge_opacity=0.2,
        monitor_border_px=2,
    )
    assert result["ok"] is True
    checks = result["checks"]
    assert checks["running_core_center"] is True
    assert checks["degraded_component_runtime"] is True
    assert checks["fatal_content_system"] is True
    assert checks["active_trace_set"] is True


def test_emit_trail_visual_self_test_publishes_expected_stream() -> None:
    hub = _FakeHub()
    result = harness.emit_trail_visual_self_test(hub, trace_id="trace-test")
    assert result["ok"] is True
    assert len(hub.span_starts) == 2
    kinds = [event.kind for event in hub.events]
    assert EVENT_JOB_UPDATE in kinds
    assert EVENT_APP_ERROR in kinds
    assert EVENT_BUS_REQUEST in kinds
    assert EVENT_BUS_REPLY in kinds
