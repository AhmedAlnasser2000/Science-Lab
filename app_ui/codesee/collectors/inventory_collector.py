from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..badges import badges_from_keys
from .. import harness
from ..graph_model import ArchitectureGraph, Edge, Node
from .base import CollectorContext, CollectorResult

try:
    from component_runtime import packs as component_packs
    from component_runtime import registry as component_registry
except Exception:  # pragma: no cover
    component_packs = None
    component_registry = None

try:
    from ui_system import manager as ui_manager
except Exception:  # pragma: no cover
    ui_manager = None


def collect_inventory(ctx: CollectorContext) -> CollectorResult:
    result = CollectorResult()
    inventory = _request_inventory(ctx)
    enabled_pack_ids = _load_enabled_component_packs(ctx)

    pack_nodes: List[Node] = []
    block_nodes: List[Node] = []
    pack_edges: List[Edge] = []
    pack_subgraphs: Dict[str, ArchitectureGraph] = {}
    block_subgraphs: Dict[str, ArchitectureGraph] = {}
    subcomponent_subgraphs: Dict[str, ArchitectureGraph] = {}

    component_packs_data = _collect_component_packs(inventory, enabled_pack_ids)
    if harness.is_enabled() and harness.fake_pack_enabled():
        component_packs_data.append(_harness_pack_stub())
    component_ids_in_packs = set()
    for pack in component_packs_data:
        pack_id = pack["pack_id"]
        graph_id = f"pack:component:{pack_id}"
        pack_root = pack.get("pack_root")
        node = Node(
            node_id=graph_id,
            title=pack.get("name") or pack_id,
            node_type="Pack",
            subgraph_id=graph_id,
            badges=badges_from_keys(top=["component"], bottom=["blocks"]),
            metadata=_pack_metadata(pack, pack_root),
        )
        pack_nodes.append(node)
        subgraph_nodes: List[Node] = [_node_copy(node, subgraph_id=None)]
        subgraph_edges: List[Edge] = []
        for component in pack.get("components", []):
            component_id = component.get("component_id")
            if not component_id:
                continue
            component_ids_in_packs.add(component_id)
            block_id = f"block:{component_id}"
            block_graph_id = _block_graph_id(component_id)
            block_node = Node(
                node_id=block_id,
                title=component.get("display_name") or component_id,
                node_type="Block",
                subgraph_id=block_graph_id,
                badges=badges_from_keys(bottom=["block"]),
                metadata=_block_metadata(component, pack_id, pack_root),
            )
            block_nodes.append(block_node)
            pack_edges.append(
                Edge(f"edge:{graph_id}:{block_id}", graph_id, block_id, "contains")
            )
            pack_edges.append(
                Edge(f"edge:{graph_id}:{block_id}:provides", graph_id, block_id, "provides")
            )
            subgraph_nodes.append(_node_copy(block_node, subgraph_id=None))
            subgraph_edges.append(
                Edge(f"edge:{graph_id}:{block_id}", graph_id, block_id, "contains")
            )
            subgraph_edges.append(
                Edge(f"edge:{graph_id}:{block_id}:provides", graph_id, block_id, "provides")
            )
            deps, dep_edges = _dependency_edges(block_id, component)
            pack_edges.extend(dep_edges)
            subgraph_edges.extend(dep_edges)
            block_graph, subgraphs = _build_block_subgraph(
                block_graph_id,
                block_node,
                component,
                pack_root,
            )
            block_subgraphs[block_graph_id] = block_graph
            subcomponent_subgraphs.update(subgraphs)
        pack_subgraphs[graph_id] = ArchitectureGraph(
            graph_id=graph_id,
            title=node.title,
            nodes=subgraph_nodes,
            edges=subgraph_edges,
        )

    built_in = _collect_builtin_blocks(component_ids_in_packs)
    if built_in:
        built_in_id = "pack:built_in"
        built_in_node = Node(
            node_id=built_in_id,
            title="Built-in Blocks",
            node_type="Pack",
            subgraph_id=built_in_id,
            badges=badges_from_keys(top=["builtin"], bottom=["blocks"]),
            metadata={"pack_id": "built_in", "source": "component_registry"},
        )
        pack_nodes.append(built_in_node)
        subgraph_nodes = [_node_copy(built_in_node, subgraph_id=None)]
        subgraph_edges = []
        for block in built_in:
            block_id = f"block:{block['component_id']}"
            block_graph_id = _block_graph_id(block["component_id"])
            block_node = Node(
                node_id=block_id,
                title=block.get("display_name") or block["component_id"],
                node_type="Block",
                subgraph_id=block_graph_id,
                badges=badges_from_keys(bottom=["block"]),
                metadata={"component_id": block.get("component_id"), "source": "component_registry"},
            )
            block_nodes.append(block_node)
            pack_edges.append(
                Edge(f"edge:{built_in_id}:{block_id}", built_in_id, block_id, "contains")
            )
            subgraph_nodes.append(_node_copy(block_node, subgraph_id=None))
            subgraph_edges.append(
                Edge(f"edge:{built_in_id}:{block_id}", built_in_id, block_id, "contains")
            )
            block_graph, subgraphs = _build_block_subgraph(
                block_graph_id,
                block_node,
                {"component_id": block.get("component_id")},
                None,
            )
            block_subgraphs[block_graph_id] = block_graph
            subcomponent_subgraphs.update(subgraphs)
        pack_subgraphs[built_in_id] = ArchitectureGraph(
            graph_id=built_in_id,
            title=built_in_node.title,
            nodes=subgraph_nodes,
            edges=subgraph_edges,
        )

    ui_pack_nodes = _collect_ui_packs(inventory)
    pack_nodes.extend(ui_pack_nodes)

    result.nodes.extend(pack_nodes)
    result.nodes.extend(block_nodes)
    result.edges.extend(pack_edges)
    result.subgraphs.update(pack_subgraphs)
    result.subgraphs.update(block_subgraphs)
    result.subgraphs.update(subcomponent_subgraphs)
    return result


