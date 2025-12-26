from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

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
    from component_runtime.host import ComponentHost
except Exception:  # pragma: no cover
    component_packs = None
    component_registry = None
    ComponentHost = None


@dataclass
class _SessionEntry:
    component_id: str
    display_name: str
    pack_name: str
    status: str
    reason: str
    openable: bool


class _SessionRow(QtWidgets.QWidget):
    def __init__(self, entry: _SessionEntry, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        title = QtWidgets.QLabel(entry.display_name)
        title.setStyleSheet("font-weight: bold;")
        pack_badge = QtWidgets.QLabel(entry.pack_name)
        pack_badge.setStyleSheet(
            "color: #333; background: #eee; padding: 2px 6px; border-radius: 8px;"
        )
        status_label = QtWidgets.QLabel(_status_label(entry))
        status_label.setStyleSheet(_status_style(entry.status))

        layout.addWidget(title)
        layout.addWidget(pack_badge)
        layout.addStretch()
        layout.addWidget(status_label)


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
        self._pack_name_map: Dict[str, str] = {}
        self._installed_pack_ids: set[str] = set()
        self._available_pack_ids: set[str] = set()
        self._component_name_map: Dict[str, str] = {}
        self._skipped_ids: List[str] = []
        self._skipped_reasons: Dict[str, str] = {}

        layout = QtWidgets.QVBoxLayout(self)
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title=f"{terms.BLOCK} Host",
            on_back=self.on_back,
            workspace_selector=selector,
        )
        layout.addWidget(header)

        banner_row = QtWidgets.QHBoxLayout()
        self.banner = QtWidgets.QLabel("")
        self.banner.setStyleSheet("color: #a33;")
        self.banner.setVisible(False)
        banner_row.addWidget(self.banner)
        banner_row.addStretch()
        self.remove_skipped_btn = QtWidgets.QPushButton("Remove missing/unavailable")
        self.remove_skipped_btn.clicked.connect(self._remove_skipped)
        self.remove_skipped_btn.setVisible(False)
        banner_row.addWidget(self.remove_skipped_btn)
        layout.addLayout(banner_row)

        actions_row = QtWidgets.QHBoxLayout()
        self.add_btn = QtWidgets.QPushButton("Add Block…")
        self.add_btn.clicked.connect(self._open_picker)
        actions_row.addWidget(self.add_btn)
        self.close_active_btn = QtWidgets.QPushButton("Close Active")
        self.close_active_btn.clicked.connect(self._close_active)
        actions_row.addWidget(self.close_active_btn)
        self.close_others_btn = QtWidgets.QPushButton("Close Others")
        self.close_others_btn.clicked.connect(self._close_others)
        actions_row.addWidget(self.close_others_btn)
        self.close_all_btn = QtWidgets.QPushButton("Close All")
        self.close_all_btn.clicked.connect(self._close_all)
        actions_row.addWidget(self.close_all_btn)
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

    def start_template(self, template: Dict[str, Any]) -> None:
        if not isinstance(template, dict):
            self._show_banner("Template unavailable.")
            return
        open_first = template.get("open_first") if isinstance(template.get("open_first"), str) else None
        recommended = [cid for cid in template.get("recommended_blocks") or [] if isinstance(cid, str)]
        if open_first and open_first not in recommended:
            recommended.insert(0, open_first)

        self._session_entries = []
        self._active_component_id = None
        self._skipped_ids = []
        self._skipped_reasons = {}

        for component_id in recommended:
            entry = self._build_entry(component_id)
            if entry is None or not entry.openable:
                reason = entry.reason if entry else "Unavailable"
                self._skipped_ids.append(component_id)
                self._skipped_reasons[component_id] = reason
                continue
            self._session_entries.append(entry)

        if open_first:
            for entry in self._session_entries:
                if entry.component_id == open_first and entry.openable:
                    self._active_component_id = entry.component_id
                    break
        if not self._active_component_id and self._session_entries:
            self._active_component_id = self._session_entries[0].component_id

        self._save_session()
        self._render_session()
        self._mount_active()
        self._update_skipped_banner()

    def add_block(self, component_id: str, *, activate: bool = True) -> None:
        if not component_id:
            return
        if any(entry.component_id == component_id for entry in self._session_entries):
            if activate:
                self._set_active(component_id)
            return
        entry = self._build_entry(component_id)
        if entry is None:
            self._show_banner("Block not available.")
            return
        if not entry.openable:
            self._show_banner(entry.reason)
            return
        self._session_entries.append(entry)
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

    def _close_active(self) -> None:
        if not self._active_component_id:
            return
        self._session_entries = [
            entry for entry in self._session_entries if entry.component_id != self._active_component_id
        ]
        self._active_component_id = self._session_entries[0].component_id if self._session_entries else None
        self._save_session()
        self._render_session()
        self._mount_active()

    def _close_others(self) -> None:
        if not self._active_component_id:
            return
        self._session_entries = [
            entry for entry in self._session_entries if entry.component_id == self._active_component_id
        ]
        self._save_session()
        self._render_session()
        self._mount_active()

    def _close_all(self) -> None:
        confirm = QtWidgets.QMessageBox.question(
            self,
            f"Close {terms.BLOCK} Session",
            "Close all blocks in this session?",
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.open_empty()

    def _remove_skipped(self) -> None:
        if not self._skipped_ids:
            return
        self._skipped_ids = []
        self._skipped_reasons = {}
        self._save_session()
        self._update_skipped_banner()

    def _on_session_selected(self) -> None:
        item = self.session_list.currentItem()
        if not item:
            self.activate_btn.setEnabled(False)
            return
        entry = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(entry, _SessionEntry):
            self.activate_btn.setEnabled(entry.openable)
        else:
            self.activate_btn.setEnabled(False)

    def _activate_selected(self) -> None:
        item = self.session_list.currentItem()
        if not item:
            return
        entry = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(entry, _SessionEntry):
            return
        if not entry.openable:
            self._show_banner(entry.reason)
            return
        self._set_active(entry.component_id)

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
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entry)
            widget = _SessionRow(entry)
            item.setSizeHint(widget.sizeHint())
            self.session_list.addItem(item)
            self.session_list.setItemWidget(item, widget)
            if entry.component_id == self._active_component_id:
                self.session_list.setCurrentItem(item)
        self._update_button_state()

    def _update_button_state(self) -> None:
        has_active = bool(self._active_component_id)
        self.close_active_btn.setEnabled(has_active)
        self.close_others_btn.setEnabled(has_active and len(self._session_entries) > 1)
        self.close_all_btn.setEnabled(bool(self._session_entries))
        current = self.session_list.currentItem()
        if current and isinstance(current.data(QtCore.Qt.ItemDataRole.UserRole), _SessionEntry):
            entry = current.data(QtCore.Qt.ItemDataRole.UserRole)
            self.activate_btn.setEnabled(entry.openable)
        else:
            self.activate_btn.setEnabled(False)

    def _mount_active(self) -> None:
        if self._active_component_id is None:
            self._show_empty_state()
            return
        if component_registry is None or self._host is None:
            self._show_banner("Block runtime unavailable.")
            return
        entry = self._find_entry(self._active_component_id)
        if entry and not entry.openable:
            self._show_banner(entry.reason)
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

    def _find_entry(self, component_id: str) -> Optional[_SessionEntry]:
        for entry in self._session_entries:
            if entry.component_id == component_id:
                return entry
        return None

    def _show_empty_state(self) -> None:
        if self._host is not None:
            self._host.unmount()
        self.empty_label.setVisible(True)

    def _show_banner(self, message: str) -> None:
        self.banner.setText(message)
        self.banner.setVisible(True)
        self.remove_skipped_btn.setVisible(False)

    def _update_skipped_banner(self) -> None:
        if not self._skipped_ids:
            self.banner.setVisible(False)
            self.remove_skipped_btn.setVisible(False)
            return
        count = len(self._skipped_ids)
        self.banner.setText(f"Skipped {count} block(s): disabled/unavailable.")
        self.banner.setVisible(True)
        self.remove_skipped_btn.setVisible(True)

    def _load_session(self) -> None:
        self._skipped_ids = []
        self._skipped_reasons = {}
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
        if not isinstance(data, dict):
            data = {}
        open_blocks = data.get("open_blocks")
        active_block = data.get("active_block")
        if not isinstance(open_blocks, list):
            open_blocks = []
        seen: set[str] = set()
        self._session_entries = []
        for component_id in open_blocks:
            if not isinstance(component_id, str):
                continue
            if component_id in seen:
                continue
            seen.add(component_id)
            entry = self._build_entry(component_id)
            if entry is None:
                self._skipped_ids.append(component_id)
                self._skipped_reasons[component_id] = "Unavailable"
                continue
            if not entry.openable:
                self._skipped_ids.append(component_id)
                self._skipped_reasons[component_id] = entry.reason
            self._session_entries.append(entry)
        self._active_component_id = active_block if isinstance(active_block, str) else None
        if self._active_component_id and not any(
            entry.component_id == self._active_component_id and entry.openable for entry in self._session_entries
        ):
            self._active_component_id = None
        if not self._active_component_id:
            for entry in self._session_entries:
                if entry.openable:
                    self._active_component_id = entry.component_id
                    break
        self._render_session()
        self._mount_active()
        self._update_skipped_banner()

    def _save_session(self) -> None:
        session_path = self._session_path()
        data = {
            "version": 1,
            "open_blocks": [entry.component_id for entry in self._session_entries],
            "active_block": self._active_component_id,
            "last_updated": datetime.utcnow().isoformat() + "Z",
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
        self._pack_name_map = {}
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
            display_name = manifest.get("display_name") or pack_id
            self._pack_name_map[pack_id] = display_name
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

    def _build_entry(self, component_id: str) -> Optional[_SessionEntry]:
        if not component_id:
            return None
        display_name = self._component_name_map.get(component_id) or _prettify_component_id(component_id)
        pack_id = self._component_pack_map.get(component_id)
        pack_name = self._pack_name_map.get(pack_id or "")
        if not pack_name:
            pack_name = "Built-in" if component_id.startswith("labhost:") else (pack_id or "Built-in")
        openable, status, reason = self._component_status(component_id)
        return _SessionEntry(
            component_id=component_id,
            display_name=display_name,
            pack_name=pack_name,
            status=status,
            reason=reason,
            openable=openable,
        )

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


def _prettify_component_id(component_id: str) -> str:
    if ":" in component_id:
        prefix, rest = component_id.split(":", 1)
        rest = rest.replace("_", " ").replace("-", " ")
        return f"{prefix.title()}: {rest.title()}"
    return component_id


def _status_label(entry: _SessionEntry) -> str:
    icon = "✅" if entry.status == "Enabled" else "⛔" if entry.status == "Disabled by project" else "⚠️"
    return f"{icon} {entry.status}"


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
