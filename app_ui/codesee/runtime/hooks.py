from __future__ import annotations

import sys
import threading
import time
import traceback
from typing import Optional

from .events import CodeSeeEvent, EVENT_APP_CRASH, EVENT_APP_ERROR
from .hub import CodeSeeRuntimeHub


_INSTALLED = False
_PREV_SYS_HOOK = None
_PREV_THREAD_HOOK = None


def install_exception_hooks(hub: CodeSeeRuntimeHub) -> None:
    global _INSTALLED, _PREV_SYS_HOOK, _PREV_THREAD_HOOK
    if _INSTALLED:
        return
    _INSTALLED = True
    _PREV_SYS_HOOK = sys.excepthook
    _PREV_THREAD_HOOK = threading.excepthook

    def _sys_hook(exc_type, exc, tb):
        detail = "".join(traceback.format_exception(exc_type, exc, tb))
        event = CodeSeeEvent(
            ts=_now_label(),
            kind=EVENT_APP_ERROR,
            severity="error",
            message=f"{exc_type.__name__}: {exc}",
            node_ids=["system:app_ui"],
            detail=detail,
            source="sys.excepthook",
        )
        hub.publish(event)
        if _PREV_SYS_HOOK:
            _PREV_SYS_HOOK(exc_type, exc, tb)

    def _thread_hook(args: threading.ExceptHookArgs):
        detail = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        event = CodeSeeEvent(
            ts=_now_label(),
            kind=EVENT_APP_CRASH,
            severity="crash",
            message=f"{args.exc_type.__name__}: {args.exc_value}",
            node_ids=["system:app_ui"],
            detail=detail,
            source="threading.excepthook",
        )
        hub.publish(event)
        if _PREV_THREAD_HOOK:
            _PREV_THREAD_HOOK(args)

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook


def _now_label() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
