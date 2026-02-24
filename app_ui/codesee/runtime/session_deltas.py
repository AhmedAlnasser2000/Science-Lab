from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

MonitorStates = Dict[str, Dict[str, object]]
TraceSnapshot = Tuple[List[Tuple[str, str]], Set[str], Optional[str]]


def monitor_transition_deltas(
    before: MonitorStates,
    after: MonitorStates,
    *,
    reason: str,
) -> List[dict]:
    out: List[dict] = []
    node_ids = set(before.keys()) | set(after.keys())
    for node_id in sorted(node_ids):
        prev = before.get(node_id) or {}
        nxt = after.get(node_id) or {}
        prev_state = str(prev.get("state") or "INACTIVE")
        next_state = str(nxt.get("state") or "INACTIVE")
        prev_active = bool(prev.get("active", False))
        next_active = bool(nxt.get("active", False))
        prev_stuck = bool(prev.get("stuck", False))
        next_stuck = bool(nxt.get("stuck", False))
        prev_fatal = bool(prev.get("fatal", False))
        next_fatal = bool(nxt.get("fatal", False))
        if (
            prev_state == next_state
            and prev_active == next_active
            and prev_stuck == next_stuck
            and prev_fatal == next_fatal
        ):
            continue
        out.append(
            {
                "delta_type": "monitor.state.transition",
                "node_id": node_id,
                "before_ref": prev_state,
                "after_ref": next_state,
                "metadata": {
                    "reason": str(reason),
                    "before": {
                        "state": prev_state,
                        "active": prev_active,
                        "stuck": prev_stuck,
                        "fatal": prev_fatal,
                    },
                    "after": {
                        "state": next_state,
                        "active": next_active,
                        "stuck": next_stuck,
                        "fatal": next_fatal,
                    },
                },
            }
        )
    return out


def trace_transition_delta(
    before: TraceSnapshot,
    after: TraceSnapshot,
    *,
    reason: str,
) -> Optional[dict]:
    before_edges, before_nodes, before_id = before
    after_edges, after_nodes, after_id = after

    if before_id == after_id and set(before_edges) == set(after_edges) and set(before_nodes) == set(after_nodes):
        return None

    return {
        "delta_type": "trace.state.transition",
        "node_id": str(after_id or before_id or "trace"),
        "before_ref": str(before_id or "none"),
        "after_ref": str(after_id or "none"),
        "metadata": {
            "reason": str(reason),
            "before": {
                "active_trace_id": before_id,
                "edge_count": len(before_edges),
                "node_count": len(before_nodes),
            },
            "after": {
                "active_trace_id": after_id,
                "edge_count": len(after_edges),
                "node_count": len(after_nodes),
            },
        },
    }
