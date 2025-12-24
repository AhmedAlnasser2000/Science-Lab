from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

try:
    from runtime_bus import topics as BUS_TOPICS
except Exception:  # pragma: no cover
    BUS_TOPICS = None

from . import job_manager, storage_manager, policy_manager, workspace_manager
from . import inventory as inventory_module
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
RUNS_LIST_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_RUNS_LIST_REQUEST", "core.runs.list.request"
)
RUNS_DELETE_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_RUNS_DELETE_REQUEST", "core.runs.delete.request"
)
RUNS_PRUNE_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_RUNS_PRUNE_REQUEST", "core.runs.prune.request"
)
RUNS_DELETE_MANY_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_RUNS_DELETE_MANY_REQUEST", "core.runs.delete_many.request"
)
WORKSPACE_GET_ACTIVE_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_WORKSPACE_GET_ACTIVE_REQUEST", "core.workspace.get_active.request"
)
WORKSPACE_SET_ACTIVE_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_WORKSPACE_SET_ACTIVE_REQUEST", "core.workspace.set_active.request"
)
WORKSPACE_LIST_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_WORKSPACE_LIST_REQUEST", "core.workspace.list.request"
)
WORKSPACE_CREATE_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_WORKSPACE_CREATE_REQUEST", "core.workspace.create.request"
)
WORKSPACE_DELETE_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_WORKSPACE_DELETE_REQUEST", "core.workspace.delete.request"
)
WORKSPACE_TEMPLATES_LIST_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_WORKSPACE_TEMPLATES_LIST_REQUEST", "core.workspace.templates.list.request"
)
INVENTORY_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_INVENTORY_GET_REQUEST", "core.inventory.get.request"
)
MODULE_INSTALL_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_CONTENT_MODULE_INSTALL_REQUEST", "core.content.module.install.request"
)
MODULE_UNINSTALL_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_CONTENT_MODULE_UNINSTALL_REQUEST", "core.content.module.uninstall.request"
)
COMPONENT_PACK_INSTALL_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_COMPONENT_PACK_INSTALL_REQUEST", "core.component_pack.install.request"
)
COMPONENT_PACK_UNINSTALL_REQUEST_TOPIC = getattr(
    BUS_TOPICS, "CORE_COMPONENT_PACK_UNINSTALL_REQUEST", "core.component_pack.uninstall.request"
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

    def _handle_runs_list(envelope) -> Dict[str, object]:  # noqa: ARG001
        try:
            data = storage_manager.list_runs_inventory()
            return {"ok": True, "roots": data.get("roots"), "labs": data.get("labs")}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _handle_runs_delete(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        lab_id = payload.get("lab_id")
        run_id = payload.get("run_id")
        root_kind = payload.get("root_kind") or "runs"
        if not lab_id or not run_id:
            return {"ok": False, "error": "lab_id_and_run_id_required"}
        result = storage_manager.delete_run(str(lab_id), str(run_id), str(root_kind))
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error") or "delete_failed"}
        return {"ok": True}

    def _handle_runs_prune(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        use_policy = payload.get("use_policy", True)
        keep_last = payload.get("keep_last_per_lab")
        older_than = payload.get("delete_older_than_days")
        max_total_mb = payload.get("max_total_mb")
        if use_policy:
            policy = policy_manager.resolve_policy()
            cleanup = (policy.get("runs") or {}).get("cleanup") or {}
            keep_last = cleanup.get("keep_last_per_lab", keep_last)
            older_than = cleanup.get("delete_older_than_days", older_than)
            max_total_mb = cleanup.get("max_total_mb", max_total_mb)
        result = storage_manager.prune_runs(
            keep_last_per_lab=keep_last,
            delete_older_than_days=older_than,
            max_total_mb=max_total_mb,
        )
        return {"ok": True, "summary": result}

    def _handle_runs_delete_many(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        items = payload.get("items") or []
        result = storage_manager.delete_runs_many(items)
        return {"ok": True, **result}

    def _handle_workspace_get_active(envelope) -> Dict[str, object]:  # noqa: ARG001
        try:
            info = workspace_manager.get_active_workspace()
            return {"ok": True, "workspace": info}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _handle_workspace_set_active(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        workspace_id = payload.get("workspace_id") or payload.get("id")
        if not workspace_id:
            return {"ok": False, "error": "workspace_id_required"}
        try:
            info = workspace_manager.set_active_workspace(str(workspace_id))
            return {"ok": True, "workspace": info}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _handle_workspace_list(envelope) -> Dict[str, object]:  # noqa: ARG001
        try:
            workspaces = workspace_manager.list_workspaces()
            return {"ok": True, "workspaces": workspaces}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _handle_workspace_create(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        workspace_id = payload.get("workspace_id") or payload.get("id")
        if not workspace_id:
            return {"ok": False, "error": "workspace_id_required"}
        try:
            info = workspace_manager.create_workspace(
                str(workspace_id),
                name=payload.get("name"),
                template_id=payload.get("template_id"),
            )
            return {"ok": True, "workspace": info}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _handle_workspace_delete(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        workspace_id = payload.get("workspace_id") or payload.get("id")
        force = bool(payload.get("force", False))
        if not workspace_id:
            return {"ok": False, "error": "workspace_id_required"}
        result = workspace_manager.delete_workspace(str(workspace_id), force=force)
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error") or "delete_failed"}
        return {"ok": True}

    def _handle_workspace_templates(envelope) -> Dict[str, object]:  # noqa: ARG001
        try:
            templates = workspace_manager.list_templates()
            return {"ok": True, "templates": templates}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _handle_inventory(envelope) -> Dict[str, object]:  # noqa: ARG001
        try:
            snapshot = inventory_module.get_inventory_snapshot()
            return {"ok": True, "inventory": snapshot}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

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

    def _handle_component_pack_install(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        pack_id = payload.get("pack_id")
        if not pack_id:
            return {"ok": False, "error": "pack_id_required"}
        job_id = job_manager.create_job(
            job_manager.JOB_COMPONENT_PACK_INSTALL,
            {"pack_id": pack_id},
            bus=proxy,
        )
        return {"ok": True, "job_id": job_id}

    def _handle_component_pack_uninstall(envelope) -> Dict[str, object]:
        payload = envelope.payload or {}
        pack_id = payload.get("pack_id")
        if not pack_id:
            return {"ok": False, "error": "pack_id_required"}
        job_id = job_manager.create_job(
            job_manager.JOB_COMPONENT_PACK_UNINSTALL,
            {"pack_id": pack_id},
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
    if RUNS_LIST_REQUEST_TOPIC:
        bus.register_handler(RUNS_LIST_REQUEST_TOPIC, _handle_runs_list)
    if RUNS_DELETE_REQUEST_TOPIC:
        bus.register_handler(RUNS_DELETE_REQUEST_TOPIC, _handle_runs_delete)
    if RUNS_PRUNE_REQUEST_TOPIC:
        bus.register_handler(RUNS_PRUNE_REQUEST_TOPIC, _handle_runs_prune)
    if RUNS_DELETE_MANY_REQUEST_TOPIC:
        bus.register_handler(RUNS_DELETE_MANY_REQUEST_TOPIC, _handle_runs_delete_many)
    if WORKSPACE_GET_ACTIVE_REQUEST_TOPIC:
        bus.register_handler(WORKSPACE_GET_ACTIVE_REQUEST_TOPIC, _handle_workspace_get_active)
    if WORKSPACE_SET_ACTIVE_REQUEST_TOPIC:
        bus.register_handler(WORKSPACE_SET_ACTIVE_REQUEST_TOPIC, _handle_workspace_set_active)
    if WORKSPACE_LIST_REQUEST_TOPIC:
        bus.register_handler(WORKSPACE_LIST_REQUEST_TOPIC, _handle_workspace_list)
    if WORKSPACE_CREATE_REQUEST_TOPIC:
        bus.register_handler(WORKSPACE_CREATE_REQUEST_TOPIC, _handle_workspace_create)
    if WORKSPACE_DELETE_REQUEST_TOPIC:
        bus.register_handler(WORKSPACE_DELETE_REQUEST_TOPIC, _handle_workspace_delete)
    if WORKSPACE_TEMPLATES_LIST_REQUEST_TOPIC:
        bus.register_handler(WORKSPACE_TEMPLATES_LIST_REQUEST_TOPIC, _handle_workspace_templates)
    if INVENTORY_REQUEST_TOPIC:
        bus.register_handler(INVENTORY_REQUEST_TOPIC, _handle_inventory)
    if MODULE_INSTALL_REQUEST_TOPIC:
        bus.register_handler(MODULE_INSTALL_REQUEST_TOPIC, _handle_module_install)
    if MODULE_UNINSTALL_REQUEST_TOPIC:
        bus.register_handler(MODULE_UNINSTALL_REQUEST_TOPIC, _handle_module_uninstall)
    if COMPONENT_PACK_INSTALL_REQUEST_TOPIC:
        bus.register_handler(COMPONENT_PACK_INSTALL_REQUEST_TOPIC, _handle_component_pack_install)
    if COMPONENT_PACK_UNINSTALL_REQUEST_TOPIC:
        bus.register_handler(COMPONENT_PACK_UNINSTALL_REQUEST_TOPIC, _handle_component_pack_uninstall)
    if JOBS_LIST_REQUEST_TOPIC:
        bus.register_handler(JOBS_LIST_REQUEST_TOPIC, _handle_jobs_list)
    if JOBS_GET_REQUEST_TOPIC:
        bus.register_handler(JOBS_GET_REQUEST_TOPIC, _handle_jobs_get)
