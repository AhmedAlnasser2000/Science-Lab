from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple


def _normalize_workspace_id(workspace_id: str | None) -> str:
    value = str(workspace_id or "").strip()
    if not value:
        return "default"
    return value


def _layout_path(workspace_id: str | None, lens: str, graph_id: str) -> Path:
    safe_workspace = _normalize_workspace_id(workspace_id)
    safe_lens = (lens or "atlas").strip() or "atlas"
    safe_graph = _safe_graph_id(graph_id)
    root = Path("data") / "workspaces" / safe_workspace / "codesee" / "layouts" / safe_lens
    return root / f"{safe_graph}.json"


def _safe_graph_id(graph_id: str | None) -> str:
    value = str(graph_id or "").strip() or "root"
    return value.replace(":", "_").replace("/", "_")


def load_positions(
    workspace_id: str | None,
    lens: str,
    graph_id: str,
) -> Dict[str, Tuple[float, float]]:
    path = _layout_path(workspace_id, lens, graph_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        return {}
    positions: Dict[str, Tuple[float, float]] = {}
    for node_id, value in nodes.items():
        if not isinstance(node_id, str):
            continue
        if not isinstance(value, list) or len(value) != 2:
            continue
        try:
            x = float(value[0])
            y = float(value[1])
        except (TypeError, ValueError):
            continue
        positions[node_id] = (x, y)
    return positions


def save_positions(
    workspace_id: str | None,
    lens: str,
    graph_id: str,
    positions: Dict[str, Tuple[float, float]],
) -> None:
    path = _layout_path(workspace_id, lens, graph_id)
    payload = {
        "version": 1,
        "graph_id": graph_id,
        "lens": lens or "atlas",
        "nodes": {node_id: [pos[0], pos[1]] for node_id, pos in positions.items()},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        return
