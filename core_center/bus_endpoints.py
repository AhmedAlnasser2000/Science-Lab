from __future__ import annotations

from typing import Any, Dict

try:
    from runtime_bus import topics as BUS_TOPICS
except Exception:  # pragma: no cover
    BUS_TOPICS = None

from . import job_manager

REPORT_REQUEST_TOPIC = getattr(BUS_TOPICS, "CORE_STORAGE_REPORT_REQUEST", "core.storage.report.request")
CLEANUP_REQUEST_TOPIC = getattr(BUS_TOPICS, "CORE_CLEANUP_REQUEST", "core.cleanup.request")


def register_core_center_endpoints(bus: Any) -> None:
    """Register Core Center request handlers on the provided bus."""

    if bus is None:
        return

    if getattr(bus, "_core_center_registered", False):
        return
    setattr(bus, "_core_center_registered", True)

    def _handle_report(envelope) -> Dict[str, object]:
        job_id = job_manager.create_job(
            job_manager.JOB_REPORT_GENERATE,
            envelope.payload or {},
            bus=bus,
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
        job_id = job_manager.create_job(job_type, payload, bus=bus)
        return {"ok": True, "job_id": job_id}

    bus.register_handler(REPORT_REQUEST_TOPIC, _handle_report)
    bus.register_handler(CLEANUP_REQUEST_TOPIC, _handle_cleanup)
