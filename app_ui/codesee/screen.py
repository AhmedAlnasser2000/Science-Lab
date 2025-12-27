from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app_ui import config as ui_config
from app_ui.widgets.app_header import AppHeader
from app_ui.widgets.workspace_selector import WorkspaceSelector

from . import icon_pack, layout_store, snapshot_index, snapshot_io, view_config
from .badges import Badge, sort_by_priority
from .canvas.scene import GraphScene
from .canvas.view import GraphView
from .collectors.atlas_builder import build_atlas_graph
from .collectors.base import CollectorContext
from .demo_graphs import build_demo_root_graph, build_demo_subgraphs
from .diff import DiffResult, NodeChange, diff_snapshots
from .graph_model import ArchitectureGraph, Node
from .lenses import LENS_ATLAS, LENS_BUS, LENS_CONTENT, LENS_PLATFORM, get_lens, get_lenses

DEFAULT_LENS = LENS_ATLAS
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
        self._lens = view_config.load_last_lens_id(self._workspace_id()) or DEFAULT_LENS
        self._reduced_motion = ui_config.get_reduced_motion()
        self._view_config = view_config.load_view_config(self._workspace_id(), self._lens)
        self._icon_style = self._view_config.icon_style

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
        self._render_graph_id: Optional[str] = None
        self._snapshot_entries: list[dict] = []
        self._diff_mode = False
        self._diff_result: Optional[DiffResult] = None
        self._diff_baseline_graph: Optional[ArchitectureGraph] = None
        self._diff_compare_graph: Optional[ArchitectureGraph] = None

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
        self.lens_label = QtWidgets.QLabel("")
        self.lens_label.setStyleSheet("color: #555;")
        breadcrumb_row.addWidget(self.lens_label)
        layout.addLayout(breadcrumb_row)

        source_row = QtWidgets.QHBoxLayout()
        source_row.addWidget(QtWidgets.QLabel("Lens:"))
        self.lens_combo = QtWidgets.QComboBox()
        self._lens_map = get_lenses()
        for lens_id in [LENS_ATLAS, LENS_PLATFORM, LENS_CONTENT, LENS_BUS]:
            lens = self._lens_map.get(lens_id)
            if lens:
                self.lens_combo.addItem(lens.title, lens_id)
        self.lens_combo.currentIndexChanged.connect(self._on_lens_changed)
        source_row.addWidget(self.lens_combo)
        source_row.addWidget(QtWidgets.QLabel("Source:"))
        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.addItems([SOURCE_DEMO, SOURCE_ATLAS, SOURCE_SNAPSHOT])
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        source_row.addWidget(self.source_combo)
        self.layers_button = QtWidgets.QToolButton()
        self.layers_button.setText("Layers")
        self.layers_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.layers_menu = QtWidgets.QMenu(self.layers_button)
        self.layers_button.setMenu(self.layers_menu)
        source_row.addWidget(self.layers_button)
        self.badges_button = QtWidgets.QToolButton()
        self.badges_button.setText("Badges")
        self.badges_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.badges_menu = QtWidgets.QMenu(self.badges_button)
        self.badges_button.setMenu(self.badges_menu)
        source_row.addWidget(self.badges_button)
        self._only_errors_btn = _make_toggle_button("Only errors", self._on_quick_filter_changed)
        self._only_failures_btn = _make_toggle_button("Only failures", self._on_quick_filter_changed)
        self._only_expecting_btn = _make_toggle_button("Only expecting", self._on_quick_filter_changed)
        source_row.addWidget(self._only_errors_btn)
        source_row.addWidget(self._only_failures_btn)
        source_row.addWidget(self._only_expecting_btn)
        self.capture_btn = QtWidgets.QPushButton("Capture Snapshot")
        self.capture_btn.clicked.connect(self._capture_snapshot)
        source_row.addWidget(self.capture_btn)
        self.load_btn = QtWidgets.QPushButton("Load Latest Snapshot")
        self.load_btn.clicked.connect(self._load_latest_snapshot_action)
        source_row.addWidget(self.load_btn)
        source_row.addWidget(QtWidgets.QLabel("Baseline:"))
        self.baseline_combo = QtWidgets.QComboBox()
        self.baseline_combo.currentIndexChanged.connect(self._on_baseline_changed)
        source_row.addWidget(self.baseline_combo)
        source_row.addWidget(QtWidgets.QLabel("Compare:"))
        self.compare_combo = QtWidgets.QComboBox()
        self.compare_combo.currentIndexChanged.connect(self._on_compare_changed)
        source_row.addWidget(self.compare_combo)
        self.diff_toggle = QtWidgets.QToolButton()
        self.diff_toggle.setText("Diff Mode")
        self.diff_toggle.setCheckable(True)
        self.diff_toggle.toggled.connect(self._on_diff_toggled)
        source_row.addWidget(self.diff_toggle)
        self.removed_button = QtWidgets.QToolButton()
        self.removed_button.setText("Removed")
        self.removed_button.clicked.connect(self._open_removed_dialog)
        source_row.addWidget(self.removed_button)
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

        self._build_layer_menu()
        self._build_badge_menu()
        self._refresh_snapshot_history()
        self._sync_style_combo()
        self._sync_view_controls()
        self._update_action_state()
        self._set_active_graphs(self._demo_root, self._demo_subgraphs)

    def open_root(self) -> None:
        if not self._active_root:
            return
        self._graph_stack = [self._active_root.graph_id]
        self._set_graph(self._active_root.graph_id)

    def on_workspace_changed(self) -> None:
        self._lens = view_config.load_last_lens_id(self._workspace_id()) or DEFAULT_LENS
        self._view_config = view_config.load_view_config(self._workspace_id(), self._lens)
        self._icon_style = self._view_config.icon_style
        self._diff_mode = False
        self._diff_result = None
        self._diff_baseline_graph = None
        self._diff_compare_graph = None
        self._sync_style_combo()
        self._sync_view_controls()
        self.scene.set_icon_style(self._resolved_icon_style())
        self.scene.set_badge_layers(self._view_config.show_badge_layers)
        self._refresh_snapshot_history()
        self.diff_toggle.blockSignals(True)
        self.diff_toggle.setChecked(False)
        self.diff_toggle.blockSignals(False)
        self._update_action_state()
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
        self._current_graph_id = graph_id
        self._current_graph = graph
        self._refresh_breadcrumb()
        self._render_current_graph()

    def _save_layout(self) -> None:
        if not self._render_graph_id:
            return
        positions = self.scene.node_positions()
        layout_store.save_positions(self._workspace_id(), self._lens, self._render_graph_id, positions)

    def _render_current_graph(self) -> None:
        if not self._current_graph_id or not self._current_graph:
            return
        graph_to_render = self._current_graph
        diff_result = None
        if self._diff_mode and self._diff_compare_graph and self._diff_result:
            graph_to_render = self._diff_compare_graph
            diff_result = self._diff_result
        self._render_graph_id = graph_to_render.graph_id
        positions = layout_store.load_positions(self._workspace_id(), self._lens, self._render_graph_id)
        filtered = self._filtered_graph(graph_to_render)
        empty_message = None
        if self._lens == LENS_BUS and not _bus_nodes_present(graph_to_render):
            empty_message = "No bus nodes found for this graph."
            filtered = ArchitectureGraph(
                graph_id=filtered.graph_id,
                title=filtered.title,
                nodes=[],
                edges=[],
            )
        self.scene.set_empty_message(empty_message)
        self.scene.build_graph(filtered, positions, diff_result=diff_result)
        self.scene.set_icon_style(self._resolved_icon_style())
        self.scene.set_badge_layers(self._view_config.show_badge_layers)

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
        lens_title = self._lens_map.get(self._lens).title if self._lens in self._lens_map else self._lens
        self.lens_label.setText(f"Lens: {lens_title}")

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
        self.removed_button.setEnabled(self._diff_mode and self._diff_result is not None)

    def _build_layer_menu(self) -> None:
        self._category_actions: Dict[str, QtGui.QAction] = {}
        self.layers_menu.clear()
        for category in _category_keys():
            action = QtGui.QAction(category, self.layers_menu)
            action.setCheckable(True)
            action.toggled.connect(self._on_category_toggled)
            self.layers_menu.addAction(action)
            self._category_actions[category] = action

    def _build_badge_menu(self) -> None:
        self._badge_actions: Dict[str, QtGui.QAction] = {}
        self.badges_menu.clear()
        for layer_id, label in _badge_layer_labels().items():
            action = QtGui.QAction(label, self.badges_menu)
            action.setCheckable(True)
            action.toggled.connect(self._on_badge_layer_toggled)
            self.badges_menu.addAction(action)
            self._badge_actions[layer_id] = action

    def _sync_view_controls(self) -> None:
        self._sync_lens_combo()
        for category, action in self._category_actions.items():
            action.blockSignals(True)
            action.setChecked(self._view_config.show_categories.get(category, True))
            action.blockSignals(False)
        for layer_id, action in self._badge_actions.items():
            action.blockSignals(True)
            action.setChecked(self._view_config.show_badge_layers.get(layer_id, True))
            action.blockSignals(False)
        self._only_errors_btn.blockSignals(True)
        self._only_errors_btn.setChecked(self._view_config.quick_filters.get("only_errors", False))
        self._only_errors_btn.blockSignals(False)
        self._only_failures_btn.blockSignals(True)
        self._only_failures_btn.setChecked(self._view_config.quick_filters.get("only_failures", False))
        self._only_failures_btn.blockSignals(False)
        self._only_expecting_btn.blockSignals(True)
        self._only_expecting_btn.setChecked(self._view_config.quick_filters.get("only_expecting", False))
        self._only_expecting_btn.blockSignals(False)

    def _sync_lens_combo(self) -> None:
        for idx in range(self.lens_combo.count()):
            lens_id = self.lens_combo.itemData(idx)
            if lens_id == self._lens:
                self.lens_combo.blockSignals(True)
                self.lens_combo.setCurrentIndex(idx)
                self.lens_combo.blockSignals(False)
                return

    def _on_lens_changed(self, index: int) -> None:
        lens_id = self.lens_combo.itemData(index)
        if not lens_id or lens_id == self._lens:
            return
        self._save_layout()
        view_config.save_view_config(
            self._workspace_id(),
            self._view_config,
            last_lens_id=str(lens_id),
            icon_style=self._icon_style,
        )
        self._lens = str(lens_id)
        self._view_config = view_config.load_view_config(self._workspace_id(), self._lens)
        self._icon_style = self._view_config.icon_style
        self._sync_style_combo()
        self._sync_view_controls()
        self._render_current_graph()
        self._refresh_breadcrumb()

    def _on_category_toggled(self, _checked: bool) -> None:
        for category, action in self._category_actions.items():
            self._view_config.show_categories[category] = action.isChecked()
        self._persist_view_config()
        self._render_current_graph()

    def _on_badge_layer_toggled(self, _checked: bool) -> None:
        for layer_id, action in self._badge_actions.items():
            self._view_config.show_badge_layers[layer_id] = action.isChecked()
        self._persist_view_config()
        self.scene.set_badge_layers(self._view_config.show_badge_layers)
        self.scene.update()

    def _on_quick_filter_changed(self) -> None:
        self._view_config.quick_filters["only_errors"] = self._only_errors_btn.isChecked()
        self._view_config.quick_filters["only_failures"] = self._only_failures_btn.isChecked()
        self._view_config.quick_filters["only_expecting"] = self._only_expecting_btn.isChecked()
        self._persist_view_config()
        self._render_current_graph()

    def _persist_view_config(self) -> None:
        view_config.save_view_config(
            self._workspace_id(),
            self._view_config,
            last_lens_id=self._lens,
            icon_style=self._icon_style,
        )

    def _filtered_graph(self, graph: ArchitectureGraph) -> ArchitectureGraph:
        lens = get_lens(self._lens)
        nodes = []
        node_map: Dict[str, Node] = {}
        for node in graph.nodes:
            if not lens.node_predicate(node):
                continue
            if not _category_visible(node, self._view_config.show_categories):
                continue
            if not _passes_quick_filters(node, self._view_config.quick_filters):
                continue
            node_map[node.node_id] = node
            nodes.append(node)
        edges = []
        for edge in graph.edges:
            src = node_map.get(edge.src_node_id)
            dst = node_map.get(edge.dst_node_id)
            if not src or not dst:
                continue
            if not lens.edge_predicate(edge, src, dst):
                continue
            edges.append(edge)
        return ArchitectureGraph(
            graph_id=graph.graph_id,
            title=graph.title,
            nodes=nodes,
            edges=edges,
        )

    def _refresh_snapshot_history(self) -> None:
        self._snapshot_entries = snapshot_index.list_snapshots_sorted(self._workspace_id())
        baseline_path = self.baseline_combo.currentData()
        compare_path = self.compare_combo.currentData()
        self.baseline_combo.blockSignals(True)
        self.compare_combo.blockSignals(True)
        self.baseline_combo.clear()
        self.compare_combo.clear()
        self.baseline_combo.addItem("None", None)
        self.compare_combo.addItem("None", None)
        for entry in self._snapshot_entries:
            label = _snapshot_label(entry)
            path = entry.get("path")
            self.baseline_combo.addItem(label, path)
            self.compare_combo.addItem(label, path)
        if baseline_path:
            _set_combo_by_data(self.baseline_combo, baseline_path)
        if compare_path:
            _set_combo_by_data(self.compare_combo, compare_path)
        self.baseline_combo.blockSignals(False)
        self.compare_combo.blockSignals(False)
        self._update_action_state()

    def _on_baseline_changed(self, _index: int) -> None:
        if self._diff_mode:
            self._update_diff_result()
            self._render_current_graph()

    def _on_compare_changed(self, _index: int) -> None:
        if self._diff_mode:
            self._update_diff_result()
            self._render_current_graph()

    def _on_diff_toggled(self, checked: bool) -> None:
        self._diff_mode = checked
        if checked:
            self._update_diff_result()
        else:
            self._diff_result = None
            self._diff_baseline_graph = None
            self._diff_compare_graph = None
        self._update_action_state()
        self._render_current_graph()

    def _update_diff_result(self) -> None:
        baseline_path = self.baseline_combo.currentData()
        compare_path = self.compare_combo.currentData()
        if not baseline_path or not compare_path or baseline_path == compare_path:
            self._diff_result = None
            self._diff_baseline_graph = None
            self._diff_compare_graph = None
            self.status_label.setText("Select two different snapshots for diff mode.")
            self._update_action_state()
            return
        baseline_graph = self._load_snapshot_by_path(str(baseline_path))
        compare_graph = self._load_snapshot_by_path(str(compare_path))
        if not baseline_graph or not compare_graph:
            self._diff_result = None
            self._diff_baseline_graph = None
            self._diff_compare_graph = None
            self.status_label.setText("Snapshot diff load failed.")
            self._update_action_state()
            return
        self._diff_baseline_graph = baseline_graph
        self._diff_compare_graph = compare_graph
        self._diff_result = diff_snapshots(baseline_graph, compare_graph)
        summary = (
            f"Diff: +{len(self._diff_result.nodes_added)} "
            f"-{len(self._diff_result.nodes_removed)} "
            f"Δ{len(self._diff_result.nodes_changed)}"
        )
        self.status_label.setText(summary)
        self._update_action_state()

    def _load_snapshot_by_path(self, path_value: str) -> Optional[ArchitectureGraph]:
        try:
            return snapshot_io.read_snapshot(Path(path_value))
        except Exception:
            return None

    def _open_removed_dialog(self) -> None:
        if not self._diff_result:
            return
        dialog = CodeSeeRemovedDialog(self._diff_result, parent=self)
        dialog.exec()

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
        self._view_config.icon_style = style
        icon_pack.save_style(self._workspace_id(), style)
        self._persist_view_config()
        self.scene.set_icon_style(self._resolved_icon_style())

    def _inspect_node(self, node: Node, badge: Optional[Badge]) -> None:
        graph = self._current_graph
        if self._diff_mode and self._diff_compare_graph:
            graph = self._diff_compare_graph
        if not graph:
            return
        diff_state = None
        diff_change = None
        if self._diff_mode and self._diff_result:
            if node.node_id in self._diff_result.nodes_added:
                diff_state = "added"
            elif node.node_id in self._diff_result.nodes_changed:
                diff_state = "changed"
                diff_change = self._diff_result.node_change_details.get(node.node_id)
        dialog = CodeSeeInspectorDialog(node, graph, badge, diff_state, diff_change, parent=self)
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
            "lens_id": self._lens,
            "timestamp": timestamp,
        }
        snapshot_io.write_snapshot(self._current_graph, path, metadata)
        self.status_label.setText(f"Snapshot saved: {path.name}")
        self._refresh_snapshot_history()

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


