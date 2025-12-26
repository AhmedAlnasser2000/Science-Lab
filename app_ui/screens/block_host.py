from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6 import QtCore, QtWidgets

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
    from component_runtime.host import ComponentHost
except Exception:  # pragma: no cover
    component_packs = None
    component_registry = None
    ComponentHost = None


@dataclass
class _SessionEntry:
    component_id: str
    display_name: str


class BlockHostScreen(QtWidgets.QWidget):
    def __init__(
        self,
        *,
        on_back: Callable[[], None],
        context_provider: Callable[[], Any],
        prefs_root_provider: Callable[[], Path],
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
        component_policy_provider: Optional[Callable[[], "WorkspaceComponentPolicy"]] = None,
        open_picker: Optional[Callable[[Callable[[str], None]], None]] = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.context_provider = context_provider
        self.prefs_root_provider = prefs_root_provider
        self.component_policy_provider = component_policy_provider
        self.open_picker = open_picker

        self._session_entries: List[_SessionEntry] = []
        self._active_component_id: Optional[str] = None
        self._component_pack_map: Dict[str, str] = {}
        self._installed_pack_ids: set[str] = set()
        self._available_pack_ids: set[str] = set()
        self._component_name_map: Dict[str, str] = {}
        self._skip_messages: List[str] = []

        layout = QtWidgets.QVBoxLayout(self)
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title=f"{terms.BLOCK} Host",
            on_back=self.on_back,
            workspace_selector=selector,
        )
        layout.addWidget(header)

        self.banner = QtWidgets.QLabel("")
        self.banner.setStyleSheet("color: #a33;")
        self.banner.setVisible(False)
        layout.addWidget(self.banner)

        actions_row = QtWidgets.QHBoxLayout()
        self.add_btn = QtWidgets.QPushButton("Add Block…")
        self.add_btn.clicked.connect(self._open_picker)
        actions_row.addWidget(self.add_btn)
        self.clear_btn = QtWidgets.QPushButton("Clear Session")
        self.clear_btn.clicked.connect(self._clear_session)
        actions_row.addWidget(self.clear_btn)
        actions_row.addStretch()
        layout.addLayout(actions_row)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, stretch=1)

        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QtWidgets.QLabel("Session"))
        self.session_list = QtWidgets.QListWidget()
        self.session_list.itemSelectionChanged.connect(self._on_session_selected)
        self.session_list.itemDoubleClicked.connect(self._activate_selected)
        left_layout.addWidget(self.session_list, stretch=1)

        session_buttons = QtWidgets.QHBoxLayout()
        self.activate_btn = QtWidgets.QPushButton("Activate")
        self.activate_btn.clicked.connect(self._activate_selected)
        session_buttons.addWidget(self.activate_btn)
        self.close_btn = QtWidgets.QPushButton("Close")
        self.close_btn.clicked.connect(self._close_selected)
        session_buttons.addWidget(self.close_btn)
        session_buttons.addStretch()
        left_layout.addLayout(session_buttons)
        splitter.addWidget(left_panel)

        self.host_container = QtWidgets.QWidget()
        host_layout = QtWidgets.QVBoxLayout(self.host_container)
        host_layout.setContentsMargins(0, 0, 0, 0)

        if ComponentHost is None or component_registry is None:
            error = QtWidgets.QLabel("Block runtime unavailable.")
            error.setStyleSheet("color: #b00;")
            host_layout.addWidget(error)
            self._host = None
        else:
            self._host = ComponentHost()
            host_layout.addWidget(self._host, stretch=1)

        self.empty_label = QtWidgets.QLabel("No blocks open. Click Add Block…")
        self.empty_label.setStyleSheet("color: #666;")
        host_layout.addWidget(self.empty_label)
        splitter.addWidget(self.host_container)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        self._refresh_registry_cache()
        self._load_session()

    def on_workspace_changed(self) -> None:
        self._refresh_registry_cache()
        self._load_session()

    def open_empty(self) -> None:
        self._session_entries = []
        self._active_component_id = None
        self._save_session()
        self._render_session()
        self._show_empty_state()

    def add_block(self, component_id: str, *, activate: bool = True) -> None:
        if not component_id:
            return
        if any(entry.component_id == component_id for entry in self._session_entries):
            if activate:
                self._set_active(component_id)
            return
        openable, _status, reason = self._component_status(component_id)
        if not openable:
            self._show_banner(reason)
            return
        display_name = self._component_name_map.get(component_id) or component_id
        self._session_entries.append(_SessionEntry(component_id=component_id, display_name=display_name))
        if activate:
            self._active_component_id = component_id
        self._save_session()
        self._render_session()
        if activate:
            self._mount_active()

    def _open_picker(self) -> None:
        if not self.open_picker:
            self._show_banner("Block picker unavailable.")
            return

        def _pick(component_id: str) -> None:
            self.add_block(component_id, activate=True)

        self.open_picker(_pick)

    def _clear_session(self) -> None:
        confirm = QtWidgets.QMessageBox.question(
            self,
            f"Clear {terms.BLOCK} Session",
            "Clear the current session?",
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.open_empty()

    def _on_session_selected(self) -> None:
        # Keep buttons enabled based on selection
        has_selection = bool(self.session_list.currentItem())
        self.activate_btn.setEnabled(has_selection)
        self.close_btn.setEnabled(has_selection)

    def _activate_selected(self) -> None:
        item = self.session_list.currentItem()
        if not item:
            return
        component_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(component_id, str):
            return
        self._set_active(component_id)

    def _close_selected(self) -> None:
        item = self.session_list.currentItem()
        if not item:
            return
        component_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(component_id, str):
            return
        self._session_entries = [e for e in self._session_entries if e.component_id != component_id]
        if self._active_component_id == component_id:
            self._active_component_id = self._session_entries[0].component_id if self._session_entries else None
        self._save_session()
        self._render_session()
        self._mount_active()

    def _set_active(self, component_id: str) -> None:
        if component_id == self._active_component_id:
            return
        self._active_component_id = component_id
        self._save_session()
        self._render_session()
        self._mount_active()

    def _render_session(self) -> None:
        self.session_list.clear()
        for entry in self._session_entries:
            item = QtWidgets.QListWidgetItem(entry.display_name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entry.component_id)
            self.session_list.addItem(item)
            if entry.component_id == self._active_component_id:
                item.setSelected(True)
        self.activate_btn.setEnabled(bool(self.session_list.currentItem()))
        self.close_btn.setEnabled(bool(self.session_list.currentItem()))

    def _mount_active(self) -> None:
        if self._active_component_id is None:
            self._show_empty_state()
            return
        if component_registry is None or self._host is None:
            self._show_banner("Block runtime unavailable.")
            return
        openable, _status, reason = self._component_status(self._active_component_id)
        if not openable:
            self._show_banner(reason)
            self._show_empty_state()
            return
        component = component_registry.get_registry().get_component(self._active_component_id)
        if not component:
            self._show_banner("Block not registered.")
            self._show_empty_state()
            return
        context = self.context_provider()
        self._host.mount(component, context)
        self.empty_label.setVisible(False)
        self.banner.setVisible(False)

    def _show_empty_state(self) -> None:
        if self._host is not None:
            self._host.unmount()
        self.empty_label.setVisible(True)

    def _show_banner(self, message: str) -> None:
        self.banner.setText(message)
        self.banner.setVisible(True)

    def _load_session(self) -> None:
        self._skip_messages = []
        session_path = self._session_path()
        if not session_path.exists():
            self._session_entries = []
            self._active_component_id = None
            self._render_session()
            self._show_empty_state()
            return
        try:
            data = json.loads(session_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        open_blocks = data.get("open_blocks") if isinstance(data, dict) else None
        active_block = data.get("active_block") if isinstance(data, dict) else None
        if not isinstance(open_blocks, list):
            open_blocks = []
        self._session_entries = []
        for component_id in open_blocks:
            if not isinstance(component_id, str):
                continue
            openable, _status, reason = self._component_status(component_id)
            if not openable:
                self._skip_messages.append(f"{component_id}: {reason}")
                continue
            display_name = self._component_name_map.get(component_id) or component_id
            self._session_entries.append(_SessionEntry(component_id, display_name))
        self._active_component_id = active_block if isinstance(active_block, str) else None
        if self._active_component_id and not any(
            entry.component_id == self._active_component_id for entry in self._session_entries
        ):
            self._active_component_id = None
        if not self._active_component_id and self._session_entries:
            self._active_component_id = self._session_entries[0].component_id
        self._render_session()
        self._mount_active()
        if self._skip_messages:
            self._show_banner("Skipped blocks: " + "; ".join(self._skip_messages))
        else:
            self.banner.setVisible(False)

    def _save_session(self) -> None:
        session_path = self._session_path()
        data = {
            "open_blocks": [entry.component_id for entry in self._session_entries],
            "active_block": self._active_component_id,
        }
        try:
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _session_path(self) -> Path:
        prefs_root = self.prefs_root_provider()
        return prefs_root / "block_host_session.json"

    def _refresh_registry_cache(self) -> None:
        self._component_pack_map = {}
        self._installed_pack_ids = set()
        self._available_pack_ids = set()
        self._component_name_map = {}

        if component_registry is not None:
            registry = component_registry.get_registry()
            for meta in registry.list_components():
                if meta.component_id:
                    self._component_name_map[meta.component_id] = meta.display_name or meta.component_id

        if component_packs is None:
            return
        try:
            repo_packs = component_packs.list_repo_packs()
        except Exception:
            repo_packs = []
        try:
            installed_packs = component_packs.list_installed_packs()
        except Exception:
            installed_packs = []
        self._installed_pack_ids = {
            str(pack.get("pack_id") or "").strip()
            for pack in installed_packs
            if pack.get("pack_id")
        }
        for pack in repo_packs:
            manifest = pack.get("manifest") if isinstance(pack, dict) else None
            if not isinstance(manifest, dict):
                continue
            pack_id = str(manifest.get("pack_id") or "").strip()
            if not pack_id:
                continue
            self._available_pack_ids.add(pack_id)
            components = manifest.get("components") or []
            if not isinstance(components, list):
                continue
            for component in components:
                if not isinstance(component, dict):
                    continue
                component_id = component.get("component_id")
                if isinstance(component_id, str) and component_id:
                    self._component_pack_map[component_id] = pack_id
                    if component_id not in self._component_name_map:
                        display_name = component.get("display_name") or component_id
                        self._component_name_map[component_id] = display_name

    def _component_status(self, component_id: str) -> Tuple[bool, str, str]:
        if not component_id:
            return False, "Unavailable", "Invalid block id."
        policy = self._component_policy()
        pack_id = self._component_pack_map.get(component_id)
        if pack_id and pack_id not in self._installed_pack_ids:
            return False, "Not installed", f"Install the {terms.PACK.lower()} to use this block."
        if policy and pack_id and not policy.is_pack_enabled(pack_id):
            return False, "Disabled by project", "Enable this Pack in Project Settings."
        if policy and not policy.is_component_enabled(component_id):
            return False, "Disabled by project", "Enable this Pack in Project Settings."
        if component_registry is None:
            return False, "Unavailable", "Block runtime unavailable."
        component = component_registry.get_registry().get_component(component_id)
        if not component:
            return False, "Unavailable", "Block not registered."
        return True, "Enabled", "Enabled in this project."

    def _component_policy(self) -> Optional[WorkspaceComponentPolicy]:
        if self.component_policy_provider:
            try:
                return self.component_policy_provider()
            except Exception:
                return None
        return _get_global_component_policy()
