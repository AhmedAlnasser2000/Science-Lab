from __future__ import annotations

import time
from typing import Callable, Dict, Optional

from .events import (
    CodeSeeEvent,
    EVENT_APP_ACTIVITY,
    EVENT_APP_ERROR,
    EVENT_BUS_REQUEST,
    SpanEnd,
    SpanStart,
    SpanUpdate,
)
from .hub import CodeSeeRuntimeHub

try:
    from runtime_bus import topics as BUS_TOPICS
except Exception:  # pragma: no cover - optional dependency
    BUS_TOPICS = None


TOPIC_JOB_STARTED = BUS_TOPICS.JOB_STARTED if BUS_TOPICS else "job.started"
TOPIC_JOB_PROGRESS = BUS_TOPICS.JOB_PROGRESS if BUS_TOPICS else "job.progress"
TOPIC_JOB_COMPLETED = BUS_TOPICS.JOB_COMPLETED if BUS_TOPICS else "job.completed"
TOPIC_CONTENT_PROGRESS = (
    BUS_TOPICS.CONTENT_INSTALL_PROGRESS if BUS_TOPICS else "content.install.progress"
)
TOPIC_CONTENT_COMPLETED = (
    BUS_TOPICS.CONTENT_INSTALL_COMPLETED if BUS_TOPICS else "content.install.completed"
)
TOPIC_CLEANUP_STARTED = BUS_TOPICS.CORE_CLEANUP_STARTED if BUS_TOPICS else "core.cleanup.started"
TOPIC_CLEANUP_COMPLETED = BUS_TOPICS.CORE_CLEANUP_COMPLETED if BUS_TOPICS else "core.cleanup.completed"
TOPIC_ERROR_RAISED = BUS_TOPICS.ERROR_RAISED if BUS_TOPICS else "error.raised"


