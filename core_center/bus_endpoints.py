from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

try:
    from runtime_bus import topics as BUS_TOPICS
except Exception:  # pragma: no cover
    BUS_TOPICS = None

from . import job_manager, storage_manager, policy_manager
from .registry import load_registry, summarize_registry

REPORT_REQUEST_TOPIC = getattr(BUS_TOPICS, "CORE_STORAGE_REPORT_REQUEST", "core.storage.report.request")
CLEANUP_REQUEST_TOPIC = getattr(BUS_TOPICS, "CORE_CLEANUP_REQUEST", "core.cleanup.request")
REPORT_READY_TOPIC = getattr(BUS_TOPICS, "CORE_STORAGE_REPORT_READY", "core.storage.report.ready")
CLEANUP_COMPLETED_TOPIC = getattr(BUS_TOPICS, "CORE_CLEANUP_COMPLETED", "core.cleanup.completed")
RUN_DIR_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_STORAGE_ALLOCATE_RUN_DIR_REQUEST", "core.storage.allocate_run_dir.request"
)
POLICY_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_POLICY_GET_REQUEST", "core.policy.get.request"
)
REGISTRY_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_REGISTRY_GET_REQUEST", "core.registry.get.request"
)
MODULE_INSTALL_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_CONTENT_MODULE_INSTALL_REQUEST", "core.content.module.install.request"
)
MODULE_UNINSTALL_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_CONTENT_MODULE_UNINSTALL_REQUEST", "core.content.module.uninstall.request"
)
JOBS_LIST_REQUEST_TOPIC = getattr(BUS_TOPICS, "CORE_JOBS_LIST_REQUEST", "core.jobs.list.request")
JOBS_GET_REQUEST_TOPIC = getattr(BUS_TOPICS, "CORE_JOBS_GET_REQUEST", "core.jobs.get.request")


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

    def _handle_run_dir(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        lab_id = payload.get("lab_id")
        policy = policy_manager.resolve_policy()
        keep_value = policy.get("runs_keep_last_n")
        keep_last_n = keep_value if isinstance(keep_value, int) and keep_value >= 0 else None
        result = storage_manager.allocate_run_dir(lab_id, keep_last_n=keep_last_n)
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error") or "allocate_failed"}
        return {"ok": True, "run_id": result.get("run_id"), "run_dir": result.get("run_dir")}

    def _handle_policy(envelope) -> Dict[str, object]:  # noqa: ARG001
        policy = policy_manager.resolve_policy()
        return {"ok": True, "policy": policy}

    def _handle_registry(envelope) -> Dict[str, object]:  # noqa: ARG001
        path = Path("data/roaming/registry.json")
        records = load_registry(path)
        summary = summarize_registry(records)
        return {"ok": True, "registry": records, "summary": summary}

    def _handle_module_install(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        module_id = payload.get("module_id")
        if not module_id:
            return {"ok": False, "error": "module_id_required"}
        job_id = job_manager.create_job(
            job_manager.JOB_MODULE_INSTALL,
            {"module_id": module_id},
            bus=proxy,
        )
        return {"ok": True, "job_id": job_id}

    def _handle_module_uninstall(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        module_id = payload.get("module_id")
        if not module_id:
            return {"ok": False, "error": "module_id_required"}
        job_id = job_manager.create_job(
            job_manager.JOB_MODULE_UNINSTALL,
            {"module_id": module_id},
            bus=proxy,
        )
        return {"ok": True, "job_id": job_id}

    def _handle_jobs_list(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        limit = payload.get("limit")
        try:
            jobs = job_manager.get_job_history(limit=limit)
            result = {"ok": True, "jobs": jobs or []}
            return result
        except Exception as exc:
            return {"ok": True, "jobs": []}

    def _handle_jobs_get(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        job_id = payload.get("job_id")
        if not job_id:
            return {"ok": False, "error": "job_id_required"}
        record = job_manager.get_job_record(job_id)
        if not record:
            return {"ok": False, "error": "job_not_found"}
        return {"ok": True, "job": record}

    bus.register_handler(REPORT_REQUEST_TOPIC, _handle_report)
    bus.register_handler(CLEANUP_REQUEST_TOPIC, _handle_cleanup)
    if RUN_DIR_REQUEST_TOPIC:
        bus.register_handler(RUN_DIR_REQUEST_TOPIC, _handle_run_dir)
    if POLICY_REQUEST_TOPIC:
        bus.register_handler(POLICY_REQUEST_TOPIC, _handle_policy)
    if REGISTRY_REQUEST_TOPIC:
        bus.register_handler(REGISTRY_REQUEST_TOPIC, _handle_registry)
    if MODULE_INSTALL_REQUEST_TOPIC:
        bus.register_handler(MODULE_INSTALL_REQUEST_TOPIC, _handle_module_install)
    if MODULE_UNINSTALL_REQUEST_TOPIC:
        bus.register_handler(MODULE_UNINSTALL_REQUEST_TOPIC, _handle_module_uninstall)
    if JOBS_LIST_REQUEST_TOPIC:
        bus.register_handler(JOBS_LIST_REQUEST_TOPIC, _handle_jobs_list)
    if JOBS_GET_REQUEST_TOPIC:
        bus.register_handler(JOBS_GET_REQUEST_TOPIC, _handle_jobs_get)
