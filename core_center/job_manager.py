from __future__ import annotations

import threading
import uuid
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Optional, List

try:
    from runtime_bus import topics as BUS_TOPICS
except Exception:  # pragma: no cover
    BUS_TOPICS = None

from .cleanup import purge_cache, prune_dumps
from .discovery import discover_components, ensure_data_roots
from .registry import load_registry, save_registry, upsert_records
from .storage_report import format_report_text, generate_report

JOB_REPORT_GENERATE = "core.report.generate"
JOB_CLEANUP_CACHE = "core.cleanup.cache"
JOB_CLEANUP_DUMPS = "core.cleanup.dumps"
JOB_MODULE_INSTALL = "core.module.install"
JOB_MODULE_UNINSTALL = "core.module.uninstall"

REPORT_READY_TOPIC = getattr(BUS_TOPICS, "CORE_STORAGE_REPORT_READY", "core.storage.report.ready")
CLEANUP_STARTED_TOPIC = getattr(BUS_TOPICS, "CORE_CLEANUP_STARTED", "core.cleanup.started")
CLEANUP_COMPLETED_TOPIC = getattr(BUS_TOPICS, "CORE_CLEANUP_COMPLETED", "core.cleanup.completed")
JOB_STARTED_TOPIC = getattr(BUS_TOPICS, "JOB_STARTED", "job.started")
JOB_PROGRESS_TOPIC = getattr(BUS_TOPICS, "JOB_PROGRESS", "job.progress")
JOB_COMPLETED_TOPIC = getattr(BUS_TOPICS, "JOB_COMPLETED", "job.completed")
CONTENT_INSTALL_PROGRESS_TOPIC = getattr(BUS_TOPICS, "CONTENT_INSTALL_PROGRESS", "content.install.progress")
CONTENT_INSTALL_COMPLETED_TOPIC = getattr(BUS_TOPICS, "CONTENT_INSTALL_COMPLETED", "content.install.completed")

JobHandler = Callable[[Dict[str, Any], "JobContext"], Dict[str, Any]]

_JOB_HANDLERS: Dict[str, JobHandler] = {}
_RUNNING_JOBS: Dict[str, threading.Thread] = {}
_JOB_STATE: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


class JobContext:
    def __init__(self, job_id: str, job_type: str, bus: Any, source: str):
        self.job_id = job_id
        self.job_type = job_type
        self.bus = bus
        self.source = source

    def progress(self, percent: float, stage: str) -> None:
        _update_job_state(self.job_id, {"progress": percent, "stage": stage})
        _publish(
            self.bus,
            JOB_PROGRESS_TOPIC,
            {"job_id": self.job_id, "job_type": self.job_type, "percent": percent, "stage": stage},
            self.source,
        )

    def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        data = dict(payload)
        data.setdefault("job_id", self.job_id)
        _publish(self.bus, topic, data, self.source)


def register_job_handler(job_type: str, handler: JobHandler) -> None:
    _JOB_HANDLERS[job_type] = handler


def create_job(job_type: str, payload: Optional[Dict[str, Any]], *args, bus: Any = None, source: str = "core_center") -> str:
    if args:
        if len(args) > 1:
            raise TypeError("create_job accepts at most one positional argument after payload")
        if bus is not None:
            raise TypeError("bus must be provided once (prefer keyword)")
        bus = args[0]
    return _create_job_impl(job_type, payload, bus=bus, source=source)


def _create_job_impl(job_type: str, payload: Optional[Dict[str, Any]], *, bus: Any = None, source: str = "core_center") -> str:
    job_id = str(uuid.uuid4())
    runner = threading.Thread(
        target=_run_job,
        args=(job_id, job_type, payload or {}, bus, source),
        name=f"core-center-job-{job_type}-{job_id}",
        daemon=True,
    )
    with _LOCK:
        _RUNNING_JOBS[job_id] = runner
        _JOB_STATE[job_id] = {
            "job_id": job_id,
            "job_type": job_type,
            "status": "pending",
            "progress": 0.0,
            "result": None,
            "error": None,
        }
    runner.start()
    return job_id