class BusBridge:
    def __init__(
        self,
        bus,
        hub: CodeSeeRuntimeHub,
        *,
        workspace_id_provider: Optional[Callable[[], str]] = None,
    ) -> None:
        self._bus = bus
        self._hub = hub
        self._workspace_id_provider = workspace_id_provider or (lambda: "default")
        self._subscriptions: list[str] = []
        self._active_spans: Dict[str, str] = {}
        self._connected = False

    def start(self) -> None:
        if not self._bus or not self._hub or self._connected:
            if self._hub:
                self._hub.set_bus_connected(False)
            return
        self._connected = True
        self._hub.set_bus_connected(True)
        self._subscribe(TOPIC_JOB_STARTED, self._on_job_started)
        self._subscribe(TOPIC_JOB_PROGRESS, self._on_job_progress)
        self._subscribe(TOPIC_JOB_COMPLETED, self._on_job_completed)
        self._subscribe(TOPIC_CONTENT_PROGRESS, self._on_content_progress)
        self._subscribe(TOPIC_CONTENT_COMPLETED, self._on_content_completed)
        self._subscribe(TOPIC_CLEANUP_STARTED, self._on_cleanup_started)
        self._subscribe(TOPIC_CLEANUP_COMPLETED, self._on_cleanup_completed)
        self._subscribe(TOPIC_ERROR_RAISED, self._on_error_raised)

    def stop(self) -> None:
        if not self._bus:
            return
        for sub_id in list(self._subscriptions):
            try:
                self._bus.unsubscribe(sub_id)
            except Exception:
                continue
        self._subscriptions.clear()
        self._connected = False
        if self._hub:
            self._hub.set_bus_connected(False)

    def _subscribe(self, topic: Optional[str], handler: Callable) -> None:
        if not (self._bus and topic):
            return

        def _wrapped(envelope):
            handler(envelope)

        try:
            sub_id = self._bus.subscribe(topic, _wrapped, replay_last=False)
        except Exception:
            return
        self._subscriptions.append(sub_id)

    def _on_job_started(self, envelope) -> None:
        payload = _payload(envelope)
        job_id = _str(payload.get("job_id") or payload.get("id") or "")
        job_type = _str(payload.get("job_type") or payload.get("type") or "job")
        span_id = f"job:{job_id or job_type}"
        label = f"Job {job_type}"
        node_id = _node_for_job(job_type)
        self._active_spans[span_id] = node_id
        self._hub.publish_span_start(
            SpanStart(
                span_id=span_id,
                label=label,
                node_id=node_id,
                source_id="system:runtime_bus",
            )
        )
        self._publish_bus_activity(envelope, node_id=node_id, message=label)

    def _on_job_progress(self, envelope) -> None:
        payload = _payload(envelope)
        job_id = _str(payload.get("job_id") or payload.get("id") or "")
        job_type = _str(payload.get("job_type") or payload.get("type") or "job")
        span_id = f"job:{job_id or job_type}"
        node_id = self._active_spans.get(span_id) or _node_for_job(job_type)
        if span_id not in self._active_spans:
            self._active_spans[span_id] = node_id
            self._hub.publish_span_start(
                SpanStart(
                    span_id=span_id,
                    label=f"Job {job_type}",
                    node_id=node_id,
                    source_id="system:runtime_bus",
                )
            )
        progress = _progress_value(payload.get("percent"))
        stage = _str(payload.get("stage") or "")
        self._hub.publish_span_update(
            SpanUpdate(
                span_id=span_id,
                progress=progress,
                message=stage or None,
            )
        )
        self._publish_bus_activity(envelope, node_id=node_id, message=stage or "job progress")

    def _on_job_completed(self, envelope) -> None:
        payload = _payload(envelope)
        job_id = _str(payload.get("job_id") or payload.get("id") or "")
        job_type = _str(payload.get("job_type") or payload.get("type") or "job")
        span_id = f"job:{job_id or job_type}"
        node_id = self._active_spans.pop(span_id, None) or _node_for_job(job_type)
        ok = bool(payload.get("ok", True))
        status = "completed" if ok else "failed"
        message = _str(payload.get("error") or payload.get("status") or status)
        self._hub.publish_span_end(
            SpanEnd(
                span_id=span_id,
                status=status,
                message=message or None,
            )
        )
        self._publish_bus_activity(envelope, node_id=node_id, message=message or "job completed")

    def _on_content_progress(self, envelope) -> None:
        payload = _payload(envelope)
        module_id = _str(payload.get("module_id") or payload.get("id") or "")
        span_id = f"content:{module_id or 'module'}"
        node_id = "system:content_system"
        if span_id not in self._active_spans:
            self._active_spans[span_id] = node_id
            self._hub.publish_span_start(
                SpanStart(
                    span_id=span_id,
                    label=f"Content {module_id or 'module'}",
                    node_id=node_id,
                    source_id="system:runtime_bus",
                )
            )
        progress = _progress_value(payload.get("percent"))
        stage = _str(payload.get("stage") or "")
        self._hub.publish_span_update(
            SpanUpdate(
                span_id=span_id,
                progress=progress,
                message=stage or None,
            )
        )
        self._publish_bus_activity(envelope, node_id=node_id, message=stage or "content progress")

    def _on_content_completed(self, envelope) -> None:
        payload = _payload(envelope)
        module_id = _str(payload.get("module_id") or payload.get("id") or "")
        action = _str(payload.get("action") or "content")
        span_id = f"content:{module_id or action}"
        node_id = self._active_spans.pop(span_id, None) or "system:content_system"
        ok = bool(payload.get("ok", True))
        status = "completed" if ok else "failed"
        message = _str(payload.get("error") or f"{action} {module_id} {status}".strip())
        self._hub.publish_span_end(
            SpanEnd(
                span_id=span_id,
                status=status,
                message=message or None,
            )
        )
        self._publish_bus_activity(envelope, node_id=node_id, message=message or "content completed")

    def _on_cleanup_started(self, envelope) -> None:
        payload = _payload(envelope)
        kind = _str(payload.get("kind") or "cleanup")
        span_id = f"cleanup:{kind}"
        node_id = "system:core_center"
        self._active_spans[span_id] = node_id
        self._hub.publish_span_start(
            SpanStart(
                span_id=span_id,
                label=f"Cleanup {kind}",
                node_id=node_id,
                source_id="system:runtime_bus",
            )
        )
        self._publish_bus_activity(envelope, node_id=node_id, message=f"cleanup {kind} started")

    def _on_cleanup_completed(self, envelope) -> None:
        payload = _payload(envelope)
        kind = _str(payload.get("kind") or "cleanup")
        span_id = f"cleanup:{kind}"
        node_id = self._active_spans.pop(span_id, None) or "system:core_center"
        ok = bool(payload.get("ok", True))
        status = "completed" if ok else "failed"
        message = _str(payload.get("error") or f"cleanup {kind} {status}".strip())
        self._hub.publish_span_end(
            SpanEnd(
                span_id=span_id,
                status=status,
                message=message or None,
            )
        )
        self._publish_bus_activity(envelope, node_id=node_id, message=message or "cleanup completed")

    def _on_error_raised(self, envelope) -> None:
        payload = _payload(envelope)
        message = _str(payload.get("message") or payload.get("error") or "Error raised")
        self._hub.publish(
            CodeSeeEvent(
                ts=_event_ts(envelope),
                kind=EVENT_APP_ERROR,
                severity="error",
                message=message,
                node_ids=["system:app_ui"],
                detail=_str(payload.get("detail") or ""),
                source="runtime_bus",
                source_node_id="system:runtime_bus",
                target_node_id="system:app_ui",
            )
        )
        self._publish_bus_activity(envelope, node_id="system:runtime_bus", message=message)

    def _publish_bus_activity(self, envelope, *, node_id: str, message: str) -> None:
        self._hub.publish(
            CodeSeeEvent(
                ts=_event_ts(envelope),
                kind=EVENT_BUS_REQUEST,
                severity="info",
                message=_short_message(message),
                node_ids=[node_id or "system:runtime_bus"],
                source="runtime_bus",
                source_node_id="system:runtime_bus",
                target_node_id=node_id or "system:runtime_bus",
            )
        )


