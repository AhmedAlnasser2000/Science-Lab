from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, MutableMapping

STATE_INACTIVE = "INACTIVE"

DEFAULT_INACTIVE_NODE_OPACITY = 0.40
DEFAULT_INACTIVE_EDGE_OPACITY = 0.20
DEFAULT_MONITOR_BORDER_PX = 2

MIN_INACTIVE_NODE_OPACITY = 0.10
MIN_INACTIVE_EDGE_OPACITY = 0.05
MAX_INACTIVE_OPACITY = 1.00
MIN_MONITOR_BORDER_PX = 1
MAX_MONITOR_BORDER_PX = 6

EdgeKey = tuple[str, str]


@dataclass(frozen=True)
class TrailFocusResult:
    focus_nodes: set[str]
    focus_edges: set[EdgeKey]
    node_opacity: dict[str, float]
    edge_opacity: dict[EdgeKey, float]


def clamp_inactive_node_opacity(value: object) -> float:
    return _clamp_float(
        value,
        default=DEFAULT_INACTIVE_NODE_OPACITY,
        minimum=MIN_INACTIVE_NODE_OPACITY,
        maximum=MAX_INACTIVE_OPACITY,
    )


def clamp_inactive_edge_opacity(value: object) -> float:
    return _clamp_float(
        value,
        default=DEFAULT_INACTIVE_EDGE_OPACITY,
        minimum=MIN_INACTIVE_EDGE_OPACITY,
        maximum=MAX_INACTIVE_OPACITY,
    )


def clamp_monitor_border_px(value: object) -> int:
    return _clamp_int(
        value,
        default=DEFAULT_MONITOR_BORDER_PX,
        minimum=MIN_MONITOR_BORDER_PX,
        maximum=MAX_MONITOR_BORDER_PX,
    )


def compute_trail_focus(
    *,
    visible_nodes: Iterable[str],
    visible_edges: Iterable[tuple[str, str]],
    monitor_states: Mapping[str, Mapping[str, object]] | None,
    trace_nodes: Iterable[str] | None,
    trace_edges: Iterable[tuple[str, str]] | None,
    selected_node_ids: Iterable[str] | None,
    enabled: bool,
    inactive_node_opacity: object = DEFAULT_INACTIVE_NODE_OPACITY,
    inactive_edge_opacity: object = DEFAULT_INACTIVE_EDGE_OPACITY,
) -> TrailFocusResult:
    normalized_nodes = {str(node_id).strip() for node_id in visible_nodes if str(node_id).strip()}
    normalized_edges = _normalize_edges(visible_edges)
    selected = {str(node_id).strip() for node_id in (selected_node_ids or []) if str(node_id).strip()}
    trace_node_set = {str(node_id).strip() for node_id in (trace_nodes or []) if str(node_id).strip()}

    focus_nodes = _compute_focus_nodes(
        visible_nodes=normalized_nodes,
        monitor_states=monitor_states or {},
        trace_nodes=trace_node_set,
        selected_node_ids=selected,
    )
    focus_edges = _compute_focus_edges(
        visible_edges=normalized_edges,
        trace_edges=trace_edges or (),
        selected_node_ids=selected,
    )
    node_map, edge_map = _compute_opacity_maps(
        visible_nodes=normalized_nodes,
        visible_edges=normalized_edges,
        focus_nodes=focus_nodes,
        focus_edges=focus_edges,
        enabled=bool(enabled),
        inactive_node_opacity=clamp_inactive_node_opacity(inactive_node_opacity),
        inactive_edge_opacity=clamp_inactive_edge_opacity(inactive_edge_opacity),
    )
    return TrailFocusResult(
        focus_nodes=focus_nodes,
        focus_edges=focus_edges,
        node_opacity=node_map,
        edge_opacity=edge_map,
    )


def _compute_focus_nodes(
    *,
    visible_nodes: set[str],
    monitor_states: Mapping[str, Mapping[str, object]],
    trace_nodes: set[str],
    selected_node_ids: set[str],
) -> set[str]:
    focus = set()
    for node_id, state in monitor_states.items():
        if node_id not in visible_nodes:
            continue
        if _is_active_monitor_state(state):
            focus.add(node_id)
    focus.update(node_id for node_id in trace_nodes if node_id in visible_nodes)
    focus.update(node_id for node_id in selected_node_ids if node_id in visible_nodes)
    return focus


def _compute_focus_edges(
    *,
    visible_edges: set[EdgeKey],
    trace_edges: Iterable[tuple[str, str]],
    selected_node_ids: set[str],
) -> set[EdgeKey]:
    focus: set[EdgeKey] = set()
    for raw_edge in trace_edges:
        edge = _normalize_edge(raw_edge)
        if not edge:
            continue
        resolved = _resolve_visible_edge(edge, visible_edges)
        if resolved:
            focus.add(resolved)
    for src, dst in visible_edges:
        if src in selected_node_ids or dst in selected_node_ids:
            focus.add((src, dst))
    return focus


def _compute_opacity_maps(
    *,
    visible_nodes: set[str],
    visible_edges: set[EdgeKey],
    focus_nodes: set[str],
    focus_edges: set[EdgeKey],
    enabled: bool,
    inactive_node_opacity: float,
    inactive_edge_opacity: float,
) -> tuple[dict[str, float], dict[EdgeKey, float]]:
    if not enabled:
        return (
            {node_id: 1.0 for node_id in visible_nodes},
            {edge: 1.0 for edge in visible_edges},
        )
    node_map = {
        node_id: 1.0 if node_id in focus_nodes else inactive_node_opacity
        for node_id in visible_nodes
    }
    edge_map = {
        edge: 1.0 if edge in focus_edges else inactive_edge_opacity
        for edge in visible_edges
    }
    return node_map, edge_map


def _is_active_monitor_state(state: Mapping[str, object]) -> bool:
    text = str(state.get("state") or "").strip().upper()
    if not text:
        return False
    return text != STATE_INACTIVE


def _normalize_edges(edges: Iterable[tuple[str, str]]) -> set[EdgeKey]:
    result: set[EdgeKey] = set()
    for raw_edge in edges:
        edge = _normalize_edge(raw_edge)
        if edge:
            result.add(edge)
    return result


def _normalize_edge(raw_edge: tuple[str, str] | object) -> EdgeKey | None:
    if not isinstance(raw_edge, tuple) or len(raw_edge) != 2:
        return None
    src = str(raw_edge[0] or "").strip()
    dst = str(raw_edge[1] or "").strip()
    if not src or not dst:
        return None
    return (src, dst)


def _resolve_visible_edge(edge: EdgeKey, visible_edges: set[EdgeKey]) -> EdgeKey | None:
    if edge in visible_edges:
        return edge
    reverse = (edge[1], edge[0])
    if reverse in visible_edges:
        return reverse
    return None


def _clamp_float(value: object, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    parsed = max(float(minimum), parsed)
    parsed = min(float(maximum), parsed)
    return parsed


def _clamp_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    parsed = max(int(minimum), parsed)
    parsed = min(int(maximum), parsed)
    return parsed
