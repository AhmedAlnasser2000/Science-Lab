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
    context_node_ids: Iterable[str] | None = None,
    enabled: bool,
    inactive_node_opacity: object = DEFAULT_INACTIVE_NODE_OPACITY,
    inactive_edge_opacity: object = DEFAULT_INACTIVE_EDGE_OPACITY,
) -> TrailFocusResult:
    normalized_nodes = {str(node_id).strip() for node_id in visible_nodes if str(node_id).strip()}
    normalized_edges = _normalize_edges(visible_edges)
    alias_map = _build_visible_node_alias_map(normalized_nodes)
    selected = _resolve_visible_nodes(selected_node_ids or (), alias_map)
    context_nodes = _resolve_visible_nodes(context_node_ids or (), alias_map)
    trace_node_set = _resolve_visible_nodes(trace_nodes or (), alias_map)
    active_monitor_nodes = _resolve_active_monitor_nodes(monitor_states or {}, alias_map)
    resolved_trace_edges = _resolve_trace_edges(
        trace_edges=trace_edges or (),
        visible_edges=normalized_edges,
        alias_map=alias_map,
    )

    focus_nodes = _compute_focus_nodes(
        active_monitor_nodes=active_monitor_nodes,
        trace_nodes=trace_node_set,
        selected_node_ids=selected,
        context_node_ids=context_nodes,
    )
    focus_edges = _compute_focus_edges(
        visible_edges=normalized_edges,
        trace_edges=resolved_trace_edges,
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
    active_monitor_nodes: set[str],
    trace_nodes: set[str],
    selected_node_ids: set[str],
    context_node_ids: set[str],
) -> set[str]:
    focus = set(active_monitor_nodes)
    focus.update(trace_nodes)
    focus.update(selected_node_ids)
    focus.update(context_node_ids)
    return focus


def _compute_focus_edges(
    *,
    visible_edges: set[EdgeKey],
    trace_edges: set[EdgeKey],
    selected_node_ids: set[str],
) -> set[EdgeKey]:
    focus: set[EdgeKey] = set(trace_edges)
    for src, dst in visible_edges:
        if src in selected_node_ids or dst in selected_node_ids:
            focus.add((src, dst))
    return focus


def _resolve_active_monitor_nodes(
    monitor_states: Mapping[str, Mapping[str, object]],
    alias_map: Mapping[str, set[str]],
) -> set[str]:
    focus: set[str] = set()
    for node_id, state in monitor_states.items():
        if not _is_active_monitor_state(state):
            continue
        focus.update(_resolve_visible_nodes((node_id,), alias_map))
    return focus


def _resolve_trace_edges(
    *,
    trace_edges: Iterable[tuple[str, str]],
    visible_edges: set[EdgeKey],
    alias_map: Mapping[str, set[str]],
) -> set[EdgeKey]:
    resolved: set[EdgeKey] = set()
    for raw_edge in trace_edges:
        edge = _normalize_edge(raw_edge)
        if not edge:
            continue
        src_ids = _resolve_visible_nodes((edge[0],), alias_map)
        dst_ids = _resolve_visible_nodes((edge[1],), alias_map)
        if not src_ids:
            src_ids = {edge[0]}
        if not dst_ids:
            dst_ids = {edge[1]}
        for src in src_ids:
            for dst in dst_ids:
                visible = _resolve_visible_edge((src, dst), visible_edges)
                if visible:
                    resolved.add(visible)
    return resolved


def _build_visible_node_alias_map(visible_nodes: set[str]) -> dict[str, set[str]]:
    alias_map: dict[str, set[str]] = {}
    for node_id in visible_nodes:
        for alias in _node_aliases(node_id):
            alias_map.setdefault(alias, set()).add(node_id)
    return alias_map


def _resolve_visible_nodes(raw_node_ids: Iterable[str], alias_map: Mapping[str, set[str]]) -> set[str]:
    resolved: set[str] = set()
    for raw_id in raw_node_ids:
        text = str(raw_id or "").strip()
        if not text:
            continue
        for alias in _node_aliases(text):
            resolved.update(alias_map.get(alias, set()))
    return resolved


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


def _node_aliases(node_id: str) -> set[str]:
    text = str(node_id or "").strip()
    if not text:
        return set()
    aliases = {text}
    if text.startswith("system:"):
        aliases.add(text.split(":", 1)[1])
    elif ":" not in text:
        aliases.add(f"system:{text}")
    if text.startswith("block:labhost:"):
        suffix = text.split("block:labhost:", 1)[1]
        if suffix:
            aliases.add(f"lab:{suffix}")
    elif text.startswith("lab:"):
        suffix = text.split("lab:", 1)[1]
        if suffix:
            aliases.add(f"block:labhost:{suffix}")
    return aliases


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
