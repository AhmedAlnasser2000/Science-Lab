from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(slots=True)
class MessageEnvelope:
    """Standard message envelope for all runtime bus traffic."""

    msg_id: str
    type: str
    timestamp: str
    source: str
    payload: Dict[str, object] = field(default_factory=dict)
    trace_id: str = ""
    target: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "msg_id": self.msg_id,
            "type": self.type,
            "timestamp": self.timestamp,
            "source": self.source,
            "payload": dict(self.payload),
            "trace_id": self.trace_id,
            "target": self.target,
        }
