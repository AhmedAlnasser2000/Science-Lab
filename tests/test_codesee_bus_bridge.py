from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app_ui.codesee.runtime import bus_bridge


@dataclass
class _Envelope:
    topic: str
    payload: dict[str, Any]
    trace_id: str = "trace-test"
    timestamp: str = "2026-02-21 16:00:00"


class _FakeHub:
    def __init__(self) -> None:
        self.span_starts = []
        self.span_updates = []
        self.span_ends = []
        self.events = []
        self.trails = []
        self.bus_connected = False

    def set_bus_connected(self, value: bool) -> None:
        self.bus_connected = bool(value)

    def publish_span_start(self, start) -> None:
        self.span_starts.append(start)

    def publish_span_update(self, update) -> None:
        self.span_updates.append(update)

    def publish_span_end(self, end) -> None:
        self.span_ends.append(end)

    def publish(self, event) -> None:
        self.events.append(event)

    def publish_trail(self, event, *, count: int, spacing_ms: int, trail_kind: str, transient: bool) -> None:
        self.trails.append(
            {
                "event": event,
                "count": int(count),
                "spacing_ms": int(spacing_ms),
                "trail_kind": str(trail_kind),
                "transient": bool(transient),
            }
        )


def test_content_span_id_matches_between_progress_and_completed() -> None:
    hub = _FakeHub()
    bridge = bus_bridge.BusBridge(bus=None, hub=hub)
    progress = _Envelope(
        topic=bus_bridge.TOPIC_CONTENT_PROGRESS,
        payload={"module_id": "gravity_demo", "percent": 50, "stage": "installing"},
    )
    bridge._on_content_progress(progress)

    assert len(hub.span_starts) == 1
    span_id = hub.span_starts[0].span_id
    assert span_id == "content:gravity_demo"
    assert bridge._active_content_span_ids["gravity_demo"] == span_id

    completed = _Envelope(
        topic=bus_bridge.TOPIC_CONTENT_COMPLETED,
        payload={"module_id": "gravity_demo", "action": "install", "ok": True},
    )
    bridge._on_content_completed(completed)

    assert len(hub.span_ends) == 1
    assert hub.span_ends[0].span_id == span_id
    assert span_id not in bridge._active_spans
    assert "gravity_demo" not in bridge._active_content_span_ids


def test_lab_run_stop_without_run_id_closes_auto_started_span() -> None:
    hub = _FakeHub()
    bridge = bus_bridge.BusBridge(bus=None, hub=hub)
    started = _Envelope(
        topic=bus_bridge.TOPIC_LAB_RUN_STARTED,
        payload={"lab_id": "gravity"},
    )
    bridge._on_lab_run_started(started)

    assert len(hub.span_starts) == 1
    started_span_id = hub.span_starts[0].span_id
    assert started_span_id.startswith("run:gravity:auto-")
    assert hub.span_starts[0].node_id == "block:labhost:gravity"

    stopped = _Envelope(
        topic=bus_bridge.TOPIC_LAB_RUN_STOPPED,
        payload={"lab_id": "gravity"},
    )
    bridge._on_lab_run_stopped(stopped)

    assert len(hub.span_ends) == 1
    assert hub.span_ends[0].span_id == started_span_id
    assert not any(span_id.startswith("run:gravity:") for span_id in bridge._active_spans)


def test_lab_run_stop_with_new_run_id_uses_cached_active_span() -> None:
    hub = _FakeHub()
    bridge = bus_bridge.BusBridge(bus=None, hub=hub)
    started = _Envelope(
        topic=bus_bridge.TOPIC_LAB_RUN_STARTED,
        payload={"lab_id": "vector_add"},
    )
    bridge._on_lab_run_started(started)

    started_span_id = hub.span_starts[0].span_id
    stopped = _Envelope(
        topic=bus_bridge.TOPIC_LAB_RUN_STOPPED,
        payload={"lab_id": "vector_add", "run_id": "run-42"},
    )
    bridge._on_lab_run_stopped(stopped)

    assert hub.span_ends[0].span_id == started_span_id
    assert started_span_id not in bridge._active_spans