def _update_job_state(job_id: str, updates: Dict[str, Any]) -> None:
    with _LOCK:
        state = _JOB_STATE.get(job_id)
        if not state:
            return
        state.update(updates)


def cancel_job(job_id: str) -> bool:
    # Future enhancement; for now we do not cancel running jobs.
    return False


def _run_job(job_id: str, job_type: str, payload: Dict[str, Any], bus: Any, source: str) -> None:
    _update_job_state(job_id, {"status": "running"})
    _publish(bus, JOB_STARTED_TOPIC, {"job_id": job_id, "job_type": job_type}, source)
    handler = _JOB_HANDLERS.get(job_type)
    context = JobContext(job_id, job_type, bus, source)
    ok = False
    result: Dict[str, Any] = {}
    error_msg = ""
    if handler is None:
        error_msg = "unknown_job"
    else:
        try:
            result = handler(payload, context) or {}
            ok = True
        except Exception as exc:  # pragma: no cover - defensive
            error_msg = str(exc)
    if not ok and job_type == JOB_REPORT_GENERATE:
        context.publish(REPORT_READY_TOPIC, {"ok": False, "error": error_msg or "failed"})
    _update_job_state(job_id, {"status": "completed", "result": result if ok else None, "error": error_msg if not ok else None})
    _publish(
        bus,
        JOB_COMPLETED_TOPIC,
        {"job_id": job_id, "job_type": job_type, "ok": ok, "result": result if ok else None, "error": error_msg if not ok else None},
        source,
    )
    with _LOCK:
        _RUNNING_JOBS.pop(job_id, None)


def _publish(bus: Any, topic: Optional[str], payload: Dict[str, Any], source: str) -> None:
    if not bus or not topic:
        return
    try:
        bus.publish(topic, payload, source=source, trace_id=None)
    except Exception:  # pragma: no cover - defensive
        return


def _refresh_registry_records() -> List[Dict[str, Any]]:
    ensure_data_roots()
    registry_path = Path("data/roaming/registry.json")
    existing = load_registry(registry_path)
    discovered = discover_components()
    merged = upsert_records(existing, discovered)
    save_registry(registry_path, merged)
    return merged


def _module_progress(ctx: JobContext, module_id: str, percent: float, stage: str) -> None:
    ctx.progress(percent, stage)
    ctx.publish(
        CONTENT_INSTALL_PROGRESS_TOPIC,
        {"module_id": module_id, "percent": percent, "stage": stage},
    )


def _module_completed(ctx: JobContext, module_id: str, action: str, ok: bool, **extra) -> None:
    payload = {"module_id": module_id, "action": action, "ok": ok}
    payload.update(extra)
    ctx.publish(CONTENT_INSTALL_COMPLETED_TOPIC, payload)


def _validate_module_id(payload: Dict[str, Any]) -> str:
    module_id = str(payload.get("module_id") or "").strip()
    if not module_id:
        raise ValueError("module_id_required")
    if any(sep in module_id for sep in ("/", "\\", "..")):
        raise ValueError("invalid_module_id")
    return module_id


def _handle_report_job(payload: Dict[str, Any], ctx: JobContext) -> Dict[str, Any]:
    ctx.progress(5, "preparing")
    ensure_data_roots()
    registry_path = Path("data/roaming/registry.json")
    existing = load_registry(registry_path)
    ctx.progress(20, "discovering")
    discovered = discover_components()
    merged = upsert_records(existing, discovered)
    save_registry(registry_path, merged)
    ctx.progress(70, "building_report")
    report = generate_report(merged)
    text = format_report_text(report)
    ctx.progress(95, "ready")
    ctx.publish(REPORT_READY_TOPIC, {"text": text, "json": report, "ok": True})
    return {"text": text, "json": report}


def _handle_cleanup_cache(payload: Dict[str, Any], ctx: JobContext) -> Dict[str, Any]:
    ctx.publish(CLEANUP_STARTED_TOPIC, {"kind": "cache"})
    ensure_data_roots()
    path = Path(payload.get("path", "data/cache"))
    try:
        result = purge_cache(path)
    except Exception as exc:
        ctx.publish(
            CLEANUP_COMPLETED_TOPIC,
            {"kind": "cache", "freed_bytes": 0, "ok": False, "error": str(exc)},
        )
        raise
    freed = result.get("bytes_freed", 0)
    ctx.publish(
        CLEANUP_COMPLETED_TOPIC,
        {"kind": "cache", "freed_bytes": freed, "ok": True, "result": result},
    )
    return {"freed_bytes": freed, "result": result}


