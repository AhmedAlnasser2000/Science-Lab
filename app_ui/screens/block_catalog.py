from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app_ui.ui_helpers import terms
from app_ui.ui_helpers.component_policy import (
    WorkspaceComponentPolicy,
    _get_global_component_policy,
)
from app_ui.widgets.app_header import AppHeader
from app_ui.widgets.workspace_selector import WorkspaceSelector

try:
    from component_runtime import packs as component_packs
    from component_runtime import registry as component_registry
except Exception:  # pragma: no cover
    component_packs = None
    component_registry = None


@dataclass
class _BlockEntry:
    component_id: str
    display_name: str
    pack_id: str
    pack_name: str
    category: str
    description: str
    status: str
    reason: str
    openable: bool
    docs_path: Optional[Path]


class BlockCatalogScreen(QtWidgets.QWidget):
    def __init__(
        self,
        *,
        on_back: Callable[[], None],
        on_open_block: Optional[Callable[[str], None]] = None,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
        component_policy_provider: Optional[Callable[[], "WorkspaceComponentPolicy"]] = None,
        bus=None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_open_block = on_open_block
        self.component_policy_provider = component_policy_provider
        self.bus = bus
        self._entries: List[_BlockEntry] = []
        self._search_text = ""

        layout = QtWidgets.QVBoxLayout(self)
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title=f"{terms.BLOCK} Catalog",
            on_back=self.on_back,
            workspace_selector=selector,
        )
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_catalog)
        header.add_action_widget(refresh_btn)
        layout.addWidget(header)

        banner = QtWidgets.QLabel("")
        banner.setStyleSheet("color: #a33;")
        banner.setVisible(False)
        self.banner = banner
        layout.addWidget(banner)

        search_row = QtWidgets.QHBoxLayout()
        search_row.addWidget(QtWidgets.QLabel("Search:"))
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Filter blocks by name, pack, or category...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_edit, stretch=1)
        layout.addLayout(search_row)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, stretch=1)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels([terms.BLOCK, terms.PACK, "Status"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnCount(3)
        header_view = self.tree.header()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.tree)

        detail_widget = QtWidgets.QWidget()
        detail_layout = QtWidgets.QVBoxLayout(detail_widget)
        self.detail_title = QtWidgets.QLabel("Select a block to view details.")
        self.detail_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.detail_meta = QtWidgets.QLabel("")
        self.detail_meta.setStyleSheet("color: #555;")
        self.detail_status = QtWidgets.QLabel("")
        self.detail_status.setStyleSheet("color: #333; font-weight: bold;")
        self.detail_reason = QtWidgets.QLabel("")
        self.detail_reason.setStyleSheet("color: #777;")
        self.detail_description = QtWidgets.QLabel("")
        self.detail_description.setWordWrap(True)

        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_meta)
        detail_layout.addWidget(self.detail_status)
        detail_layout.addWidget(self.detail_reason)
        detail_layout.addWidget(self.detail_description)

        btn_row = QtWidgets.QHBoxLayout()
        self.open_btn = QtWidgets.QPushButton("Open in Sandbox")
        self.open_btn.clicked.connect(self._open_selected)
        self.open_btn.setEnabled(False)
        self.docs_btn = QtWidgets.QPushButton("Open Docs")
        self.docs_btn.clicked.connect(self._open_docs)
        self.docs_btn.setEnabled(False)
        btn_row.addWidget(self.open_btn)
        btn_row.addWidget(self.docs_btn)
        btn_row.addStretch()
        detail_layout.addLayout(btn_row)

        splitter.addWidget(detail_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        self.refresh_catalog()

    def _component_policy(self) -> Optional[WorkspaceComponentPolicy]:
        if self.component_policy_provider:
            try:
                return self.component_policy_provider()
            except Exception:
                return None
        return _get_global_component_policy()

    def on_workspace_changed(self) -> None:
        self.refresh_catalog()

    def _on_search_changed(self, text: str) -> None:
        self._search_text = text.strip().lower()
        self._build_tree()

    def refresh_catalog(self) -> None:
        self._entries = self._collect_entries()
        self._build_tree()

    def _collect_entries(self) -> List[_BlockEntry]:
        entries: List[_BlockEntry] = []
        policy = self._component_policy()
        pack_entries: List[Dict[str, Any]] = []
        installed_ids: set[str] = set()

        if component_packs is None:
            self.banner.setText("Component packs unavailable. Install the runtime to browse packs.")
            self.banner.setVisible(True)
        else:
            self.banner.setVisible(False)
            try:
                pack_entries = component_packs.list_repo_packs()
            except Exception:
                pack_entries = []
            try:
                installed = component_packs.list_installed_packs()
            except Exception:
                installed = []
            installed_ids = {str(p.get("pack_id") or "").strip() for p in installed if p.get("pack_id")}

        pack_component_ids: set[str] = set()
        registry_available = component_registry is not None
        registry = component_registry.get_registry() if registry_available else None

        for pack in pack_entries:
            manifest = pack.get("manifest") if isinstance(pack, dict) else None
            if not isinstance(manifest, dict):
                continue
            pack_id = str(manifest.get("pack_id") or "").strip()
            if not pack_id:
                continue
            pack_name = manifest.get("display_name") or pack_id
            pack_root = pack.get("pack_root") if isinstance(pack, dict) else None
            installed = pack_id in installed_ids
            pack_enabled = policy.is_pack_enabled(pack_id) if policy else True
            components = manifest.get("components") or []
            if not isinstance(components, list):
                continue
            for component in components:
                if not isinstance(component, dict):
                    continue
                component_id = component.get("component_id")
                if not isinstance(component_id, str) or not component_id:
                    continue
                pack_component_ids.add(component_id)
                display_name = component.get("display_name") or component_id
                params = component.get("params") or {}
                category = (
                    params.get("category")
                    or params.get("topic")
                    or component.get("category")
                    or component.get("topic")
                    or "Other"
                )
                description = params.get("description") or component.get("description") or "No description provided."
                docs_path = _resolve_docs_path(pack_root, component.get("assets") or {})

                if not installed:
                    status = "Not installed"
                    reason = f"Install the {terms.PACK.lower()} to use this {terms.BLOCK.lower()}."
                    openable = False
                elif policy and not pack_enabled:
                    status = "Disabled by project"
                    reason = "Disabled by project. Enable the pack in Project Management."
                    openable = False
                else:
                    if registry and registry.get_component(component_id):
                        status = "Enabled"
                        reason = "Enabled in this project."
                        openable = True
                    else:
                        status = "Unavailable"
                        reason = "Component not registered."
                        openable = False

                entries.append(
                    _BlockEntry(
                        component_id=component_id,
                        display_name=display_name,
                        pack_id=pack_id,
                        pack_name=pack_name,
                        category=str(category),
                        description=description,
                        status=status,
                        reason=reason,
                        openable=openable,
                        docs_path=docs_path,
                    )
                )

        if registry:
            for meta in registry.list_components():
                if meta.component_id in pack_component_ids:
                    continue
                if not meta.component_id:
                    continue
                status = "Enabled"
                reason = "Enabled in this project."
                if policy and not policy.is_component_enabled(meta.component_id):
                    status = "Disabled by project"
                    reason = "Disabled by project."
                entries.append(
                    _BlockEntry(
                        component_id=meta.component_id,
                        display_name=meta.display_name or meta.component_id,
                        pack_id="built_in",
                        pack_name="Built-in",
                        category="Core",
                        description="Built-in block.",
                        status=status,
                        reason=reason,
                        openable=bool(meta.component_id),
                        docs_path=None,
                    )
                )

        return entries

    def _build_tree(self) -> None:
        self.tree.clear()
        search = self._search_text
        packs: Dict[str, Dict[str, List[_BlockEntry]]] = {}

        for entry in self._entries:
            if search:
                haystack = " ".join(
                    [
                        entry.display_name,
                        entry.component_id,
                        entry.pack_name,
                        entry.pack_id,
                        entry.category,
                    ]
                ).lower()
                if search not in haystack:
                    continue
            packs.setdefault(entry.pack_name, {})
            packs[entry.pack_name].setdefault(entry.category, [])
            packs[entry.pack_name][entry.category].append(entry)

        for pack_name, categories in sorted(packs.items(), key=lambda item: item[0].lower()):
            pack_item = QtWidgets.QTreeWidgetItem([pack_name, "", ""])
            pack_item.setExpanded(True)
            for category, entries in sorted(categories.items(), key=lambda item: item[0].lower()):
                category_item = QtWidgets.QTreeWidgetItem([category, "", ""])
                category_item.setExpanded(True)
                for entry in sorted(entries, key=lambda e: e.display_name.lower()):
                    item = QtWidgets.QTreeWidgetItem([
                        entry.display_name,
                        entry.pack_name,
                        _status_label(entry.status),
                    ])
                    item.setData(0, QtCore.Qt.ItemDataRole.UserRole, entry)
                    category_item.addChild(item)
                pack_item.addChild(category_item)
            self.tree.addTopLevelItem(pack_item)

        if self.tree.topLevelItemCount() == 0:
            self.detail_title.setText("No blocks found.")
            self.open_btn.setEnabled(False)
            self.docs_btn.setEnabled(False)

    def _on_selection_changed(self) -> None:
        item = self.tree.currentItem()
        if not item:
            self._clear_details()
            return
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(data, _BlockEntry):
            self._clear_details()
            return
        self.detail_title.setText(f"{terms.BLOCK}: {data.display_name}")
        self.detail_meta.setText(f"{terms.PACK}: {data.pack_name} | Category: {data.category}")
        self.detail_status.setText(_status_label(data.status))
        self.detail_reason.setText(data.reason)
        self.detail_description.setText(data.description)
        self.open_btn.setEnabled(bool(self.on_open_block and data.openable))
        self.docs_btn.setEnabled(bool(data.docs_path))

    def _clear_details(self) -> None:
        self.detail_title.setText("Select a block to view details.")
        self.detail_meta.setText("")
        self.detail_status.setText("")
        self.detail_reason.setText("")
        self.detail_description.setText("")
        self.open_btn.setEnabled(False)
        self.docs_btn.setEnabled(False)

    def _open_selected(self) -> None:
        item = self.tree.currentItem()
        if not item:
            return
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(data, _BlockEntry):
            return
        if not self.on_open_block:
            QtWidgets.QMessageBox.warning(self, terms.BLOCK, "Block runtime unavailable.")
            return
        if not data.openable:
            QtWidgets.QMessageBox.information(self, terms.BLOCK, data.reason)
            return
        self.on_open_block(data.component_id)

    def _open_docs(self) -> None:
        item = self.tree.currentItem()
        if not item:
            return
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(data, _BlockEntry) or not data.docs_path:
            return
        if not data.docs_path.exists():
            QtWidgets.QMessageBox.warning(self, "Docs", "Documentation file not found.")
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(data.docs_path)))


def _resolve_docs_path(pack_root: Optional[Path], assets: Dict[str, Any]) -> Optional[Path]:
    if not isinstance(assets, dict):
        return None
    doc_path = assets.get("docs") or assets.get("doc") or assets.get("markdown")
    if not isinstance(doc_path, str) or not doc_path:
        return None
    if pack_root is None:
        pack_root = Path(".")
    return (Path(pack_root) / doc_path).resolve()


def _status_label(status: str) -> str:
    if status == "Enabled":
        return "Enabled (ok)"
    if status == "Disabled by project":
        return "Disabled (project)"
    if status == "Not installed":
        return "Not installed"
    if status == "Unavailable":
        return "Unavailable"
    return status
