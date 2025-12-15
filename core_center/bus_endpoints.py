from __future__ import annotations

from typing import Any, Dict

try:
    from runtime_bus import topics as BUS_TOPICS
except Exception:  # pragma: no cover
    BUS_TOPICS = None

from . import job_manager

REPORT_REQUEST_TOPIC = getattr(BUS_TOPICS, "CORE_STORAGE_REPORT_REQUEST", "core.storage.report.request")
CLEANUP_REQUEST_TOPIC = getattr(BUS_TOPICS, "CORE_CLEANUP_REQUEST", "core.cleanup.request")
REPORT_READY_TOPIC = getattr(BUS_TOPICS, "CORE_STORAGE_REPORT_READY", "core.storage.report.ready")
CLEANUP_COMPLETED_TOPIC = getattr(BUS_TOPICS, "CORE_CLEANUP_COMPLETED", "core.cleanup.completed")


class _StickyBusProxy:
    """Proxy adding sticky publish behaviour for selected topics."""

    def __init__(self, base_bus, sticky_topics):
        self._base_bus = base_bus
        self._sticky_topics = set(topic for topic in sticky_topics if topic)

    def publish(self, topic, payload, *, source, trace_id=None, **kwargs):
        sticky = kwargs.pop("sticky", False) or topic in self._sticky_topics
        return self._base_bus.publish(
            topic,
            payload,
            source=source,
            trace_id=trace_id,
            sticky=sticky,
            **kwargs,
        )


def register_core_center_endpoints(bus: Any) -> None:
    """Register Core Center request handlers on the provided bus."""

    if bus is None:
        return

    if getattr(bus, "_core_center_registered", False):
        return
    setattr(bus, "_core_center_registered", True)
    sticky_topics = {REPORT_READY_TOPIC, CLEANUP_COMPLETED_TOPIC}
    proxy = getattr(bus, "_core_center_proxy", None)
    if proxy is None:
        proxy = _StickyBusProxy(bus, sticky_topics)
        setattr(bus, "_core_center_proxy", proxy)

    def _handle_report(envelope) -> Dict[str, object]:
        job_id = job_manager.create_job(
            job_manager.JOB_REPORT_GENERATE,
            envelope.payload or {},
            bus=proxy,
        )
        return {"ok": True, "job_id": job_id}

    def _handle_cleanup(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        kind = (payload.get("kind") or "").lower()
        if kind == "cache":
            job_type = job_manager.JOB_CLEANUP_CACHE
        elif kind == "dumps":
            job_type = job_manager.JOB_CLEANUP_DUMPS
        else:
            return {"ok": False, "error": "unknown_job"}
        job_id = job_manager.create_job(job_type, payload, bus=proxy)
        print(f"[core_center] cleanup job queued kind={kind} job_id={job_id}")
        return {"ok": True, "job_id": job_id}

    bus.register_handler(REPORT_REQUEST_TOPIC, _handle_report)
    bus.register_handler(CLEANUP_REQUEST_TOPIC, _handle_cleanup)