def _make_toggle_button(label: str, handler: Callable[[], None]) -> QtWidgets.QToolButton:
    btn = QtWidgets.QToolButton()
    btn.setText(label)
    btn.setCheckable(True)
    btn.toggled.connect(handler)
    return btn


def _snapshot_label(entry: dict) -> str:
    timestamp = entry.get("timestamp") or entry.get("filename") or "snapshot"
    source = entry.get("source") or "Unknown"
    graph_id = entry.get("graph_id") or "graph"
    return f"{timestamp} | {source} | {graph_id}"


def _set_combo_by_data(combo: QtWidgets.QComboBox, value: Optional[str]) -> None:
    if value is None:
        return
    for idx in range(combo.count()):
        if combo.itemData(idx) == value:
            combo.setCurrentIndex(idx)
            return


def _category_keys() -> list[str]:
    return ["Workspace", "Pack", "Block", "Topic", "Unit", "Lesson", "Activity", "System"]


def _badge_layer_labels() -> Dict[str, str]:
    return {
        "health": "Health",
        "correctness": "Correctness",
        "connectivity": "Connectivity",
        "policy": "Policy",
        "perf": "Performance",
        "activity": "Activity",
    }


def _category_visible(node: Node, categories: Dict[str, bool]) -> bool:
    node_type = (node.node_type or "").strip()
    if node_type in categories:
        return categories.get(node_type, True)
    return True


