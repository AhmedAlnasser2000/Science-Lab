from __future__ import annotations

import json
import threading
import uuid
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, List

try:
    from runtime_bus import topics as BUS_TOPICS
except Exception:  # pragma: no cover
    BUS_TOPICS = None

from .cleanup import purge_cache, prune_dumps
from diagnostics.fs_ops import safe_copytree, safe_rmtree
from .discovery import discover_components, ensure_data_roots
from .registry import load_registry, save_registry, upsert_records
from .storage_report import format_report_text, generate_report

JOB_REPORT_GENERATE = "core.report.generate"
JOB_CLEANUP_CACHE = "core.cleanup.cache"
JOB_CLEANUP_DUMPS = "core.cleanup.dumps"
JOB_MODULE_INSTALL = "core.module.install"
JOB_MODULE_UNINSTALL = "core.module.uninstall"
JOB_COMPONENT_PACK_INSTALL = "core.component_pack.install"
JOB_COMPONENT_PACK_UNINSTALL = "core.component_pack.uninstall"

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
JOB_HISTORY_PATH = Path("data/roaming/jobs.json")
REPO_ROOT = Path("content_repo")
STORE_ROOT = Path("content_store")
COMPONENT_REPO_ROOT = Path("component_repo") / "component_v1" / "packs"
COMPONENT_STORE_ROOT = Path("component_store") / "component_v1" / "packs"
DEBUG_LOG_PATH = Path(r"c:\Users\ahmed\Downloads\PhysicsLab\.cursor\debug.log")

DEFAULT_JOB_TIMEOUT = 60.0
_JOB_TIMEOUTS = {
    JOB_REPORT_GENERATE: 30.0,
    JOB_CLEANUP_CACHE: 30.0,
    JOB_CLEANUP_DUMPS: 30.0,
    JOB_MODULE_INSTALL: 60.0,
    JOB_MODULE_UNINSTALL: 60.0,
    JOB_COMPONENT_PACK_INSTALL: 45.0,
    JOB_COMPONENT_PACK_UNINSTALL: 45.0,
}


def _agent_log(location: str, message: str, data: Dict[str, Any], hypothesis_id: str, run_id: str = "baseline") -> None:
    # region agent log
    try:
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as _fh:
            _fh.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": run_id,
                        "hypothesisId": hypothesis_id,
                        "location": location,
                        "message": message,
                        "data": data,
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # endregion


def _load_manifest(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_module_paths(module_id: str, *, source: str) -> tuple[Path, Path, str]:
    """Resolve module paths allowing manifest id/folder name mismatch."""
    base = REPO_ROOT if source == "repo" else STORE_ROOT
    if not base.exists():
        raise FileNotFoundError(f"module not found in repo: {module_id}")
    for manifest_path in base.rglob("module_manifest.json"):
        manifest = _load_manifest(manifest_path)
        manifest_id = str(manifest.get("module_id") or "").strip()
        folder_id = manifest_path.parent.name
        if module_id in (manifest_id, folder_id):
            resolved_id = manifest_id or folder_id
            target_dir = STORE_ROOT / folder_id
            _agent_log(
                "core_center/job_manager.py:_resolve_module_paths",
                "module_resolved",
                {
                    "module_id": module_id,
                    "manifest_id": manifest_id,
                    "folder_id": folder_id,
                    "resolved_id": resolved_id,
                    "source": source,
                    "source_dir": str(manifest_path.parent),
                    "target_dir": str(target_dir),
                },
                hypothesis_id="H3",
            )
            return manifest_path.parent, target_dir, resolved_id
    raise FileNotFoundError(f"module not found in repo: {module_id}")


def _resolve_installed_module_path(module_id: str) -> tuple[Path, str]:
    """Find installed module path in store by manifest id or folder name."""
    if not STORE_ROOT.exists():
        raise FileNotFoundError(f"module not installed: {module_id}")
    for manifest_path in STORE_ROOT.rglob("module_manifest.json"):
        manifest = _load_manifest(manifest_path)
        manifest_id = str(manifest.get("module_id") or "").strip()
        folder_id = manifest_path.parent.name
        if module_id in (manifest_id, folder_id):
            return manifest_path.parent, (manifest_id or folder_id)
    raise FileNotFoundError(f"module not installed: {module_id}")


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

    def publish(self, topic: str, payload: Dict[str, Any], *, sticky: bool = False) -> None:
        data = dict(payload)
        data.setdefault("job_id", self.job_id)
        _publish(self.bus, topic, data, self.source, sticky=sticky)


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
            "source": source,
            "status": "pending",
            "progress": 0.0,
            "result": None,
            "error": None,
            "payload": payload or {},
        }
    runner.start()
    _start_job_timeout(job_id, job_type, bus, source)
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
    started_at = _now_iso()
    _update_job_state(job_id, {"status": "running", "started_at": started_at})
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
    if _job_already_terminal(job_id):
        with _LOCK:
            _RUNNING_JOBS.pop(job_id, None)
        return
    if not ok and job_type == JOB_REPORT_GENERATE:
        context.publish(REPORT_READY_TOPIC, {"ok": False, "error": error_msg or "failed"})
    finished_at = _now_iso()
    status = "COMPLETED" if ok else "FAILED"
    _update_job_state(
        job_id,
        {
            "status": status,
            "finished_at": finished_at,
            "result": result if ok else None,
            "error": error_msg if not ok else None,
            "ok": ok,
            "result_summary": _summarize_result(result) if ok else None,
        },
    )
    _publish(
        bus,
        JOB_COMPLETED_TOPIC,
        {
            "job_id": job_id,
            "job_type": job_type,
            "status": status,
            "ok": ok,
            "result": result if ok else None,
            "error": error_msg if not ok else None,
        },
        source,
        sticky=True,
    )
    with _LOCK:
        _RUNNING_JOBS.pop(job_id, None)
        snapshot = dict(_JOB_STATE.get(job_id, {}))
    _persist_job_record(snapshot)


