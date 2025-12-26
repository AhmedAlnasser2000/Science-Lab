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


@dataclass
class _PackInfo:
    pack_id: str
    name: str
    installed: bool
    enabled: bool
    component_count: int


class _PackRow(QtWidgets.QWidget):
    def __init__(self, info: _PackInfo, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        name_label = QtWidgets.QLabel(info.name)
        name_label.setStyleSheet("font-weight: bold;")
        status_label = QtWidgets.QLabel(_pack_status_label(info))
        status_label.setStyleSheet("color: #666;")
        count_label = QtWidgets.QLabel(f"{info.component_count} {terms.BLOCK.lower()}s")
        count_label.setStyleSheet("color: #777; font-size: 11px;")

        layout.addWidget(name_label)
        layout.addWidget(status_label)
        layout.addWidget(count_label)


class _BlockTile(QtWidgets.QFrame):
    def __init__(
        self,
        entry: _BlockEntry,
        on_open: Optional[Callable[[str], None]],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.entry = entry
        self.on_open = on_open
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame { border: 1px solid #ddd; border-radius: 6px; }")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        top_row = QtWidgets.QHBoxLayout()
        name_label = QtWidgets.QLabel(entry.display_name)
        name_label.setStyleSheet("font-weight: bold;")
        status_label = QtWidgets.QLabel(_status_label(entry.status))
        status_label.setStyleSheet(_status_style(entry.status))
        top_row.addWidget(name_label)
        top_row.addStretch()
        top_row.addWidget(status_label)

        meta_row = QtWidgets.QHBoxLayout()
        pack_label = QtWidgets.QLabel(f"{terms.PACK}: {entry.pack_name}")
        pack_label.setStyleSheet("color: #666;")
        category_label = QtWidgets.QLabel(entry.category or "General")
        category_label.setStyleSheet(
            "color: #444; background: #eee; padding: 2px 6px; border-radius: 8px;"
        )
        meta_row.addWidget(pack_label)
        meta_row.addStretch()
        meta_row.addWidget(category_label)

        desc_label = QtWidgets.QLabel(entry.description)
        desc_label.setStyleSheet("color: #555;")
        desc_label.setWordWrap(True)

        action_row = QtWidgets.QHBoxLayout()
        open_btn = QtWidgets.QPushButton("Open in Sandbox")
        open_btn.setEnabled(bool(on_open and entry.openable))
        open_btn.clicked.connect(self._open)
        action_row.addWidget(open_btn)
        action_row.addStretch()

        layout.addLayout(top_row)
        layout.addLayout(meta_row)
        layout.addWidget(desc_label)
        layout.addLayout(action_row)

    def _open(self) -> None:
        if not self.on_open:
            return
        if not self.entry.openable:
            return
        self.on_open(self.entry.component_id)


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
        self._pack_infos: List[_PackInfo] = []
        self._search_text = ""
        self._selected_pack_id: Optional[str] = None
        self._current_entry: Optional[_BlockEntry] = None

        layout = QtWidgets.QVBoxLayout(self)
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title=f"{terms.BLOCK} Catalog",
            on_back=self.on_back,
            workspace_selector=selector,
        )
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

        self.pack_list = QtWidgets.QListWidget()
        self.pack_list.setMinimumWidth(220)
        self.pack_list.itemSelectionChanged.connect(self._on_pack_selected)
        splitter.addWidget(self.pack_list)

        self.block_list = QtWidgets.QListWidget()
        self.block_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.block_list.itemSelectionChanged.connect(self._on_block_selected)
        splitter.addWidget(self.block_list)

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
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 2)

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
        self._build_block_list()

    def _on_pack_selected(self) -> None:
        item = self.pack_list.currentItem()
        if not item:
            self._selected_pack_id = None
        else:
            pack_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
            self._selected_pack_id = pack_id if isinstance(pack_id, str) else None
        self._build_block_list()

    def refresh_catalog(self) -> None:
        self._entries, self._pack_infos = self._collect_entries()
        self._build_pack_list()
        self._build_block_list()

    def _collect_entries(self) -> tuple[List[_BlockEntry], List[_PackInfo]]:
        entries: List[_BlockEntry] = []
        policy = self._component_policy()
        pack_entries: List[Dict[str, Any]] = []
        installed_ids: set[str] = set()
        pack_info_map: Dict[str, _PackInfo] = {}

        if component_packs is None:
            self.banner.setText("Pack inventory unavailable. Install the runtime to browse packs.")
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
                components = []

            pack_info_map[pack_id] = _PackInfo(
                pack_id=pack_id,
                name=pack_name,
                installed=installed,
                enabled=pack_enabled,
                component_count=len(components),
            )

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
                    or "General"
                )
                description = params.get("description") or component.get("description") or "No description provided."
                docs_path = _resolve_docs_path(pack_root, component.get("assets") or {})

                if not installed:
                    status = "Not installed"
                    reason = f"Install the {terms.PACK.lower()} to use this {terms.BLOCK.lower()}."
                    openable = False
                elif policy and not pack_enabled:
                    status = "Disabled by project"
                    reason = "Enable this Pack in Project Management."
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
            built_in_id = "built_in"
            built_in_entries: List[_BlockEntry] = []
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
                built_in_entries.append(
                    _BlockEntry(
                        component_id=meta.component_id,
                        display_name=meta.display_name or meta.component_id,
                        pack_id=built_in_id,
                        pack_name="Built-in",
                        category="Core",
                        description="Built-in block.",
                        status=status,
                        reason=reason,
                        openable=bool(meta.component_id),
                        docs_path=None,
                    )
                )
            if built_in_entries:
                entries.extend(built_in_entries)
                pack_info_map[built_in_id] = _PackInfo(
                    pack_id=built_in_id,
                    name="Built-in",
                    installed=True,
                    enabled=True,
                    component_count=len(built_in_entries),
                )

        pack_infos = list(pack_info_map.values())
        pack_infos.sort(key=lambda p: p.name.lower())
        return entries, pack_infos

    def _build_pack_list(self) -> None:
        self.pack_list.clear()
        all_item = QtWidgets.QListWidgetItem("All Packs")
        all_item.setData(QtCore.Qt.ItemDataRole.UserRole, None)
        self.pack_list.addItem(all_item)

        for info in self._pack_infos:
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, info.pack_id)
            widget = _PackRow(info)
            item.setSizeHint(widget.sizeHint())
            self.pack_list.addItem(item)
            self.pack_list.setItemWidget(item, widget)

        self.pack_list.setCurrentRow(0)

    def _build_block_list(self) -> None:
        self.block_list.clear()
        entries = self._filtered_entries()
        grouped: Dict[str, List[_BlockEntry]] = {}
        for entry in entries:
            grouped.setdefault(entry.category or "General", []).append(entry)

        for category in sorted(grouped.keys(), key=str.lower):
            header_item = QtWidgets.QListWidgetItem(category)
            header_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            header_item.setBackground(QtGui.QColor("#f0f0f0"))
            header_item.setForeground(QtGui.QColor("#444"))
            self.block_list.addItem(header_item)
            for entry in grouped[category]:
                item = QtWidgets.QListWidgetItem()
                item.setData(QtCore.Qt.ItemDataRole.UserRole, entry)
                tile = _BlockTile(entry, self._open_from_tile if entry.openable else None)
                item.setSizeHint(tile.sizeHint())
                self.block_list.addItem(item)
                self.block_list.setItemWidget(item, tile)

        self._clear_details()

    def _filtered_entries(self) -> List[_BlockEntry]:
        search = self._search_text
        pack_id = self._selected_pack_id
        entries = [
            entry
            for entry in self._entries
            if (not pack_id or entry.pack_id == pack_id)
        ]

        if search:
            entries = [
                entry
                for entry in entries
                if search
                in " ".join(
                    [
                        entry.display_name,
                        entry.component_id,
                        entry.pack_name,
                        entry.pack_id,
                        entry.category,
                    ]
                ).lower()
            ]

        def status_key(entry: _BlockEntry) -> int:
            order = {
                "Enabled": 0,
                "Disabled by project": 1,
                "Not installed": 2,
                "Unavailable": 3,
            }
            return order.get(entry.status, 4)

        entries.sort(key=lambda e: (status_key(e), e.display_name.lower()))
        return entries

    def _on_block_selected(self) -> None:
        item = self.block_list.currentItem()
        if not item:
            self._clear_details()
            return
        data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(data, _BlockEntry):
            self._clear_details()
            return
        self._render_details(data)

    def _render_details(self, entry: _BlockEntry) -> None:
        self.detail_title.setText(f"{terms.BLOCK}: {entry.display_name}")
        self.detail_meta.setText(f"{terms.PACK}: {entry.pack_name} | Category: {entry.category}")
        self.detail_status.setText(_status_label(entry.status))
        self.detail_reason.setText(entry.reason)
        self.detail_description.setText(entry.description)
        self.open_btn.setEnabled(bool(self.on_open_block and entry.openable))
        self.docs_btn.setEnabled(bool(entry.docs_path))
        self._current_entry = entry

    def _clear_details(self) -> None:
        self._current_entry = None
        self.detail_title.setText("Select a block to view details.")
        self.detail_meta.setText("")
        self.detail_status.setText("")
        self.detail_reason.setText("")
        self.detail_description.setText("")
        self.open_btn.setEnabled(False)
        self.docs_btn.setEnabled(False)

    def _open_from_tile(self, component_id: str) -> None:
        if not self.on_open_block:
            return
        self.on_open_block(component_id)

    def _open_selected(self) -> None:
        if not self._current_entry:
            return
        entry = self._current_entry
        if not self.on_open_block:
            QtWidgets.QMessageBox.warning(self, terms.BLOCK, "Block runtime unavailable.")
            return
        if not entry.openable:
            QtWidgets.QMessageBox.information(self, terms.BLOCK, entry.reason)
            return
        self.on_open_block(entry.component_id)

    def _open_docs(self) -> None:
        if not self._current_entry or not self._current_entry.docs_path:
            return
        if not self._current_entry.docs_path.exists():
            QtWidgets.QMessageBox.warning(self, "Docs", "Documentation file not found.")
            return
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(str(self._current_entry.docs_path))
        )


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
        return "Enabled ✅"
    if status == "Disabled by project":
        return "Disabled ⛔"
    if status == "Not installed":
        return "Not installed"
    if status == "Unavailable":
        return "Unavailable"
    return status


def _status_style(status: str) -> str:
    if status == "Enabled":
        return "color: #1b7f3a; font-weight: bold;"
    if status == "Disabled by project":
        return "color: #b14a00; font-weight: bold;"
    if status == "Not installed":
        return "color: #666;"
    if status == "Unavailable":
        return "color: #a33;"
    return "color: #333;"


def _pack_status_label(info: _PackInfo) -> str:
    if not info.installed:
        return "Not installed"
    if info.enabled:
        return "Enabled ✅"
    return "Disabled ⛔"
