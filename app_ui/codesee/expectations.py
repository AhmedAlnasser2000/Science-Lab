from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class EVACheck:
    check_id: str
    ts: float
    node_id: str
    expected: Any
    actual: Any
    mode: str
    tolerance: Optional[float] = None
    passed: bool = False
    message: str = ""
    context: Dict[str, Any] = field(default_factory=dict)


def evaluate_check(expected: Any, actual: Any, mode: str, tolerance: Optional[float]) -> tuple[bool, str]:
    mode = (mode or "exact").lower()
    if mode == "exact":
        passed = expected == actual
        message = "Exact match" if passed else "Exact mismatch"
        return passed, message
    if mode == "tolerance":
        try:
            diff = abs(float(expected) - float(actual))
            tol = float(tolerance or 0.0)
            passed = diff <= tol
            message = f"Diff {diff:.4f} <= {tol:.4f}" if passed else f"Diff {diff:.4f} > {tol:.4f}"
            return passed, message
        except Exception:
            return False, "Tolerance comparison failed"
    if mode == "contains":
        try:
            passed = expected in actual
            message = "Contains" if passed else "Missing expected content"
            return passed, message
        except Exception:
            return False, "Contains check failed"
    if mode == "regex":
        try:
            pattern = str(expected)
            passed = re.search(pattern, str(actual)) is not None
            message = "Regex match" if passed else "Regex mismatch"
            return passed, message
        except Exception:
            return False, "Regex check failed"
    return False, "Custom check not evaluated"


def build_check(
    *,
    check_id: str,
    node_id: str,
    expected: Any,
    actual: Any,
    mode: str = "exact",
    tolerance: Optional[float] = None,
    message: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> EVACheck:
    passed, auto_message = evaluate_check(expected, actual, mode, tolerance)
    return EVACheck(
        check_id=check_id,
        ts=time.time(),
        node_id=node_id,
        expected=_json_safe(expected),
        actual=_json_safe(actual),
        mode=mode,
        tolerance=tolerance,
        passed=passed,
        message=message or auto_message,
        context=_json_safe(context or {}),
    )


def check_to_dict(check: EVACheck) -> Dict[str, Any]:
    return {
        "check_id": check.check_id,
        "ts": check.ts,
        "node_id": check.node_id,
        "expected": _json_safe(check.expected),
        "actual": _json_safe(check.actual),
        "mode": check.mode,
        "tolerance": check.tolerance,
        "passed": check.passed,
        "message": check.message,
        "context": _json_safe(check.context or {}),
    }


def check_from_dict(data: Dict[str, Any]) -> Optional[EVACheck]:
    if not isinstance(data, dict):
        return None
    check_id = str(data.get("check_id") or "").strip()
    node_id = str(data.get("node_id") or "").strip()
    if not check_id or not node_id:
        return None
    ts = float(data.get("ts") or 0.0)
    return EVACheck(
        check_id=check_id,
        ts=ts,
        node_id=node_id,
        expected=data.get("expected"),
        actual=data.get("actual"),
        mode=str(data.get("mode") or "exact"),
        tolerance=data.get("tolerance"),
        passed=bool(data.get("passed")),
        message=str(data.get("message") or ""),
        context=data.get("context") if isinstance(data.get("context"), dict) else {},
    )


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_json_safe(v) for v in value]
        return str(value)
