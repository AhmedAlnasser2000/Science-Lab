from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from .messages import MessageEnvelope

logger = logging.getLogger(__name__)


def _iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeBus:
    """In-process pub/sub and request-reply bus."""

    def __init__(self):
        self._lock = threading.RLock()
        self._subscribers: Dict[str, tuple[str, Callable[[MessageEnvelope], None]]] = {}
        self._topic_index: Dict[str, set[str]] = {}
        self._request_handlers: Dict[str, Callable[[MessageEnvelope], Dict[str, object]]] = {}

    def subscribe(self, topic: str, handler: Callable[[MessageEnvelope], None]) -> str:
        sub_id = str(uuid.uuid4())
        with self._lock:
            self._subscribers[sub_id] = (topic, handler)
            self._topic_index.setdefault(topic, set()).add(sub_id)
        return sub_id

    def unsubscribe(self, sub_id: str) -> None:
        with self._lock:
            topic, _ = self._subscribers.pop(sub_id, (None, None))
            if topic and topic in self._topic_index:
                self._topic_index[topic].discard(sub_id)
                if not self._topic_index[topic]:
                    self._topic_index.pop(topic, None)

    def register_handler(self, topic: str, handler: Callable[[MessageEnvelope], Dict[str, object]]) -> None:
        with self._lock:
            self._request_handlers[topic] = handler

    def publish(
        self,
        topic: str,
        payload: Optional[Dict[str, object]],
        source: str,
        trace_id: Optional[str] = None,
    ) -> MessageEnvelope:
        envelope = self._build_envelope(topic, payload, source, trace_id)
        handlers = self._copy_handlers(topic)
        for handler in handlers:
            try:
                handler(envelope)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("runtime_bus publish handler error on %s: %s", topic, exc)
        return envelope

    def request(
        self,
        topic: str,
        payload: Optional[Dict[str, object]],
        source: str,
        timeout_ms: int,
        trace_id: Optional[str] = None,
    ) -> Dict[str, object]:
        handler = self._get_request_handler(topic)
        if handler is None:
            return {"ok": False, "error": "no_handler"}

        envelope = self._build_envelope(topic, payload, source, trace_id, target="request")
        done = threading.Event()
        response: Dict[str, object] = {}

        def _invoke():
            nonlocal response
            try:
                result = handler(envelope) or {}
                if not isinstance(result, dict):
                    response = {"ok": False, "error": "invalid_response"}
                else:
                    response = result
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("runtime_bus request handler error on %s: %s", topic, exc)
                response = {"ok": False, "error": "handler_error"}
            finally:
                done.set()

        thread = threading.Thread(target=_invoke, name=f"bus-request-{topic}", daemon=True)
        thread.start()

        if not done.wait(timeout_ms / 1000):
            return {"ok": False, "error": "timeout"}
        return response

    def _build_envelope(
        self,
        topic: str,
        payload: Optional[Dict[str, object]],
        source: str,
        trace_id: Optional[str],
        target: Optional[str] = None,
    ) -> MessageEnvelope:
        trace = trace_id or str(uuid.uuid4())
        body = payload if isinstance(payload, dict) else {}
        return MessageEnvelope(
            msg_id=str(uuid.uuid4()),
            type=topic,
            timestamp=_iso_timestamp(),
            source=source,
            payload=dict(body),
            trace_id=trace,
            target=target,
        )

    def _copy_handlers(self, topic: str) -> list[Callable[[MessageEnvelope], None]]:
        with self._lock:
            sub_ids = list(self._topic_index.get(topic, ()))
            handlers = [self._subscribers[sid][1] for sid in sub_ids if sid in self._subscribers]
        return handlers

    def _get_request_handler(
        self, topic: str
    ) -> Optional[Callable[[MessageEnvelope], Dict[str, object]]]:
        with self._lock:
            return self._request_handlers.get(topic)


_GLOBAL_BUS: Optional[RuntimeBus] = None
_GLOBAL_LOCK = threading.Lock()


def get_global_bus() -> RuntimeBus:
    global _GLOBAL_BUS
    with _GLOBAL_LOCK:
        if _GLOBAL_BUS is None:
            _GLOBAL_BUS = RuntimeBus()
    return _GLOBAL_BUS
