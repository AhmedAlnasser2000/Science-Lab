from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


EVENT_APP_ACTIVITY = "app.activity"
EVENT_APP_ERROR = "app.error"
EVENT_APP_CRASH = "app.crash"
EVENT_JOB_UPDATE = "job.update"
EVENT_BUS_REQUEST = "bus.request"
EVENT_BUS_REPLY = "bus.reply"
EVENT_LOG_LINE = "log.line"


@dataclass(frozen=True)
class CodeSeeEvent:
    ts: str
    kind: str
    severity: str
    message: str
    node_ids: List[str] = field(default_factory=list)
    detail: Optional[str] = None
    source: Optional[str] = None