def _handle_cleanup_dumps(payload: Dict[str, Any], ctx: JobContext) -> Dict[str, Any]:
    ctx.publish(CLEANUP_STARTED_TOPIC, {"kind": "dumps"})
    ensure_data_roots()
    path = Path(payload.get("path", "data/dumps"))
    max_age = payload.get("max_age_days")
    max_total_bytes = payload.get("max_total_bytes")
    try:
        result = prune_dumps(path, max_age_days=max_age, max_total_bytes=max_total_bytes)
    except Exception as exc:
        ctx.publish(
            CLEANUP_COMPLETED_TOPIC,
            {"kind": "dumps", "freed_bytes": 0, "ok": False, "error": str(exc)},
        )
        raise
    freed = result.get("bytes_freed", 0)
    ctx.publish(
        CLEANUP_COMPLETED_TOPIC,
        {"kind": "dumps", "freed_bytes": freed, "ok": True, "result": result},
    )
    return {"freed_bytes": freed, "result": result}


def _handle_module_install(payload: Dict[str, Any], ctx: JobContext) -> Dict[str, Any]:
    module_id = _validate_module_id(payload)
    source_dir = Path("content_repo") / module_id
    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(f"module not found in repo: {module_id}")
    staging_dir = Path("data/cache/module_installs") / module_id / ctx.job_id
    target_dir = Path("content_store") / module_id
    staging_parent = staging_dir.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    store_parent = target_dir.parent
    store_parent.mkdir(parents=True, exist_ok=True)
    try:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        _module_progress(ctx, module_id, 5, "preparing staging")
        shutil.copytree(source_dir, staging_dir)
        _module_progress(ctx, module_id, 55, "staged copy complete")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.move(str(staging_dir), str(target_dir))
        _module_progress(ctx, module_id, 80, "installed to store")
        _refresh_registry_records()
        _module_progress(ctx, module_id, 95, "registry updated")
        _module_completed(ctx, module_id, "install", True, install_path=str(target_dir))
        return {"module_id": module_id, "install_path": str(target_dir)}
    except Exception as exc:
        _module_completed(ctx, module_id, "install", False, error=str(exc))
        raise
    finally:
        try:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass
        try:
            if staging_parent.exists() and not any(staging_parent.iterdir()):
                staging_parent.rmdir()
        except Exception:
            pass


def _handle_module_uninstall(payload: Dict[str, Any], ctx: JobContext) -> Dict[str, Any]:
    module_id = _validate_module_id(payload)
    target_dir = Path("content_store") / module_id
    if not target_dir.exists() or not target_dir.is_dir():
        raise FileNotFoundError(f"module not installed: {module_id}")
    try:
        _module_progress(ctx, module_id, 10, "removing module")
        shutil.rmtree(target_dir)
        _module_progress(ctx, module_id, 70, "removed from store")
        _refresh_registry_records()
        _module_progress(ctx, module_id, 95, "registry updated")
        _module_completed(ctx, module_id, "uninstall", True)
        return {"module_id": module_id}
    except Exception as exc:
        _module_completed(ctx, module_id, "uninstall", False, error=str(exc))
        raise


def _register_builtin_jobs() -> None:
    register_job_handler(JOB_REPORT_GENERATE, _handle_report_job)
    register_job_handler(JOB_CLEANUP_CACHE, _handle_cleanup_cache)
    register_job_handler(JOB_CLEANUP_DUMPS, _handle_cleanup_dumps)
    register_job_handler(JOB_MODULE_INSTALL, _handle_module_install)
    register_job_handler(JOB_MODULE_UNINSTALL, _handle_module_uninstall)


_register_builtin_jobs()

KNOWN_JOBS = frozenset(_JOB_HANDLERS.keys())
