from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional
import time


class CodeSeeLogBuffer:
    def __init__(self, max_lines: int = 400) -> None:
        self._lines: Deque[str] = deque(maxlen=max_lines)

    def append(self, message: object) -> None:
        try:
            text = str(message)
        except Exception:
            return
        stamp = time.strftime("%H:%M:%S")
        self._lines.append(f"{stamp} {text}")

    def get_lines(self, limit: Optional[int] = None) -> List[str]:
        lines = list(self._lines)
        if limit is None or limit >= len(lines):
            return lines
        return lines[-limit:]


LOG_BUFFER = CodeSeeLogBuffer(max_lines=500)