def _collect_component_packs(
    inventory: Optional[Dict],
    enabled_pack_ids: Optional[set[str]],
) -> List[Dict]:
    packs: List[Dict] = []
    inventory_ids = set()
    if isinstance(inventory, dict):
        for item in inventory.get("component_packs") or []:
            pack_id = str(item.get("id") or "").strip()
            if pack_id:
                inventory_ids.add(pack_id)
    if component_packs is not None:
        try:
            for entry in component_packs.list_installed_packs():
                manifest = entry.get("manifest") if isinstance(entry, dict) else None
                if not isinstance(manifest, dict):
                    continue
                pack_id = str(manifest.get("pack_id") or "").strip()
                if not pack_id:
                    continue
                if inventory_ids and pack_id not in inventory_ids:
                    continue
                if enabled_pack_ids is not None and pack_id not in enabled_pack_ids:
                    continue
                packs.append(
                    {
                        "pack_id": pack_id,
                        "name": manifest.get("display_name") or pack_id,
                        "version": manifest.get("version"),
                        "components": manifest.get("components") or [],
                        "pack_root": entry.get("pack_root"),
                        "manifest": manifest,
                    }
                )
        except Exception:
            pass
    if packs:
        return packs
    if inventory_ids:
        if enabled_pack_ids is not None:
            inventory_ids = {pack_id for pack_id in inventory_ids if pack_id in enabled_pack_ids}
        return [{"pack_id": pack_id, "name": pack_id, "components": []} for pack_id in inventory_ids]
    return []


def _harness_pack_stub() -> Dict:
    return {
        "pack_id": "harness_pack",
        "name": "Harness Pack",
        "version": "0.0.1",
        "components": [
            {
                "component_id": "harness.block",
                "display_name": "Harness Block",
                "kind": "demo",
                "impl": "harness.impl",
                "params": {"lab_id": "harness"},
            }
        ],
        "pack_root": None,
        "manifest": {},
    }


def _safe_graph_id(value: Optional[str]) -> str:
    text = str(value or "").strip() or "graph"
    return text.replace(":", "_").replace("/", "_").replace("\\", "_")


def _block_graph_id(component_id: str) -> str:
    return f"block:{_safe_graph_id(component_id)}"


def _subcomponent_graph_id(component_id: str, token: str) -> str:
    return f"subcomponent:{_safe_graph_id(component_id)}:{_safe_graph_id(token)}"


def _pack_metadata(pack: Dict, pack_root: Optional[Path]) -> Dict:
    metadata = {
        "pack_id": pack.get("pack_id"),
        "version": pack.get("version"),
        "source": "component_store",
    }
    if pack_root:
        metadata["pack_root"] = str(Path(pack_root))
        metadata["manifest_path"] = str(Path(pack_root) / "component_pack_manifest.json")
    components = pack.get("components")
    if isinstance(components, list):
        metadata["component_count"] = len(components)
    return metadata