def _publish(bus: Any, topic: Optional[str], payload: Dict[str, Any], source: str, *, sticky: bool = False) -> None:
    if not bus or not topic:
        return
    try:
        bus.publish(topic, payload, source=source, trace_id=None, sticky=sticky)
    except Exception:  # pragma: no cover - defensive
        return


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summarize_result(result: Dict[str, Any]) -> Optional[str]:
    if not result:
        return None
    try:
        text = result.get("text")
        if isinstance(text, str) and text:
            return text[:120]
    except Exception:
        pass
    return None


def _job_timeout_seconds(job_type: str) -> Optional[float]:
    return _JOB_TIMEOUTS.get(job_type, DEFAULT_JOB_TIMEOUT)


def _job_already_terminal(job_id: str) -> bool:
    with _LOCK:
        status = _JOB_STATE.get(job_id, {}).get("status")
    return status in ("COMPLETED", "FAILED")


def _start_job_timeout(job_id: str, job_type: str, bus: Any, source: str) -> None:
    timeout = _job_timeout_seconds(job_type)
    if not timeout:
        return
    timer = threading.Thread(
        target=_watch_job_timeout,
        args=(job_id, job_type, bus, source, timeout),
        name=f"core-center-job-timeout-{job_id}",
        daemon=True,
    )
    timer.start()


def _watch_job_timeout(job_id: str, job_type: str, bus: Any, source: str, timeout: float) -> None:
    time.sleep(timeout)
    with _LOCK:
        state = _JOB_STATE.get(job_id)
        if not state or state.get("status") != "running":
            return
        state.update(
            {
                "status": "FAILED",
                "finished_at": _now_iso(),
                "ok": False,
                "error": f"timeout after {int(timeout)}s",
                "timed_out": True,
            }
        )
        snapshot = dict(state)
        _RUNNING_JOBS.pop(job_id, None)
    if job_type == JOB_REPORT_GENERATE:
        _publish(bus, REPORT_READY_TOPIC, {"ok": False, "error": snapshot.get("error")}, source)
    if job_type in (JOB_MODULE_INSTALL, JOB_MODULE_UNINSTALL):
        payload = snapshot.get("payload") or {}
        module_id = payload.get("module_id")
        action = "install" if job_type == JOB_MODULE_INSTALL else "uninstall"
        if module_id:
            _publish(
                bus,
                CONTENT_INSTALL_COMPLETED_TOPIC,
                {"module_id": module_id, "action": action, "ok": False, "error": snapshot.get("error")},
                source,
                sticky=True,
            )
    _publish(
        bus,
        JOB_COMPLETED_TOPIC,
        {
            "job_id": job_id,
            "job_type": job_type,
            "status": "FAILED",
            "ok": False,
            "result": None,
            "error": snapshot.get("error"),
        },
        source,
        sticky=True,
    )
    _persist_job_record(snapshot)


def _safe_load_history() -> List[Dict[str, Any]]:
    ensure_data_roots()
    path = JOB_HISTORY_PATH
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        bad_path = path.with_suffix(path.suffix + f".bad.{int(time.time())}")
        try:
            path.rename(bad_path)
        except Exception:
            pass
        return []
    except Exception:
        return []
    return []


