from __future__ import annotations

import os
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
_IN_SYS_HOOK = False
_IN_THREAD_HOOK = False


def install_exception_hooks(hub: CodeSeeRuntimeHub) -> None:
    global _INSTALLED, _PREV_SYS_HOOK, _PREV_THREAD_HOOK
    try:
        if os.environ.get("PHYSICSLAB_CODESEE_DISABLE", "0") == "1":
            return
    except Exception:
        return
    if _INSTALLED:
        return
    _INSTALLED = True
    _PREV_SYS_HOOK = sys.excepthook
    _PREV_THREAD_HOOK = threading.excepthook

    def _sys_hook(exc_type, exc, tb):
        global _IN_SYS_HOOK
        if _IN_SYS_HOOK:
            try:
                sys.stderr.write("[codesee] sys.excepthook reentry; skipping\n")
            except Exception:
                pass
            return
        _IN_SYS_HOOK = True
        try:
            try:
                detail = "".join(traceback.format_exception(exc_type, exc, tb))
            except Exception:
                detail = f"{exc_type.__name__}: {exc!r}"
            event = CodeSeeEvent(
                ts=_now_label(),
                kind=EVENT_APP_ERROR,
                severity="error",
                message=f"{exc_type.__name__}: {exc}",
                node_ids=["system:app_ui"],
                detail=detail,
                source="sys.excepthook",
            )
            try:
                hub.publish(event)
            except Exception:
                pass
            if _PREV_SYS_HOOK:
                try:
                    _PREV_SYS_HOOK(exc_type, exc, tb)
                except Exception:
                    pass
        finally:
            _IN_SYS_HOOK = False

    def _thread_hook(args: threading.ExceptHookArgs):
        global _IN_THREAD_HOOK
        if _IN_THREAD_HOOK:
            try:
                sys.stderr.write("[codesee] threading.excepthook reentry; skipping\n")
            except Exception:
                pass
            return
        _IN_THREAD_HOOK = True
        try:
            try:
                detail = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
            except Exception:
                detail = f"{args.exc_type.__name__}: {args.exc_value!r}"
            event = CodeSeeEvent(
                ts=_now_label(),
                kind=EVENT_APP_CRASH,
                severity="crash",
                message=f"{args.exc_type.__name__}: {args.exc_value}",
                node_ids=["system:app_ui"],
                detail=detail,
                source="threading.excepthook",
            )
            try:
                hub.publish(event)
            except Exception:
                pass
            if _PREV_THREAD_HOOK:
                try:
                    _PREV_THREAD_HOOK(args)
                except Exception:
                    pass
        finally:
            _IN_THREAD_HOOK = False

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook


def _now_label() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