def _passes_quick_filters(node: Node, quick_filters: Dict[str, bool]) -> bool:
    if not any(quick_filters.values()):
        return True
    badges = node.badges or []
    keys = {badge.key for badge in badges}
    severity = node.effective_severity()
    if quick_filters.get("only_errors"):
        has_error = any(key.startswith("state.error") for key in keys) or severity == "error"
        if not has_error:
            return False
    if quick_filters.get("only_failures"):
        has_failure = "probe.fail" in keys or severity in ("probe.fail", "correctness", "failure")
        if not has_failure:
            return False
    if quick_filters.get("only_expecting"):
        if "expect.value" not in keys:
            return False
    return True


def _bus_nodes_present(graph: ArchitectureGraph) -> bool:
    for node in graph.nodes:
        if node.node_type != "System":
            continue
        token = f"{node.node_id} {node.title}".lower()
        if "bus" in token:
            return True
    return False


class CodeSeeInspectorDialog(QtWidgets.QDialog):
    def __init__(
        self,
        node: Node,
        graph: ArchitectureGraph,
        selected_badge: Optional[Badge],
        diff_state: Optional[str],
        diff_change: Optional[NodeChange],
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

        if diff_state:
            diff_label = QtWidgets.QLabel(f"Diff status: {diff_state}")
            diff_label.setStyleSheet("color: #555;")
            layout.addWidget(diff_label)
            if diff_change:
                diff_details = QtWidgets.QPlainTextEdit()
                diff_details.setReadOnly(True)
                diff_details.setPlainText(_format_diff_change(diff_change))
                layout.addWidget(diff_details)

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


class CodeSeeRemovedDialog(QtWidgets.QDialog):
    def __init__(self, diff_result: DiffResult, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Removed Items")
        self.setMinimumWidth(420)

        layout = QtWidgets.QVBoxLayout(self)
        nodes_label = QtWidgets.QLabel("Removed Nodes")
        nodes_label.setStyleSheet("color: #444;")
        layout.addWidget(nodes_label)
        nodes_text = QtWidgets.QPlainTextEdit()
        nodes_text.setReadOnly(True)
        nodes_text.setPlainText(_format_removed_nodes(diff_result))
        layout.addWidget(nodes_text)

        edges_label = QtWidgets.QLabel("Removed Edges")
        edges_label.setStyleSheet("color: #444;")
        layout.addWidget(edges_label)
        edges_text = QtWidgets.QPlainTextEdit()
        edges_text.setReadOnly(True)
        edges_text.setPlainText(_format_removed_edges(diff_result))
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


def _format_diff_change(change: NodeChange) -> str:
    lines = ["Before:", f"  title: {change.before.title}", f"  type: {change.before.node_type}"]
    lines.append(f"  severity: {change.severity_before}")
    lines.append("  badges:")
    lines.extend(f"    - {_format_badge_line(badge)}" for badge in change.badges_before)
    lines.append("After:")
    lines.append(f"  title: {change.after.title}")
    lines.append(f"  type: {change.after.node_type}")
    lines.append(f"  severity: {change.severity_after}")
    lines.append("  badges:")
    lines.extend(f"    - {_format_badge_line(badge)}" for badge in change.badges_after)
    lines.append(f"Changed fields: {', '.join(change.fields_changed)}")
    return "\n".join(lines)


def _format_removed_nodes(diff_result: DiffResult) -> str:
    if not diff_result.nodes_removed:
        return "No removed nodes."
    return "\n".join(sorted(diff_result.nodes_removed))


def _format_removed_edges(diff_result: DiffResult) -> str:
    if not diff_result.edges_removed:
        return "No removed edges."
    lines = []
    for src, dst, kind in sorted(diff_result.edges_removed):
        lines.append(f"{kind}: {src} -> {dst}")
    return "\n".join(lines)
