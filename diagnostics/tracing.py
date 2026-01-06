from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

_SPAN_LIMIT = 256
_SPAN_BUFFER: Deque[Dict[str, Any]] = deque(maxlen=_SPAN_LIMIT)


@dataclass
class Span:
    name: str
    attrs: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    def __enter__(self) -> "Span":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.end_time = time.time()
        record_span(self)


def start_span(name: str, **attrs: Any) -> Span:
    return Span(name=name, attrs=attrs)


def span(name: str, **attrs: Any) -> Span:
    return start_span(name, **attrs)


def record_span(span_obj: Span) -> None:
    _SPAN_BUFFER.append(
        {
            "name": span_obj.name,
            "attrs": dict(span_obj.attrs or {}),
            "start_time": span_obj.start_time,
            "end_time": span_obj.end_time,
        }
    )


def get_recent_spans() -> List[Dict[str, Any]]:
    return list(_SPAN_BUFFER)


def clear_spans() -> None:
    _SPAN_BUFFER.clear()


def set_span_limit(limit: int) -> None:
    global _SPAN_LIMIT, _SPAN_BUFFER
    _SPAN_LIMIT = max(1, int(limit))
    _SPAN_BUFFER = deque(_SPAN_BUFFER, maxlen=_SPAN_LIMIT)