def _payload(envelope) -> Dict[str, object]:
    payload = getattr(envelope, "payload", None) or {}
    return payload if isinstance(payload, dict) else {}


def _event_ts(envelope) -> str:
    ts = getattr(envelope, "timestamp", None)
    if isinstance(ts, str) and ts:
        return ts
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _short_message(value: str, limit: int = 140) -> str:
    text = value or ""
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _progress_value(raw) -> Optional[float]:
    if raw is None:
        return None
    try:
        value = float(raw)
    except Exception:
        return None
    if value > 1.0:
        value = value / 100.0
    if value < 0.0:
        return 0.0
    return min(value, 1.0)


def _node_for_job(job_type: str) -> str:
    job_type = (job_type or "").lower()
    if "component_pack" in job_type or "pack" in job_type:
        return "system:component_runtime"
    if "module" in job_type or "content" in job_type:
        return "system:content_system"
    if "cleanup" in job_type or "report" in job_type:
        return "system:core_center"
    return "system:core_center"


def run_bus_bridge_smoke_test() -> None:
    from PyQt6 import QtCore, QtWidgets
    from runtime_bus.bus import RuntimeBus

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    bus = RuntimeBus()
    hub = CodeSeeRuntimeHub()
    hub.set_workspace_id("codesee_smoke")
    bridge = BusBridge(bus, hub)
    bridge.start()
    bus.publish(TOPIC_JOB_STARTED, {"job_id": "demo", "job_type": "core.cleanup.cache"}, source="core_center")
    bus.publish(TOPIC_JOB_PROGRESS, {"job_id": "demo", "job_type": "core.cleanup.cache", "percent": 50}, source="core_center")
    bus.publish(TOPIC_JOB_COMPLETED, {"job_id": "demo", "job_type": "core.cleanup.cache", "ok": True}, source="core_center")
    QtCore.QTimer.singleShot(250, app.quit)
    app.exec()
    hub.flush_activity()
    if hub.event_count() <= 0:
        raise AssertionError("expected bus bridge to record events")
    if hub.active_span_count() < 0:
        raise AssertionError("expected span tracking to be available")
    hub_reload = CodeSeeRuntimeHub()
    hub_reload.set_workspace_id("codesee_smoke")
    if hub_reload.event_count() <= 0:
        raise AssertionError("expected persisted events to reload")
    bridge.stop()