def _persist_job_record(record: Dict[str, Any]) -> None:
    try:
        records = _safe_load_history()
        job_id = record.get("job_id")
        if job_id:
            records = [r for r in records if r.get("job_id") != job_id]
        records.append(record)
        # keep most recent 200 by started time desc
        records = sorted(
            records,
            key=lambda r: r.get("started_at") or "",
            reverse=True,
        )[:200]
        JOB_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with JOB_HISTORY_PATH.open("w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2)
    except Exception:
        # defensive: never raise
        pass


def get_job_history(*, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    records = _safe_load_history()
    ordered = sorted(records, key=lambda r: r.get("started_at") or "", reverse=True)
    if limit is not None:
        try:
            n = int(limit)
            if n >= 0:
                ordered = ordered[:n]
        except Exception:
            pass
    return ordered


def get_job_record(job_id: str) -> Optional[Dict[str, Any]]:
    if not job_id:
        return None
    for rec in _safe_load_history():
        if rec.get("job_id") == job_id:
            return rec
    return None


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
    ctx.publish(CONTENT_INSTALL_COMPLETED_TOPIC, payload, sticky=True)


def _validate_module_id(payload: Dict[str, Any]) -> str:
    module_id = str(payload.get("module_id") or "").strip()
    if not module_id:
        raise ValueError("module_id_required")
    if any(sep in module_id for sep in ("/", "\\", "..")):
        raise ValueError("invalid_module_id")
    return module_id


def _validate_pack_id(payload: Dict[str, Any]) -> str:
    pack_id = str(payload.get("pack_id") or "").strip()
    if not pack_id:
        raise ValueError("pack_id_required")
    if any(sep in pack_id for sep in ("/", "\\", "..")):
        raise ValueError("invalid_pack_id")
    return pack_id


def _prune_module_staging(module_id: str) -> None:
    base = Path("data/cache/module_installs") / module_id
    if not base.exists():
        return
    try:
        safe_rmtree(base)
    except Exception:
        pass


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
    source_dir, target_dir, resolved_id = _resolve_module_paths(module_id, source="repo")
    staging_dir = Path("data/cache/module_installs") / resolved_id / ctx.job_id
    staging_parent = staging_dir.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    store_parent = target_dir.parent
    store_parent.mkdir(parents=True, exist_ok=True)
    _agent_log(
        "core_center/job_manager.py:_handle_module_install",
        "module_install_start",
        {
            "module_id": module_id,
            "resolved_id": resolved_id,
            "source_dir": str(source_dir),
            "target_dir": str(target_dir),
            "staging_dir": str(staging_dir),
            "target_exists": target_dir.exists(),
            "staging_exists": staging_dir.exists(),
        },
        hypothesis_id="H2",
    )
    ok = False
    error_msg = ""
    result: Dict[str, Any] = {}
    try:
        if target_dir.exists() and (target_dir / "module_manifest.json").exists():
            _module_progress(ctx, resolved_id, 100, "already installed")
            ok = True
            result = {"module_id": resolved_id, "install_path": str(target_dir), "message": "already installed"}
            return result
        if staging_dir.exists():
            safe_rmtree(staging_dir)
        _module_progress(ctx, resolved_id, 5, "preparing staging")
        safe_copytree(source_dir, staging_dir)
        _module_progress(ctx, resolved_id, 55, "staged copy complete")
        if target_dir.exists():
            safe_rmtree(target_dir)
        shutil.move(str(staging_dir), str(target_dir))
        _module_progress(ctx, resolved_id, 80, "installed to store")
        _refresh_registry_records()
        _module_progress(ctx, resolved_id, 95, "registry updated")
        ok = True
        result = {"module_id": resolved_id, "install_path": str(target_dir)}
        return result
    except Exception as exc:
        error_msg = (
            f"install failed: module={module_id} src={source_dir} "
            f"staging={staging_dir} dst={target_dir} err={exc!r}"
        )
        raise RuntimeError(error_msg) from exc
    finally:
        _agent_log(
            "core_center/job_manager.py:_handle_module_install",
            "module_install_finish",
            {
                "module_id": module_id,
                "resolved_id": resolved_id,
                "ok": ok,
                "error": error_msg or None,
                "staging_exists_after": staging_dir.exists(),
                "staging_parent_exists": staging_parent.exists(),
                "target_exists_after": target_dir.exists(),
            },
            hypothesis_id="H2",
        )
        _module_completed(
            ctx,
            resolved_id,
            "install",
            ok,
            error=error_msg or None,
            install_path=str(target_dir) if ok else None,
        )
        try:
            if staging_dir.exists():
                safe_rmtree(staging_dir)
        except Exception:
            pass
        _prune_module_staging(resolved_id)
        try:
            if staging_parent.exists() and not any(staging_parent.iterdir()):
                staging_parent.rmdir()
        except Exception:
            pass


def _handle_module_uninstall(payload: Dict[str, Any], ctx: JobContext) -> Dict[str, Any]:
    module_id = _validate_module_id(payload)
    try:
        target_dir, resolved_id = _resolve_installed_module_path(module_id)
    except FileNotFoundError:
        resolved_id = module_id
        _module_progress(ctx, resolved_id, 100, "already uninstalled")
        _module_completed(ctx, resolved_id, "uninstall", True, error=None)
        return {"module_id": resolved_id, "message": "already uninstalled"}
    ok = False
    error_msg = ""
    result: Dict[str, Any] = {}
    try:
        _module_progress(ctx, resolved_id, 10, "removing module")
        safe_rmtree(target_dir)
        _module_progress(ctx, resolved_id, 70, "removed from store")
        _refresh_registry_records()
        _module_progress(ctx, resolved_id, 95, "registry updated")
        ok = True
        result = {"module_id": resolved_id}
        return result
    except Exception as exc:
        error_msg = f"uninstall failed: module={module_id} dst={target_dir} err={exc!r}"
        raise RuntimeError(error_msg) from exc
    finally:
        _module_completed(ctx, resolved_id, "uninstall", ok, error=error_msg or None)
        if ok:
            _prune_module_staging(resolved_id)


def _handle_component_pack_install(payload: Dict[str, Any], ctx: JobContext) -> Dict[str, Any]:
    pack_id = _validate_pack_id(payload)
    source_dir = COMPONENT_REPO_ROOT / pack_id
    target_dir = COMPONENT_STORE_ROOT / pack_id
    staging_dir = Path("data/cache/pack_installs") / pack_id / ctx.job_id
    staging_parent = staging_dir.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    COMPONENT_STORE_ROOT.mkdir(parents=True, exist_ok=True)
    ok = False
    error_msg = ""
    try:
        ctx.progress(5, "preparing")
        if not source_dir.exists():
            raise FileNotFoundError(f"pack not found: {pack_id}")
        if target_dir.exists():
            ctx.progress(100, "already installed")
            ok = True
            return {"pack_id": pack_id, "install_path": str(target_dir), "text": f"{pack_id} already installed"}
        if staging_dir.exists():
            safe_rmtree(staging_dir)
        safe_copytree(source_dir, staging_dir)
        ctx.progress(60, "staged copy complete")
        if target_dir.exists():
            safe_rmtree(target_dir)
        shutil.move(str(staging_dir), str(target_dir))
        ctx.progress(90, "installed to store")
        ok = True
        return {"pack_id": pack_id, "install_path": str(target_dir), "text": f"Installed {pack_id}"}
    except Exception as exc:
        error_msg = (
            f"install failed: pack={pack_id} src={source_dir} staging={staging_dir} dst={target_dir} err={exc!r}"
        )
        raise RuntimeError(error_msg) from exc
    finally:
        try:
            if staging_dir.exists():
                safe_rmtree(staging_dir)
        except Exception:
            pass
        try:
            if staging_parent.exists() and not any(staging_parent.iterdir()):
                staging_parent.rmdir()
        except Exception:
            pass
        if not ok:
            ctx.progress(0, "failed")


def _handle_component_pack_uninstall(payload: Dict[str, Any], ctx: JobContext) -> Dict[str, Any]:
    pack_id = _validate_pack_id(payload)
    target_dir = COMPONENT_STORE_ROOT / pack_id
    ok = False
    error_msg = ""
    try:
        ctx.progress(10, "removing pack")
        if not target_dir.exists():
            ctx.progress(100, "already removed")
            ok = True
            return {"pack_id": pack_id, "text": f"{pack_id} already removed"}
        safe_rmtree(target_dir)
        ctx.progress(90, "removed from store")
        ok = True
        return {"pack_id": pack_id, "text": f"Uninstalled {pack_id}"}
    except Exception as exc:
        error_msg = f"uninstall failed: pack={pack_id} dst={target_dir} err={exc!r}"
        raise RuntimeError(error_msg) from exc
    finally:
        if not ok:
            ctx.progress(0, "failed")


def _register_builtin_jobs() -> None:
    register_job_handler(JOB_REPORT_GENERATE, _handle_report_job)
    register_job_handler(JOB_CLEANUP_CACHE, _handle_cleanup_cache)
    register_job_handler(JOB_CLEANUP_DUMPS, _handle_cleanup_dumps)
    register_job_handler(JOB_MODULE_INSTALL, _handle_module_install)
    register_job_handler(JOB_MODULE_UNINSTALL, _handle_module_uninstall)
    register_job_handler(JOB_COMPONENT_PACK_INSTALL, _handle_component_pack_install)
    register_job_handler(JOB_COMPONENT_PACK_UNINSTALL, _handle_component_pack_uninstall)


_register_builtin_jobs()

KNOWN_JOBS = frozenset(_JOB_HANDLERS.keys())
