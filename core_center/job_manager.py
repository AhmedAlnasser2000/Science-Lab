from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
JOB_HISTORY_LIMIT = 50
JOB_HISTORY_PATH = Path("data/roaming/jobs.json")

DEBUG_LOG_PATH = Path(r"c:\Users\ahmed\Downloads\PhysicsLab\.cursor\debug.log")
CORE_DEBUG_LOG_ENABLED = bool(
    os.getenv("PHYSICSLAB_CORE_DEBUG") == "1"
    or os.getenv("PHYSICSLAB_UI_DEBUG") == "1"
    or os.getenv("PHYSICSLAB_BUS_DEBUG") == "1"
)


def _append_job_debug_log(record: Dict[str, Any]) -> None:
    if not CORE_DEBUG_LOG_ENABLED:
        return
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(record)
        payload.setdefault("timestamp", int(time.time() * 1000))
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as _log_file:
            _log_file.write(json.dumps(payload) + "\n")
    except Exception as exc:  # pragma: no cover - debug aid
        print(f"[core_debug] log write failed: {exc!r}", flush=True)

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
    _record_job_start(job_id, job_type, source)
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
    _record_job_completion(job_id, job_type, source, ok, error_msg, result if ok else None)
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
    merged = upsert_records(existing, discovered, drop_missing=True)
    # region agent log
    _append_job_debug_log(
        {
            "sessionId": "debug-session",
            "runId": "pre-fix",
            "hypothesisId": "H3",
            "location": "core_center.job_manager:_refresh_registry_records",
            "message": "registry refresh aggregation",
            "data": {
                "existing": len(existing),
                "discovered": len(discovered),
                "merged": len(merged),
            },
        }
    )
    # endregion
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


def get_job_history(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    entries = _load_job_history()
    if limit is not None:
        try:
            max_items = max(1, int(limit))
            return entries[:max_items]
        except (TypeError, ValueError):
            return entries[: limit or len(entries)]
    return entries


def get_job_record(job_id: str) -> Optional[Dict[str, Any]]:
    if not job_id:
        return None
    for entry in _load_job_history():
        if entry.get("job_id") == job_id:
            return entry
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_job_history() -> List[Dict[str, Any]]:
    if not JOB_HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(JOB_HISTORY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def _save_job_history(entries: List[Dict[str, Any]]) -> None:
    ensure_data_roots()
    JOB_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    JOB_HISTORY_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _upsert_job_record(record: Dict[str, Any]) -> None:
    entries = _load_job_history()
    job_id = record.get("job_id")
    updated = False
    for idx, entry in enumerate(entries):
        if entry.get("job_id") == job_id:
            new_entry = dict(entry)
            for key, value in record.items():
                if value is not None or key not in new_entry:
                    new_entry[key] = value
            entries[idx] = new_entry
            updated = True
            break
    if not updated:
        entries.insert(0, record)
    trimmed = entries[:JOB_HISTORY_LIMIT]
    _save_job_history(trimmed)


def _record_job_start(job_id: str, job_type: str, source: str) -> None:
    record = {
        "job_id": job_id,
        "job_type": job_type,
        "source": source,
        "status": "running",
        "started_at": _now_iso(),
        "finished_at": None,
        "ok": None,
        "error": None,
        "result_summary": None,
    }
    _upsert_job_record(record)


def _record_job_completion(
    job_id: str,
    job_type: str,
    source: str,
    ok: bool,
    error: Optional[str],
    result: Optional[Dict[str, Any]],
) -> None:
    status = "completed" if ok else "failed"
    summary = None
    if isinstance(result, dict):
        summary_value = result.get("summary")
        if isinstance(summary_value, str):
            summary = summary_value[:200]
    record = {
        "job_id": job_id,
        "job_type": job_type,
        "source": source,
        "status": status,
        "finished_at": _now_iso(),
        "ok": bool(ok),
        "error": error or None,
        "result_summary": summary,
    }
    _upsert_job_record(record)


def _register_builtin_jobs() -> None:
    register_job_handler(JOB_REPORT_GENERATE, _handle_report_job)
    register_job_handler(JOB_CLEANUP_CACHE, _handle_cleanup_cache)
    register_job_handler(JOB_CLEANUP_DUMPS, _handle_cleanup_dumps)
    register_job_handler(JOB_MODULE_INSTALL, _handle_module_install)
    register_job_handler(JOB_MODULE_UNINSTALL, _handle_module_uninstall)


_register_builtin_jobs()

KNOWN_JOBS = frozenset(_JOB_HANDLERS.keys())