def _block_metadata(component: Dict, pack_id: Optional[str], pack_root: Optional[Path]) -> Dict:
    metadata: Dict[str, object] = {
        "component_id": component.get("component_id"),
        "pack_id": pack_id,
        "kind": component.get("kind"),
        "impl": component.get("impl"),
        "declared_by": "component_pack_manifest",
    }
    if pack_root:
        metadata["manifest_path"] = str(Path(pack_root) / "component_pack_manifest.json")
    assets = component.get("assets")
    if isinstance(assets, dict):
        metadata["assets"] = sorted(str(key) for key in assets.keys())
    params = component.get("params")
    if isinstance(params, dict):
        metadata["params"] = sorted(str(key) for key in params.keys())
    deps = _component_dependencies(component)
    if deps:
        metadata["dependencies"] = deps
    return metadata


def _component_dependencies(component: Dict) -> List[str]:
    deps = ["system:component_runtime", "system:app_ui"]
    params = component.get("params")
    if isinstance(params, dict):
        lab_id = params.get("lab_id")
        if isinstance(lab_id, str) and lab_id:
            deps.append(f"lab:{lab_id}")
    return deps


def _dependency_edges(block_id: str, component: Dict) -> Tuple[List[str], List[Edge]]:
    deps = _component_dependencies(component)
    edges = []
    for dep in deps:
        edges.append(Edge(f"edge:{block_id}:{dep}:depends", block_id, dep, "depends"))
    return deps, edges


def _build_block_subgraph(
    graph_id: str,
    block_node: Node,
    component: Dict,
    pack_root: Optional[Path],
) -> Tuple[ArchitectureGraph, Dict[str, ArchitectureGraph]]:
    subgraphs: Dict[str, ArchitectureGraph] = {}
    sub_nodes: List[Node] = [_node_copy(block_node, subgraph_id=None)]
    sub_edges: List[Edge] = []

    token = component.get("impl") or "component"
    subgraph_id = _subcomponent_graph_id(block_node.node_id, token)
    sub_node = Node(
        node_id=subgraph_id,
        title="Implementation",
        node_type="Subcomponent",
        subgraph_id=subgraph_id,
        metadata={
            "component_id": component.get("component_id"),
            "impl": component.get("impl"),
            "kind": component.get("kind"),
        },
    )
    sub_nodes.append(sub_node)
    sub_edges.append(Edge(f"edge:{block_node.node_id}:{sub_node.node_id}", block_node.node_id, sub_node.node_id, "contains"))

    artifact_nodes, artifact_edges = _build_artifacts(sub_node, component, pack_root)
    artifact_nodes.insert(0, _node_copy(sub_node, subgraph_id=None))
    subgraphs[subgraph_id] = ArchitectureGraph(
        graph_id=subgraph_id,
        title=f"{block_node.title} • Implementation",
        nodes=artifact_nodes,
        edges=artifact_edges,
    )

    graph = ArchitectureGraph(
        graph_id=graph_id,
        title=block_node.title,
        nodes=sub_nodes,
        edges=sub_edges,
    )
    return graph, subgraphs


def _build_artifacts(
    sub_node: Node,
    component: Dict,
    pack_root: Optional[Path],
) -> Tuple[List[Node], List[Edge]]:
    nodes: List[Node] = []
    edges: List[Edge] = []
    assets = component.get("assets") if isinstance(component, dict) else None
    if isinstance(assets, dict):
        for key, value in assets.items():
            node_id = f"artifact:{_safe_graph_id(sub_node.node_id)}:{_safe_graph_id(key)}"
            metadata = {"asset_key": key, "path": str(value)}
            if pack_root and isinstance(value, str):
                metadata["resolved_path"] = str(Path(pack_root) / value)
            nodes.append(
                Node(
                    node_id=node_id,
                    title=f"Asset: {key}",
                    node_type="Artifact",
                    metadata=metadata,
                )
            )
            edges.append(Edge(f"edge:{sub_node.node_id}:{node_id}", sub_node.node_id, node_id, "contains"))
    if pack_root:
        manifest_path = Path(pack_root) / "component_pack_manifest.json"
        manifest_node = Node(
            node_id=f"artifact:{_safe_graph_id(sub_node.node_id)}:manifest",
            title="Manifest: component_pack_manifest.json",
            node_type="Artifact",
            metadata={"path": str(manifest_path)},
        )
        nodes.append(manifest_node)
        edges.append(Edge(f"edge:{sub_node.node_id}:{manifest_node.node_id}", sub_node.node_id, manifest_node.node_id, "contains"))
    if not nodes:
        placeholder = Node(
            node_id=f"artifact:{_safe_graph_id(sub_node.node_id)}:none",
            title="No artifacts found",
            node_type="Artifact",
        )
        nodes.append(placeholder)
        edges.append(Edge(f"edge:{sub_node.node_id}:{placeholder.node_id}", sub_node.node_id, placeholder.node_id, "contains"))
    return nodes, edges


