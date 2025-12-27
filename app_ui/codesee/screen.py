from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from PyQt6 import QtCore, QtWidgets

from app_ui.widgets.app_header import AppHeader
from app_ui.widgets.workspace_selector import WorkspaceSelector

from . import layout_store
from .canvas.scene import GraphScene
from .canvas.view import GraphView
from .demo_graphs import build_demo_root_graph, build_demo_subgraphs
from .graph_model import ArchitectureGraph

DEFAULT_LENS = "atlas"


class CodeSeeScreen(QtWidgets.QWidget):
    def __init__(
        self,
        on_back: Callable[[], None],
        workspace_info_provider: Callable[[], Dict[str, Any]],
        *,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self._workspace_info_provider = workspace_info_provider
        self._lens = DEFAULT_LENS
        self._root_graph = build_demo_root_graph()
        self._subgraphs = build_demo_subgraphs()
        self._graph_stack: list[str] = [self._root_graph.graph_id]
        self._current_graph_id: Optional[str] = None

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

        self.scene = GraphScene(
            on_open_subgraph=self._enter_subgraph,
            on_layout_changed=self._save_layout,
        )
        self.view = GraphView(self.scene)
        layout.addWidget(self.view, stretch=1)

        self._refresh_breadcrumb()

    def open_root(self) -> None:
        self._graph_stack = [self._root_graph.graph_id]
        self._set_graph(self._root_graph.graph_id)

    def on_workspace_changed(self) -> None:
        if not self._current_graph_id:
            return
        self._current_graph_id = None
        self._set_graph(self._graph_stack[-1])

    def save_layout(self) -> None:
        self._save_layout()

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
        if graph_id == self._root_graph.graph_id:
            return self._root_graph
        return self._subgraphs.get(graph_id)

    def _graph_title(self, graph_id: str) -> str:
        graph = self._graph_for_id(graph_id)
        if graph:
            return graph.title
        return graph_id

    def _enter_subgraph(self, graph_id: str) -> None:
        if graph_id not in self._subgraphs:
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
        self._current_graph_id = graph_id
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
