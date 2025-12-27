from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PyQt6 import QtCore, QtWidgets

from app_ui import config as ui_config
from app_ui.widgets.app_header import AppHeader
from app_ui.widgets.workspace_selector import WorkspaceSelector

from . import icon_pack, layout_store, snapshot_io
from .badges import Badge, sort_by_priority
from .canvas.scene import GraphScene
from .canvas.view import GraphView
from .collectors.atlas_builder import build_atlas_graph
from .collectors.base import CollectorContext
from .demo_graphs import build_demo_root_graph, build_demo_subgraphs
from .graph_model import ArchitectureGraph, Node

DEFAULT_LENS = "atlas"
SOURCE_DEMO = "Demo"
SOURCE_ATLAS = "Atlas"
SOURCE_SNAPSHOT = "Snapshot (Latest)"
ICON_STYLE_LABELS = {
    icon_pack.ICON_STYLE_AUTO: "Auto",
    icon_pack.ICON_STYLE_COLOR: "Color",
    icon_pack.ICON_STYLE_MONO: "Mono",
}


class CodeSeeScreen(QtWidgets.QWidget):
    def __init__(
        self,
        on_back: Callable[[], None],
        workspace_info_provider: Callable[[], Dict[str, Any]],
        *,
        bus=None,
        content_adapter=None,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self._workspace_info_provider = workspace_info_provider
        self._bus = bus
        self._content_adapter = content_adapter
        self._lens = DEFAULT_LENS
        self._reduced_motion = ui_config.get_reduced_motion()
        self._icon_style = icon_pack.load_style(self._workspace_id())

        self._demo_root = build_demo_root_graph()
        self._demo_subgraphs = build_demo_subgraphs()
        self._atlas_root: Optional[ArchitectureGraph] = None
        self._atlas_subgraphs: Dict[str, ArchitectureGraph] = {}
        self._snapshot_graph: Optional[ArchitectureGraph] = None

        self._active_root: Optional[ArchitectureGraph] = self._demo_root
        self._active_subgraphs: Dict[str, ArchitectureGraph] = self._demo_subgraphs
        self._source = SOURCE_DEMO
        self._graph_stack: list[str] = [self._demo_root.graph_id]
        self._current_graph_id: Optional[str] = None
        self._current_graph: Optional[ArchitectureGraph] = None

        layout = QtWidgets.QVBoxLayout(self)
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(title="Code See", on_back=self._handle_back, workspace_selector=selector)
        layout.addWidget(header)

        breadcrumb_row = QtWidgets.QHBoxLayout()
        self.back_btn = QtWidgets.QPushButton("Back")
        self.back_btn.clicked.connect(self._back_to_parent)
        breadcrumb_row.addWidget(self.back_btn)
        self.breadcrumb_container = QtWidgets.QWidget()
        self.breadcrumb_layout = QtWidgets.QHBoxLayout(self.breadcrumb_container)
        self.breadcrumb_layout.setContentsMargins(0, 0, 0, 0)
        breadcrumb_row.addWidget(self.breadcrumb_container, stretch=1)
        lens_label = QtWidgets.QLabel(f"Lens: {self._lens}")
        lens_label.setStyleSheet("color: #555;")
        breadcrumb_row.addWidget(lens_label)
        layout.addLayout(breadcrumb_row)

        source_row = QtWidgets.QHBoxLayout()
        source_row.addWidget(QtWidgets.QLabel("Source:"))
        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.addItems([SOURCE_DEMO, SOURCE_ATLAS, SOURCE_SNAPSHOT])
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        source_row.addWidget(self.source_combo)
        self.capture_btn = QtWidgets.QPushButton("Capture Snapshot")
        self.capture_btn.clicked.connect(self._capture_snapshot)
        source_row.addWidget(self.capture_btn)
        self.load_btn = QtWidgets.QPushButton("Load Latest Snapshot")
        self.load_btn.clicked.connect(self._load_latest_snapshot_action)
        source_row.addWidget(self.load_btn)
        source_row.addWidget(QtWidgets.QLabel("Icon Style:"))
        self.style_combo = QtWidgets.QComboBox()
        self.style_combo.addItems(list(ICON_STYLE_LABELS.values()))
        self.style_combo.currentTextChanged.connect(self._on_icon_style_changed)
        source_row.addWidget(self.style_combo)
        source_row.addStretch()
        layout.addLayout(source_row)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: #555;")
        layout.addWidget(self.status_label)

        self.scene = GraphScene(
            on_open_subgraph=self._enter_subgraph,
            on_layout_changed=self._save_layout,
            on_inspect=self._inspect_node,
            icon_style=self._resolved_icon_style(),
        )
        self.view = GraphView(self.scene)
        layout.addWidget(self.view, stretch=1)

        self._sync_style_combo()
        self._update_action_state()
        self._set_active_graphs(self._demo_root, self._demo_subgraphs)

    def open_root(self) -> None:
        if not self._active_root:
            return
        self._graph_stack = [self._active_root.graph_id]
        self._set_graph(self._active_root.graph_id)

    def on_workspace_changed(self) -> None:
        self._icon_style = icon_pack.load_style(self._workspace_id())
        self._sync_style_combo()
        self.scene.set_icon_style(self._resolved_icon_style())
        if self._source == SOURCE_ATLAS:
            self._build_atlas()
            return
        if self._source == SOURCE_SNAPSHOT:
            self._load_latest_snapshot(show_status=False)
            return
        if not self._current_graph_id:
            return
        self._current_graph_id = None
        self._set_graph(self._graph_stack[-1])

    def save_layout(self) -> None:
        self._save_layout()

    def set_reduced_motion(self, value: bool) -> None:
        self._reduced_motion = bool(value)
        self.scene.set_icon_style(self._resolved_icon_style())

    def _handle_back(self) -> None:
        self._save_layout()
        self.on_back()

    def _workspace_id(self) -> str:
        info = self._workspace_info_provider() or {}
        if isinstance(info, dict):
            workspace_id = info.get("id") or info.get("workspace_id")
            if workspace_id:
                return str(workspace_id)
        return "default"

    def _graph_for_id(self, graph_id: str) -> Optional[ArchitectureGraph]:
        if self._active_root and graph_id == self._active_root.graph_id:
            return self._active_root
        return self._active_subgraphs.get(graph_id)

    def _graph_title(self, graph_id: str) -> str:
        graph = self._graph_for_id(graph_id)
        if graph:
            return graph.title
        return graph_id

    def _enter_subgraph(self, graph_id: str) -> None:
        if graph_id not in self._active_subgraphs:
            return
        self._graph_stack.append(graph_id)
        self._set_graph(graph_id)

    def _back_to_parent(self) -> None:
        if len(self._graph_stack) <= 1:
            return
        self._graph_stack.pop()
        self._set_graph(self._graph_stack[-1])

    def _set_graph(self, graph_id: str) -> None:
        self._save_layout()
        graph = self._graph_for_id(graph_id)
        if not graph:
            return
        positions = layout_store.load_positions(self._workspace_id(), self._lens, graph_id)
        self.scene.build_graph(graph, positions)
        self.scene.set_icon_style(self._resolved_icon_style())
        self._current_graph_id = graph_id
        self._current_graph = graph
        self._refresh_breadcrumb()

    def _save_layout(self) -> None:
        if not self._current_graph_id:
            return
        positions = self.scene.node_positions()
        layout_store.save_positions(self._workspace_id(), self._lens, self._current_graph_id, positions)

    def _refresh_breadcrumb(self) -> None:
        while self.breadcrumb_layout.count():
            item = self.breadcrumb_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for idx, graph_id in enumerate(self._graph_stack):
            title = self._graph_title(graph_id)
            btn = QtWidgets.QPushButton(title)
            btn.setFlat(True)
            btn.clicked.connect(lambda _checked=False, index=idx: self._jump_to_index(index))
            self.breadcrumb_layout.addWidget(btn)
            if idx < len(self._graph_stack) - 1:
                sep = QtWidgets.QLabel(">")
                sep.setStyleSheet("color: #666;")
                self.breadcrumb_layout.addWidget(sep)
        self.back_btn.setEnabled(len(self._graph_stack) > 1)

    def _jump_to_index(self, index: int) -> None:
        if index < 0 or index >= len(self._graph_stack):
            return
        self._graph_stack = self._graph_stack[: index + 1]
        self._set_graph(self._graph_stack[-1])

    def _on_source_changed(self, value: str) -> None:
        if value == self._source:
            return
        self._save_layout()
        self._source = value
        self._update_action_state()
        if value == SOURCE_DEMO:
            self._set_active_graphs(self._demo_root, self._demo_subgraphs)
            self.status_label.setText("")
            return
        if value == SOURCE_ATLAS:
            self._build_atlas()
            return
        if value == SOURCE_SNAPSHOT:
            self._load_latest_snapshot(show_status=True)

    def _set_active_graphs(
        self,
        root: ArchitectureGraph,
        subgraphs: Dict[str, ArchitectureGraph],
    ) -> None:
        self._active_root = root
        self._active_subgraphs = subgraphs
        self._graph_stack = [root.graph_id]
        self._current_graph_id = None
        self._current_graph = None
        self._set_graph(root.graph_id)

    def _update_action_state(self) -> None:
        self.capture_btn.setEnabled(self._source in (SOURCE_DEMO, SOURCE_ATLAS))

    def _resolved_icon_style(self) -> str:
        return icon_pack.resolve_style(self._icon_style, self._reduced_motion)

    def _sync_style_combo(self) -> None:
        label = ICON_STYLE_LABELS.get(self._icon_style, "Auto")
        self.style_combo.blockSignals(True)
        self.style_combo.setCurrentText(label)
        self.style_combo.blockSignals(False)

    def _on_icon_style_changed(self, value: str) -> None:
        style = _style_from_label(value)
        self._icon_style = style
        icon_pack.save_style(self._workspace_id(), style)
        self.scene.set_icon_style(self._resolved_icon_style())

    def _inspect_node(self, node: Node, badge: Optional[Badge]) -> None:
        if not self._current_graph:
            return
        dialog = CodeSeeInspectorDialog(node, self._current_graph, badge, parent=self)
        dialog.exec()

    def _build_atlas(self) -> None:
        ctx = CollectorContext(
            workspace_id=self._workspace_id(),
            workspace_info=self._workspace_info_provider() or {},
            bus=self._bus,
            content_adapter=self._content_adapter,
        )
        root, subgraphs = build_atlas_graph(ctx)
        self._atlas_root = root
        self._atlas_subgraphs = subgraphs
        self._set_active_graphs(root, subgraphs)
        self.status_label.setText("Atlas graph ready.")

    def _snapshot_dir(self) -> Path:
        return Path("data") / "workspaces" / self._workspace_id() / "codesee" / "snapshots"

    def _latest_snapshot_path(self) -> Optional[Path]:
        directory = self._snapshot_dir()
        if not directory.exists():
            return None
        snapshots = sorted(directory.glob("*.json"))
        if not snapshots:
            return None
        return snapshots[-1]

    def _sanitize_graph_id(self, graph_id: str) -> str:
        safe = graph_id.replace(":", "_").replace("/", "_")
        return safe or "graph"

    def _capture_snapshot(self) -> None:
        if not self._current_graph:
            self.status_label.setText("No graph loaded to snapshot.")
            return
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        safe_graph = self._sanitize_graph_id(self._current_graph.graph_id)
        path = self._snapshot_dir() / f"{timestamp}_{safe_graph}.json"
        metadata = {
            "source": self._source,
            "workspace_id": self._workspace_id(),
            "graph_id": self._current_graph.graph_id,
        }
        snapshot_io.write_snapshot(self._current_graph, path, metadata)
        self.status_label.setText(f"Snapshot saved: {path.name}")

    def _load_latest_snapshot_action(self) -> None:
        self._load_latest_snapshot(show_status=True)

    def _load_latest_snapshot(self, *, show_status: bool) -> None:
        path = self._latest_snapshot_path()
        if not path:
            if show_status:
                self.status_label.setText("No snapshots found.")
            return
        try:
            graph = snapshot_io.read_snapshot(path)
        except Exception as exc:
            if show_status:
                self.status_label.setText(f"Snapshot load failed: {exc}")
            return
        self._snapshot_graph = graph
        self._set_active_graphs(graph, {})
        if show_status:
            self.status_label.setText(f"Snapshot loaded: {path.name}")


def _style_from_label(label: str) -> str:
    for style, value in ICON_STYLE_LABELS.items():
        if value == label:
            return style
    return icon_pack.ICON_STYLE_AUTO


class CodeSeeInspectorDialog(QtWidgets.QDialog):
    def __init__(
        self,
        node: Node,
        graph: ArchitectureGraph,
        selected_badge: Optional[Badge],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Code See Inspector")
        self.setMinimumWidth(480)

        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel(node.title)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        meta = QtWidgets.QLabel(f"ID: {node.node_id} | Type: {node.node_type}")
        meta.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(meta)

        if selected_badge:
            selected = QtWidgets.QLabel(f"Selected badge: {_format_badge_line(selected_badge)}")
            selected.setWordWrap(True)
            layout.addWidget(selected)

        badges_label = QtWidgets.QLabel("Badges")
        badges_label.setStyleSheet("color: #444;")
        layout.addWidget(badges_label)
        badges_text = QtWidgets.QPlainTextEdit()
        badges_text.setReadOnly(True)
        badges_text.setPlainText(_format_badges(node.badges))
        layout.addWidget(badges_text)

        edges_label = QtWidgets.QLabel("Edges")
        edges_label.setStyleSheet("color: #444;")
        layout.addWidget(edges_label)
        edges_text = QtWidgets.QPlainTextEdit()
        edges_text.setReadOnly(True)
        edges_text.setPlainText(_format_edges(graph, node))
        layout.addWidget(edges_text)

        close_row = QtWidgets.QHBoxLayout()
        close_row.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)


def _format_badges(badges: list[Badge]) -> str:
    if not badges:
        return "No badges."
    lines = []
    for badge in sort_by_priority(badges):
        lines.append(_format_badge_line(badge))
        if badge.detail:
            lines.append(f"  detail: {badge.detail}")
        if badge.timestamp:
            lines.append(f"  timestamp: {badge.timestamp}")
    return "\n".join(lines)


def _format_badge_line(badge: Badge) -> str:
    line = f"{badge.key} ({badge.rail}) - {badge.title}: {badge.summary}"
    return line.strip()


def _format_edges(graph: ArchitectureGraph, node: Node) -> str:
    node_map = graph.node_map()
    outgoing = []
    incoming = []
    for edge in graph.edges:
        if edge.src_node_id == node.node_id:
            dst = node_map.get(edge.dst_node_id)
            dst_label = dst.title if dst else edge.dst_node_id
            outgoing.append(f"{edge.kind} -> {dst_label} ({edge.dst_node_id})")
        if edge.dst_node_id == node.node_id:
            src = node_map.get(edge.src_node_id)
            src_label = src.title if src else edge.src_node_id
            incoming.append(f"{edge.kind} <- {src_label} ({edge.src_node_id})")
    if not outgoing and not incoming:
        return "No edges."
    lines = []
    if outgoing:
        lines.append("Outgoing:")
        lines.extend(f"- {line}" for line in outgoing)
    if incoming:
        lines.append("Incoming:")
        lines.extend(f"- {line}" for line in incoming)
    return "\n".join(lines)