def _node_copy(node: Node, *, subgraph_id: Optional[str]) -> Node:
    return Node(
        node_id=node.node_id,
        title=node.title,
        node_type=node.node_type,
        subgraph_id=subgraph_id,
        badges=list(node.badges),
        severity_state=node.severity_state,
        checks=list(node.checks),
        spans=list(node.spans),
        metadata=dict(node.metadata or {}),
    )


def _collect_ui_packs(inventory: Optional[Dict]) -> List[Node]:
    nodes: List[Node] = []
    inventory_ids = set()
    if isinstance(inventory, dict):
        for item in inventory.get("ui_packs") or []:
            pack_id = str(item.get("id") or "").strip()
            if pack_id:
                inventory_ids.add(pack_id)

    packs = []
    if ui_manager is not None:
        repo_root = Path("ui_repo/ui_v1")
        store_root = Path("ui_store/ui_v1")
        try:
            packs = ui_manager.list_packs(repo_root, store_root)
        except Exception:
            packs = []

    if packs:
        for pack in packs:
            if inventory_ids and pack.id not in inventory_ids:
                continue
            if pack.source != "store" and inventory_ids:
                continue
            node_id = f"pack:ui:{pack.id}"
            nodes.append(
                Node(
                    node_id=node_id,
                    title=pack.name,
                    node_type="Pack",
                    badges=badges_from_keys(top=["ui"], bottom=["theme"]),
                    metadata={"pack_id": pack.id, "pack_kind": "ui", "source": pack.source},
                )
            )
    else:
        for pack_id in inventory_ids:
            node_id = f"pack:ui:{pack_id}"
            nodes.append(
                Node(
                    node_id=node_id,
                    title=pack_id,
                    node_type="Pack",
                    badges=badges_from_keys(top=["ui"], bottom=["theme"]),
                    metadata={"pack_id": pack_id, "pack_kind": "ui", "source": "inventory"},
                )
            )

    return nodes


def _collect_builtin_blocks(packed_ids: set) -> List[Dict]:
    results: List[Dict] = []
    if component_registry is None:
        return results
    try:
        registry = component_registry.get_registry()
    except Exception:
        return results
    for meta in registry.list_components():
        component_id = meta.component_id
        if not component_id or component_id in packed_ids:
            continue
        results.append({"component_id": component_id, "display_name": meta.display_name})
    return results


def _request_inventory(ctx: CollectorContext) -> Optional[Dict]:
    if not ctx.bus:
        return None
    try:
        from runtime_bus import topics as BUS_TOPICS

        topic = BUS_TOPICS.CORE_INVENTORY_GET_REQUEST
    except Exception:
        topic = "core.inventory.get.request"
    try:
        response = ctx.bus.request(topic, {}, source="codesee", timeout_ms=1500)
    except Exception:
        return None
    if not response.get("ok"):
        return None
    inventory = response.get("inventory")
    return inventory if isinstance(inventory, dict) else None


def _load_enabled_component_packs(ctx: CollectorContext) -> Optional[set[str]]:
    prefs_root = _workspace_prefs_root(ctx)
    if not prefs_root:
        return None
    config_path = prefs_root / "workspace_config.json"
    if not config_path.exists():
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    enabled = config.get("enabled_component_packs")
    if not isinstance(enabled, list):
        return None
    normalized = {str(item).strip() for item in enabled if str(item).strip()}
    return normalized


def _workspace_prefs_root(ctx: CollectorContext) -> Optional[Path]:
    info = ctx.workspace_info or {}
    if isinstance(info, dict):
        paths = info.get("paths")
        if isinstance(paths, dict):
            prefs = paths.get("prefs")
            if prefs:
                return Path(prefs)
        direct = info.get("path")
        if direct:
            return Path(direct) / "prefs"
    workspace_id = (info.get("id") if isinstance(info, dict) else None) or ctx.workspace_id or "default"
    return Path("data") / "workspaces" / str(workspace_id) / "prefs"
