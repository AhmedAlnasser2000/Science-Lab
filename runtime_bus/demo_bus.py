"""Simple runtime bus demo / smoke test."""

from __future__ import annotations

import threading
import time

from . import topics
from .bus import RuntimeBus


def main() -> None:
    bus = RuntimeBus()

    print("[demo] testing pub/sub")
    received = {}
    event = threading.Event()

    def _on_lab(msg):
        received["payload"] = msg.payload
        event.set()

    sub_id = bus.subscribe(topics.LAB_TELEMETRY, _on_lab)
    bus.publish(topics.LAB_TELEMETRY, {"value": 42}, source="demo", trace_id=None)
    if not event.wait(1):
        raise SystemExit("pub/sub test failed: no message received")
    assert received["payload"]["value"] == 42
    bus.unsubscribe(sub_id)
    print("[demo] pub/sub ok")

    print("[demo] testing request/reply")

    def _req_handler(envelope):
        data = envelope.payload.copy()
        data["handled"] = True
        return {"ok": True, "data": data}

    bus.register_handler(topics.CORE_STORAGE_REPORT_REQUEST, _req_handler)
    response = bus.request(
        topics.CORE_STORAGE_REPORT_REQUEST,
        {"report": "now"},
        source="demo",
        timeout_ms=500,
    )
    assert response["ok"] is True and response["data"]["report"] == "now"
    print("[demo] request/reply ok")

    print("[demo] testing timeout")

    def _slow_handler(envelope):
        time.sleep(0.2)
        return {"ok": True}

    bus.register_handler(topics.CORE_STORAGE_REPORT_READY, _slow_handler)
    response = bus.request(
        topics.CORE_STORAGE_REPORT_READY,
        {"report": "slow"},
        source="demo",
        timeout_ms=50,
    )
    assert response["ok"] is False and response["error"] == "timeout"

    no_handler = bus.request(
        "non.existing.topic",
        {"payload": 1},
        source="demo",
        timeout_ms=100,
    )
    assert no_handler["ok"] is False and no_handler["error"] == "no_handler"
    print("[demo] timeout/absence handling ok")
    print("[demo] runtime bus demo complete")


if __name__ == "__main__":
    main()
