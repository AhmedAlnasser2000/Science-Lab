from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

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

    pack_nodes: List[Node] = []
    block_nodes: List[Node] = []
    pack_edges: List[Edge] = []
    pack_subgraphs: Dict[str, ArchitectureGraph] = {}

    component_packs_data = _collect_component_packs(inventory)
    component_ids_in_packs = set()
    for pack in component_packs_data:
        pack_id = pack["pack_id"]
        graph_id = f"pack:component:{pack_id}"
        node = Node(
            node_id=graph_id,
            title=pack.get("name") or pack_id,
            node_type="Pack",
            badges_top=["component"],
            badges_bottom=["blocks"],
            subgraph_id=graph_id,
        )
        pack_nodes.append(node)
        subgraph_nodes: List[Node] = [node]
        subgraph_edges: List[Edge] = []
        for component in pack.get("components", []):
            component_id = component.get("component_id")
            if not component_id:
                continue
            component_ids_in_packs.add(component_id)
            block_id = f"block:{component_id}"
            block_node = Node(
                node_id=block_id,
                title=component.get("display_name") or component_id,
                node_type="Block",
                badges_bottom=["block"],
            )
            block_nodes.append(block_node)
            pack_edges.append(
                Edge(f"edge:{graph_id}:{block_id}", graph_id, block_id, "contains")
            )
            subgraph_nodes.append(block_node)
            subgraph_edges.append(
                Edge(f"edge:{graph_id}:{block_id}", graph_id, block_id, "contains")
            )
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
            badges_top=["builtin"],
            badges_bottom=["blocks"],
            subgraph_id=built_in_id,
        )
        pack_nodes.append(built_in_node)
        subgraph_nodes = [built_in_node]
        subgraph_edges = []
        for block in built_in:
            block_id = f"block:{block['component_id']}"
            block_node = Node(
                node_id=block_id,
                title=block.get("display_name") or block["component_id"],
                node_type="Block",
                badges_bottom=["block"],
            )
            block_nodes.append(block_node)
            pack_edges.append(
                Edge(f"edge:{built_in_id}:{block_id}", built_in_id, block_id, "contains")
            )
            subgraph_nodes.append(block_node)
            subgraph_edges.append(
                Edge(f"edge:{built_in_id}:{block_id}", built_in_id, block_id, "contains")
            )
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
    return result


def _collect_component_packs(inventory: Optional[Dict]) -> List[Dict]:
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
                packs.append(
                    {
                        "pack_id": pack_id,
                        "name": manifest.get("display_name") or pack_id,
                        "version": manifest.get("version"),
                        "components": manifest.get("components") or [],
                    }
                )
        except Exception:
            pass
    if packs:
        return packs
    if inventory_ids:
        return [{"pack_id": pack_id, "name": pack_id, "components": []} for pack_id in inventory_ids]
    return []


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
                    badges_top=["ui"],
                    badges_bottom=["theme"],
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
                    badges_top=["ui"],
                    badges_bottom=["theme"],
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
