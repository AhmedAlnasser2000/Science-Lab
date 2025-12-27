from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional

from PyQt6 import QtCore

from .events import CodeSeeEvent, EVENT_EXPECT_CHECK
from ..expectations import EVACheck, check_to_dict


class CodeSeeRuntimeHub(QtCore.QObject):
    event_emitted = QtCore.pyqtSignal(object)

    def __init__(self, *, max_events: int = 500) -> None:
        super().__init__()
        self._events: Deque[CodeSeeEvent] = deque(maxlen=max_events)

    def publish(self, event: CodeSeeEvent) -> None:
        self._events.append(event)
        self.event_emitted.emit(event)

    def query(self, node_id: str, limit: int = 20) -> List[CodeSeeEvent]:
        results: List[CodeSeeEvent] = []
        for event in reversed(self._events):
            if node_id in (event.node_ids or []):
                results.append(event)
                if len(results) >= limit:
                    break
        return list(reversed(results))

    def recent(self, limit: int = 50) -> List[CodeSeeEvent]:
        if limit <= 0:
            return []
        return list(self._events)[-limit:]

    def publish_expect_check(self, check: EVACheck) -> None:
        severity = "failure" if not check.passed else "info"
        event = CodeSeeEvent(
            ts=str(check.ts),
            kind=EVENT_EXPECT_CHECK,
            severity=severity,
            message=check.message,
            node_ids=[check.node_id],
            detail=None,
            source="expectation",
            payload=check_to_dict(check),
        )
        self.publish(event)


_GLOBAL_HUB: Optional[CodeSeeRuntimeHub] = None


def set_global_hub(hub: CodeSeeRuntimeHub) -> None:
    global _GLOBAL_HUB
    _GLOBAL_HUB = hub


def get_global_hub() -> Optional[CodeSeeRuntimeHub]:
    return _GLOBAL_HUB
