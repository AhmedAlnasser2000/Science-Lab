from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt6 import QtCore, QtWidgets

from app_ui.widgets.app_header import AppHeader
from app_ui.widgets.workspace_selector import WorkspaceSelector
from app_ui.ui_helpers import terms

try:
    from runtime_bus import topics as BUS_TOPICS
except Exception:  # pragma: no cover
    BUS_TOPICS = None

try:
    from app_ui.codesee.expectations import build_check
    from app_ui.codesee.runtime.events import SpanEnd, SpanStart, SpanUpdate
    from app_ui.codesee.runtime.hub import (
        publish_expect_check_global,
        publish_span_end_global,
        publish_span_start_global,
        publish_span_update_global,
    )
except Exception:  # pragma: no cover - defensive
    build_check = None
    publish_expect_check_global = None
    publish_span_start_global = None
    publish_span_update_global = None
    publish_span_end_global = None
    SpanStart = None
    SpanUpdate = None
    SpanEnd = None

BUS_WORKSPACE_GET_ACTIVE_REQUEST = (
    BUS_TOPICS.CORE_WORKSPACE_GET_ACTIVE_REQUEST
    if BUS_TOPICS
    else "core.workspace.get_active.request"
)
BUS_WORKSPACE_LIST_REQUEST = (
    BUS_TOPICS.CORE_WORKSPACE_LIST_REQUEST
    if BUS_TOPICS
    else "core.workspace.list.request"
)
BUS_WORKSPACE_SET_ACTIVE_REQUEST = (
    BUS_TOPICS.CORE_WORKSPACE_SET_ACTIVE_REQUEST
    if BUS_TOPICS
    else "core.workspace.set_active.request"
)
BUS_WORKSPACE_CREATE_REQUEST = (
    BUS_TOPICS.CORE_WORKSPACE_CREATE_REQUEST
    if BUS_TOPICS
    else "core.workspace.create.request"
)
BUS_WORKSPACE_DELETE_REQUEST = (
    BUS_TOPICS.CORE_WORKSPACE_DELETE_REQUEST
    if BUS_TOPICS
    else "core.workspace.delete.request"
)
BUS_WORKSPACE_TEMPLATES_LIST_REQUEST = (
    BUS_TOPICS.CORE_WORKSPACE_TEMPLATES_LIST_REQUEST
    if BUS_TOPICS
    else "core.workspace.templates.list.request"
)
BUS_INVENTORY_REQUEST = (
    BUS_TOPICS.CORE_INVENTORY_GET_REQUEST
    if BUS_TOPICS
    else "core.inventory.get.request"
)


def _workspace_prefs_root_from_paths(paths: Dict[str, Any]) -> Path:
    prefs = paths.get("prefs")
    if prefs:
        return Path(prefs)
    root = paths.get("root")
    base = Path(root) if root else Path("data/workspaces/default")
    return Path(base) / "prefs"


def _workspace_prefs_root_from_dir(workspace_dir: str | Path) -> Path:
    root = Path(workspace_dir)
    return root / "prefs"


def _workspace_config_path(prefs_root: Path) -> Path:
    return prefs_root / "workspace_config.json"


def _load_workspace_config_from_root(prefs_root: Path) -> Dict[str, Any]:
    path = _workspace_config_path(prefs_root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_workspace_config_to_root(prefs_root: Path, config: Dict[str, Any]) -> None:
    path = _workspace_config_path(prefs_root)
    try:
        prefs_root.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except Exception:
        pass


def _read_git_commit_hash() -> Optional[str]:
    root = Path(__file__).resolve().parent.parent.parent
    head_path = root / ".git" / "HEAD"
    if not head_path.exists():
        return None
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    if head.startswith("ref:"):
        ref = head.split(" ", 1)[1].strip()
        ref_path = root / ".git" / ref
        if not ref_path.exists():
            return None
        try:
            return ref_path.read_text(encoding="utf-8").strip()[:12]
        except Exception:
            return None
    return head[:12] if head else None


def _request_inventory_snapshot(bus) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not bus:
        return None, "runtime bus unavailable"
    try:
        response = bus.request(
            BUS_INVENTORY_REQUEST,
            {},
            source="app_ui",
            timeout_ms=1500,
        )
    except Exception as exc:
        return None, str(exc)
    if not response.get("ok"):
        return None, response.get("error") or "inventory_failed"
    return response.get("inventory") or {}, None


class WorkspaceManagementScreen(QtWidgets.QWidget):
    TEMPLATE_PREF_FILES = (
        "workspace_config.json",
        "lab_prefs.json",
        "policy_overrides.json",
        "pins.json",
    )

    def __init__(
        self,
        on_back,
        on_workspace_changed: Callable[[Dict[str, Any]], None],
        bus=None,
        *,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
        on_open_component_management: Optional[Callable[[], None]] = None,
        on_open_block_catalog: Optional[Callable[[], None]] = None,
        on_open_module_management: Optional[Callable[[], None]] = None,
        on_open_content_management: Optional[Callable[[], None]] = None,
        log_handler: Optional[
            Callable[[str, str, str, str, Dict[str, Any]], None]
        ] = None,
    ):
        super().__init__()
        self.on_back = on_back
        self.on_workspace_changed = on_workspace_changed
        self.bus = bus
        self._log_handler = log_handler
        self._open_component_management = on_open_component_management
        self._open_block_catalog = on_open_block_catalog
        self._open_module_management = on_open_module_management
        self._open_content_management = on_open_content_management
        self._templates: list[Dict[str, Any]] = []
        self._workspaces: list[Dict[str, Any]] = []

        layout = QtWidgets.QVBoxLayout(self)
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title=f"{terms.PROJECT} Management",
            on_back=self.on_back,
            workspace_selector=selector,
        )
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        header.add_action_widget(refresh_btn)
        if self._open_block_catalog:
            block_btn = QtWidgets.QPushButton(f"{terms.BLOCK} Catalog")
            block_btn.clicked.connect(self._open_block_catalog)
            header.add_action_widget(block_btn)
        layout.addWidget(header)

        self.active_label = QtWidgets.QLabel(f"Active {terms.PROJECT.lower()}: ?")
        self.active_label.setStyleSheet("color: #444;")
        layout.addWidget(self.active_label)

        self.table = QtWidgets.QTreeWidget()
        self.table.setColumnCount(5)
        self.table.setHeaderLabels(["Name", "ID", "Active", "Template", "Path"])
        header_view = self.table.header()
        header_view.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.table, stretch=1)

        btn_row = QtWidgets.QHBoxLayout()
        self.create_btn = QtWidgets.QPushButton(f"Create {terms.PROJECT}...")
        self.create_btn.clicked.connect(self._create_workspace)
        self.set_active_btn = QtWidgets.QPushButton(f"Set Active {terms.PROJECT}")
        self.set_active_btn.clicked.connect(self._set_active)
        self.delete_btn = QtWidgets.QPushButton(f"Delete {terms.PROJECT}")
        self.delete_btn.clicked.connect(self._delete_workspace)
        btn_row.addWidget(self.create_btn)
        btn_row.addWidget(self.set_active_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color: #555;")
        layout.addWidget(self.status)

        templates_box = QtWidgets.QGroupBox("Templates")
        templates_layout = QtWidgets.QVBoxLayout(templates_box)
        templates_row = QtWidgets.QHBoxLayout()
        templates_row.addWidget(QtWidgets.QLabel("Template"))
        self.template_combo = QtWidgets.QComboBox()
        templates_row.addWidget(self.template_combo, stretch=1)
        self.template_preview_btn = QtWidgets.QPushButton("Preview")
        self.template_preview_btn.clicked.connect(self._preview_template)
        self.template_diff_btn = QtWidgets.QPushButton("Diff")
        self.template_diff_btn.clicked.connect(self._diff_template)
        self.template_apply_btn = QtWidgets.QPushButton("Apply")
        self.template_apply_btn.clicked.connect(self._apply_template)
        templates_row.addWidget(self.template_preview_btn)
        templates_row.addWidget(self.template_diff_btn)
        templates_row.addWidget(self.template_apply_btn)
        templates_layout.addLayout(templates_row)
        self.template_status = QtWidgets.QLabel("")
        self.template_status.setStyleSheet("color: #555;")
        templates_layout.addWidget(self.template_status)
        layout.addWidget(templates_box)

        io_box = QtWidgets.QGroupBox("Export / Import")
        io_layout = QtWidgets.QVBoxLayout(io_box)
        io_row = QtWidgets.QHBoxLayout()
        self.export_btn = QtWidgets.QPushButton("Export Project...")
        self.export_btn.clicked.connect(self._export_workspace)
        self.import_btn = QtWidgets.QPushButton("Import Project...")
        self.import_btn.clicked.connect(self._import_workspace)
        io_row.addWidget(self.export_btn)
        io_row.addWidget(self.import_btn)
        io_row.addStretch()
        io_layout.addLayout(io_row)
        self.io_status = QtWidgets.QLabel("")
        self.io_status.setStyleSheet("color: #555;")
        io_layout.addWidget(self.io_status)
        layout.addWidget(io_box)

        packs_box = QtWidgets.QGroupBox(f"{terms.PACK}s")
        packs_layout = QtWidgets.QVBoxLayout(packs_box)
        self.pack_tree = QtWidgets.QTreeWidget()
        self.pack_tree.setColumnCount(2)
        self.pack_tree.setHeaderLabels(["Pack", "Version"])
        pack_header = self.pack_tree.header()
        pack_header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        pack_header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.pack_tree.itemChanged.connect(self._on_pack_item_changed)
        packs_layout.addWidget(self.pack_tree, stretch=1)
        self.pack_status = QtWidgets.QLabel("")
        self.pack_status.setStyleSheet("color: #555;")
        packs_layout.addWidget(self.pack_status)
        layout.addWidget(packs_box)
        self._pack_syncing = False
        self._pack_context: Dict[str, Any] = {}

        self.refresh()

    def refresh(self) -> None:
        self.table.clear()
        self._templates = self._load_templates()
        self._workspaces = self._load_workspaces()
        self._refresh_template_combo()
        active_id = None
        for ws in self._workspaces:
            active = bool(ws.get("active"))
            active_id = ws.get("id") if active else active_id
            item = QtWidgets.QTreeWidgetItem(
                [
                    ws.get("name") or ws.get("id") or "",
                    ws.get("id") or "",
                    "Yes" if active else "",
                    ws.get("template_id") or "",
                    ws.get("path") or "",
                ]
            )
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ws)
            self.table.addTopLevelItem(item)
        self.active_label.setText(f"Active {terms.PROJECT.lower()}: {active_id or 'unknown'}")
        self._update_buttons()
        self._refresh_pack_controls()

    def _load_templates(self) -> list[Dict[str, Any]]:
        if not self.bus:
            return []
        try:
            response = self.bus.request(
                BUS_WORKSPACE_TEMPLATES_LIST_REQUEST,
                {},
                source="app_ui",
                timeout_ms=1500,
            )
        except Exception:
            return []
        if not response.get("ok"):
            return []
        return response.get("templates") or []

    def _refresh_template_combo(self) -> None:
        active_id = None
        for ws in self._workspaces:
            if ws.get("active"):
                active_id = ws.get("template_id")
                break
        self.template_combo.clear()
        self.template_combo.addItem("Select template...", "")
        for tpl in self._templates:
            template_id = tpl.get("template_id") or tpl.get("id")
            if not template_id:
                continue
            label = tpl.get("name") or template_id
            self.template_combo.addItem(label, template_id)
        if active_id:
            idx = self.template_combo.findData(active_id)
            if idx >= 0:
                self.template_combo.setCurrentIndex(idx)

    def _load_workspaces(self) -> list[Dict[str, Any]]:
        if not self.bus:
            self.status.setText("Runtime bus unavailable.")
            return []
        try:
            response = self.bus.request(
                BUS_WORKSPACE_LIST_REQUEST,
                {},
                source="app_ui",
                timeout_ms=2000,
            )
        except Exception as exc:
            self.status.setText(f"Project list failed: {exc}")
            return []
        if not response.get("ok"):
            self.status.setText(f"Project list failed: {response.get('error') or 'unknown'}")
            return []
        return response.get("workspaces") or []

    def _selected_workspace(self) -> Optional[Dict[str, Any]]:
        item = self.table.currentItem()
        if not item:
            return None
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _update_buttons(self) -> None:
        ws = self._selected_workspace()
        has_ws = ws is not None
        active = bool(ws.get("active")) if ws else False
        self.set_active_btn.setEnabled(bool(self.bus and has_ws and not active))
        self.delete_btn.setEnabled(bool(self.bus and has_ws and not active))
        self.create_btn.setEnabled(bool(self.bus))
        if hasattr(self, "export_btn"):
            self.export_btn.setEnabled(bool(self.bus and (has_ws or self._active_workspace())))
        if hasattr(self, "import_btn"):
            self.import_btn.setEnabled(bool(self.bus))
        self._refresh_pack_controls()

    def _refresh_pack_controls(self) -> None:
        if not hasattr(self, "pack_tree"):
            return
        self._pack_syncing = True
        self.pack_tree.clear()
        self.pack_tree.setEnabled(False)
        self.pack_status.setText("Select a project to edit packs.")
        self._pack_context = {}
        ws = self._selected_workspace() or self._active_workspace()
        if not ws:
            self._pack_syncing = False
            return
        prefs_root = self._prefs_root(ws)
        if prefs_root is None:
            self.pack_status.setText("Project prefs unavailable.")
            self._pack_syncing = False
            return
        inventory, error = _request_inventory_snapshot(self.bus)
        if inventory is None:
            self.pack_status.setText(error or "Inventory unavailable.")
            self._pack_syncing = False
            return
        packs = inventory.get("component_packs") or []
        available_ids = {
            str(pack.get("id") or "").strip()
            for pack in packs
            if pack.get("id")
        }
        if not packs:
            self.pack_status.setText("No installed packs.")
            self._pack_syncing = False
            return
        config = self._load_workspace_config(ws)
        enabled_set = self._resolve_workspace_enabled_packs_from_config(config, available_ids)
        for pack in packs:
            pack_id = str(pack.get("id") or "").strip()
            if not pack_id:
                continue
            label = pack.get("name") or pack_id
            version = pack.get("version") or ""
            item = QtWidgets.QTreeWidgetItem([f"{label} ({pack_id})", version])
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            state = (
                QtCore.Qt.CheckState.Checked
                if pack_id in enabled_set
                else QtCore.Qt.CheckState.Unchecked
            )
            item.setCheckState(0, state)
            item.setData(
                0,
                QtCore.Qt.ItemDataRole.UserRole,
                {"workspace_id": ws.get("id"), "pack_id": pack_id},
            )
            self.pack_tree.addTopLevelItem(item)
        self.pack_tree.setEnabled(True)
        self.pack_status.setText(
            f"Project '{ws.get('id') or '?'}': {len(enabled_set)}/{len(available_ids)} packs enabled."
        )
        self._pack_context = {
            "workspace": ws,
            "available_ids": available_ids,
            "prefs_root": prefs_root,
        }
        self._pack_syncing = False

    def _resolve_workspace_enabled_packs_from_config(
        self, config: Dict[str, Any], available_ids: set[str]
    ) -> set[str]:
        value = config.get("enabled_component_packs")
        if isinstance(value, list):
            return {str(entry) for entry in value if str(entry) in available_ids}
        return set(available_ids)

    def _load_workspace_config(self, workspace: Dict[str, Any]) -> Dict[str, Any]:
        prefs_root = self._prefs_root(workspace)
        if prefs_root is None:
            return {}
        return _load_workspace_config_from_root(prefs_root)

    def _save_workspace_config(self, workspace: Dict[str, Any], config: Dict[str, Any]) -> None:
        prefs_root = self._prefs_root(workspace)
        if prefs_root is None:
            return
        _save_workspace_config_to_root(prefs_root, config)

    def _update_workspace_pack_setting(
        self,
        workspace: Dict[str, Any],
        prefs_root: Path,
        pack_id: str,
        enabled: bool,
        available_ids: set[str],
    ) -> None:
        config = _load_workspace_config_from_root(prefs_root)
        enabled_set = self._resolve_workspace_enabled_packs_from_config(config, available_ids)
        changed = False
        if enabled:
            if pack_id not in enabled_set:
                enabled_set.add(pack_id)
                changed = True
        else:
            if pack_id in enabled_set:
                enabled_set.discard(pack_id)
                changed = True
        if not changed:
            return
        if len(enabled_set) == len(available_ids):
            config.pop("enabled_component_packs", None)
        else:
            config["enabled_component_packs"] = sorted(enabled_set)
        _save_workspace_config_to_root(prefs_root, config)
        if self._log_handler:
            self._log_handler(
                "workspace",
                "H_WS_TOGGLE",
                "app_ui/screens/workspace_management.py:WorkspaceManagementScreen._update_workspace_pack_setting",
                "pack_toggle",
                {
                    "workspace_id": workspace.get("id"),
                    "pack_id": pack_id,
                    "enabled": enabled,
                    "enabled_count": len(enabled_set),
                    "total": len(available_ids),
                },
            )
        if workspace.get("active"):
            active_info = self._fetch_active_workspace_info()
            if active_info:
                self.on_workspace_changed(active_info)
        self._refresh_pack_controls()

    def _fetch_active_workspace_info(self) -> Optional[Dict[str, Any]]:
        if not self.bus:
            return None
        try:
            response = self.bus.request(
                BUS_WORKSPACE_GET_ACTIVE_REQUEST,
                {},
                source="app_ui",
                timeout_ms=1500,
            )
        except Exception:
            return None
        if response.get("ok"):
            workspace = response.get("workspace")
            if isinstance(workspace, dict):
                return workspace
        return None

    def _on_pack_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        if self._pack_syncing:
            return
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
        pack_id = data.get("pack_id")
        context = self._pack_context or {}
        workspace = context.get("workspace")
        prefs_root = context.get("prefs_root")
        available_ids = context.get("available_ids") or set()
        workspace_id = data.get("workspace_id")
        if (
            not pack_id
            or not workspace
            or prefs_root is None
            or (workspace_id and workspace_id != workspace.get("id"))
        ):
            return
        enabled = item.checkState(0) == QtCore.Qt.CheckState.Checked
        self._update_workspace_pack_setting(
            workspace,
            prefs_root,
            pack_id,
            enabled,
            set(available_ids),
        )

    def _create_workspace(self) -> None:
        if not self.bus:
            self.status.setText("Runtime bus unavailable.")
            return
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Create Project")
        form = QtWidgets.QFormLayout(dialog)
        name_edit = QtWidgets.QLineEdit()
        id_edit = QtWidgets.QLineEdit()
        template_combo = QtWidgets.QComboBox()
        template_combo.addItem("None", "")
        for tpl in self._templates:
            template_id = tpl.get("template_id") or tpl.get("id")
            label = tpl.get("name") or template_id
            template_combo.addItem(label, template_id)
        form.addRow("Name", name_edit)
        form.addRow("ID (slug)", id_edit)
        form.addRow("Template", template_combo)
        btn_row = QtWidgets.QHBoxLayout()
        ok_btn = QtWidgets.QPushButton("Create")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        form.addRow(btn_row)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        name = name_edit.text().strip()
        workspace_id = id_edit.text().strip() or self._slugify(name or "workspace")
        template_id = template_combo.currentData()
        payload = {"workspace_id": workspace_id}
        if name:
            payload["name"] = name
        if template_id:
            payload["template_id"] = template_id
        try:
            response = self.bus.request(
                BUS_WORKSPACE_CREATE_REQUEST,
                payload,
                source="app_ui",
                timeout_ms=2000,
            )
        except Exception as exc:
            self.status.setText(f"Create failed: {exc}")
            return
        if not response.get("ok"):
            self.status.setText(f"Create failed: {response.get('error') or 'unknown'}")
            return
        self.status.setText(f"Created project {workspace_id}.")
        self.refresh()

    def _set_active(self) -> None:
        ws = self._selected_workspace()
        if not (self.bus and ws):
            return
        workspace_id = ws.get("id")
        try:
            response = self.bus.request(
                BUS_WORKSPACE_SET_ACTIVE_REQUEST,
                {"workspace_id": workspace_id},
                source="app_ui",
                timeout_ms=1500,
            )
        except Exception as exc:
            self.status.setText(f"Set active failed: {exc}")
            return
        if not response.get("ok"):
            self.status.setText(f"Set active failed: {response.get('error') or 'unknown'}")
            return
        workspace = response.get("workspace")
        if isinstance(workspace, dict):
            self.on_workspace_changed(workspace)
        self.status.setText(f"Active project: {workspace_id}")
        self.refresh()

    def _delete_workspace(self) -> None:
        ws = self._selected_workspace()
        if not (self.bus and ws):
            return
        if ws.get("active"):
            self.status.setText("Cannot delete the active project.")
            return
        workspace_id = ws.get("id")
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete project",
            f"Delete project '{workspace_id}'? This removes its runs and prefs.",
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            response = self.bus.request(
                BUS_WORKSPACE_DELETE_REQUEST,
                {"workspace_id": workspace_id},
                source="app_ui",
                timeout_ms=3000,
            )
        except Exception as exc:
            self.status.setText(f"Delete failed: {exc}")
            return
        if not response.get("ok"):
            self.status.setText(f"Delete failed: {response.get('error') or 'unknown'}")
            return
        self.status.setText(f"Deleted project {workspace_id}.")
        self.refresh()

    def _slugify(self, value: str) -> str:
        clean = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
        return clean or "workspace"

    def _active_workspace(self) -> Optional[Dict[str, Any]]:
        for ws in self._workspaces:
            if ws.get("active"):
                return ws
        return None

    def _template_info(self, template_id: str) -> Optional[Dict[str, Any]]:
        for tpl in self._templates:
            candidate = tpl.get("template_id") or tpl.get("id")
            if candidate == template_id:
                return tpl
        return None

    def _prefs_root(self, workspace: Dict[str, Any]) -> Optional[Path]:
        path = workspace.get("path")
        if not isinstance(path, str) or not path:
            return None
        return Path(path) / "prefs"

    def _template_root(self, template_id: str) -> Optional[Path]:
        info = self._template_info(template_id)
        if not info:
            return None
        path = info.get("path")
        if not isinstance(path, str) or not path:
            return None
        return Path(path)

    def _load_json(self, path: Path) -> Dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _format_value(self, value: Any) -> str:
        if isinstance(value, dict):
            return f"{{{', '.join(list(value.keys())[:4])}}}"
        if isinstance(value, list):
            return f"[list:{len(value)}]"
        return repr(value)

    def _diff_dicts(
        self,
        current: Dict[str, Any],
        incoming: Dict[str, Any],
        prefix: str,
        added: List[str],
        removed: List[str],
        changed: List[str],
    ) -> None:
        current_keys = set(current.keys())
        incoming_keys = set(incoming.keys())
        for key in sorted(incoming_keys - current_keys):
            path = f"{prefix}{key}"
            added.append(f"+ {path} = {self._format_value(incoming.get(key))}")
        for key in sorted(current_keys - incoming_keys):
            path = f"{prefix}{key}"
            removed.append(f"- {path} = {self._format_value(current.get(key))}")
        for key in sorted(current_keys & incoming_keys):
            path = f"{prefix}{key}"
            cur_val = current.get(key)
            new_val = incoming.get(key)
            if isinstance(cur_val, dict) and isinstance(new_val, dict):
                self._diff_dicts(cur_val, new_val, f"{path}.", added, removed, changed)
                continue
            if cur_val != new_val:
                changed.append(
                    f"* {path}: {self._format_value(cur_val)} -> {self._format_value(new_val)}"
                )

    def _summarize_template(self, template_root: Path) -> str:
        lines = []
        for name in self.TEMPLATE_PREF_FILES:
            path = template_root / name
            if not path.exists():
                continue
            data = self._load_json(path)
            keys = list(data.keys())
            key_list = ", ".join(keys[:6])
            suffix = "..." if len(keys) > 6 else ""
            lines.append(f"- {name}: keys [{key_list}{suffix}]")
        if not lines:
            return "No preference files found in this template."
        return "\n".join(lines)

    def _preview_template(self) -> None:
        template_id = self.template_combo.currentData()
        if not template_id:
            self.template_status.setText("Select a template to preview.")
            return
        root = self._template_root(str(template_id))
        if not root or not root.exists():
            self.template_status.setText("Template path not found.")
            return
        info = self._template_info(str(template_id)) or {}
        header = f"Template: {info.get('name') or template_id} ({template_id})"
        summary = self._summarize_template(root)
        self._show_text_dialog("Template Preview", f"{header}\n\n{summary}")

    def _diff_template(self) -> None:
        template_id = self.template_combo.currentData()
        if not template_id:
            self.template_status.setText("Select a template to diff.")
            return
        workspace = self._active_workspace()
        if not workspace:
            self.template_status.setText("No active project selected.")
            return
        prefs_root = self._prefs_root(workspace)
        template_root = self._template_root(str(template_id))
        if not prefs_root or not template_root:
            self.template_status.setText("Template or project prefs path missing.")
            return
        blocks: List[str] = []
        for name in self.TEMPLATE_PREF_FILES:
            template_path = template_root / name
            if not template_path.exists():
                continue
            current_path = prefs_root / name
            current = self._load_json(current_path) if current_path.exists() else {}
            incoming = self._load_json(template_path)
            added: List[str] = []
            removed: List[str] = []
            changed: List[str] = []
            self._diff_dicts(current, incoming, "", added, removed, changed)
            if not (added or removed or changed):
                blocks.append(f"{name}: no differences")
                continue
            blocks.append(f"{name}:")
            blocks.extend(added or [])
            blocks.extend(removed or [])
            blocks.extend(changed or [])
        if not blocks:
            blocks.append("No template files found.")
        self._show_text_dialog("Template Diff", "\n".join(blocks))

    def _merge_dicts(self, base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_dicts(merged.get(key) or {}, value)
            else:
                merged[key] = value
        return merged

    def _apply_template(self) -> None:
        template_id = self.template_combo.currentData()
        if not template_id:
            self.template_status.setText("Select a template to apply.")
            return
        workspace = self._active_workspace()
        if not workspace:
            self.template_status.setText("No active project selected.")
            return
        prefs_root = self._prefs_root(workspace)
        template_root = self._template_root(str(template_id))
        if not prefs_root or not template_root:
            self.template_status.setText("Template or project prefs path missing.")
            return
        prefs_root.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_root = prefs_root / "_backup" / timestamp
        backup_root.mkdir(parents=True, exist_ok=True)
        changed_files = []
        for name in self.TEMPLATE_PREF_FILES:
            template_path = template_root / name
            if not template_path.exists():
                continue
            current_path = prefs_root / name
            current = self._load_json(current_path) if current_path.exists() else {}
            incoming = self._load_json(template_path)
            merged = self._merge_dicts(current, incoming)
            if merged == current:
                continue
            if current_path.exists():
                try:
                    backup_root.joinpath(name).write_text(
                        current_path.read_text(encoding="utf-8"),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
            try:
                current_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
                changed_files.append(name)
            except Exception:
                continue
        if not changed_files:
            self.template_status.setText("Template applied; no changes were required.")
        else:
            self.template_status.setText(f"Applied template to: {', '.join(changed_files)}")
        self.refresh()

    def _export_workspace(self) -> None:
        ws = self._selected_workspace() or self._active_workspace()
        if not ws:
            self.io_status.setText("No project selected.")
            return
        prefs_root = self._prefs_root(ws)
        if not prefs_root:
            self.io_status.setText("Project prefs unavailable.")
            return
        export_info = self._prompt_export_settings(ws)
        if not export_info:
            return
        target, include_files = export_info
        expected_files = 1 + len(include_files)
        written_files = 0
        span_id = None
        if callable(publish_span_start_global) and SpanStart:
            span_id = f"content.export.{ws.get('id')}.{int(time.time() * 1000)}"
            publish_span_start_global(
                SpanStart(
                    span_id=span_id,
                    label="Export project",
                    node_id="system:content_system",
                    source_id="system:content_system",
                    severity=None,
                    ts=time.time(),
                )
            )

        def _emit_export_check(status: str, message: str, error: Optional[str] = None) -> None:
            if not callable(build_check) or not callable(publish_expect_check_global):
                return
            expected = {"status": "ok", "files": expected_files}
            actual = {"status": status, "files": written_files}
            if error:
                actual["error"] = error
            check = build_check(
                check_id="content.export.summary",
                node_id="system:content_system",
                expected=expected,
                actual=actual,
                mode="exact",
                message=message,
                context={
                    "action": "export",
                    "workspace_id": ws.get("id"),
                    "target": Path(target).name,
                    "included_files": list(include_files),
                },
            )
            publish_expect_check_global(check)
        config = _load_workspace_config_from_root(prefs_root)
        enabled_packs = config.get("enabled_component_packs")
        inventory, _ = _request_inventory_snapshot(self.bus)
        installed_modules = []
        installed_packs = []
        if isinstance(inventory, dict):
            installed_modules = [
                str(item.get("id"))
                for item in inventory.get("modules") or []
                if item.get("id")
            ]
            installed_packs = [
                str(item.get("id"))
                for item in inventory.get("component_packs") or []
                if item.get("id")
            ]
        if not isinstance(enabled_packs, list):
            enabled_packs = installed_packs
        manifest = {
            "format_version": 1,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "workspace": {
                "id": ws.get("id"),
                "name": ws.get("name") or ws.get("id"),
                "template_id": ws.get("template_id"),
            },
            "requirements": {
                "enabled_component_packs": enabled_packs,
                "installed_modules": installed_modules,
            },
            "included_files": include_files,
        }
        commit = _read_git_commit_hash()
        if commit:
            manifest["app_commit"] = commit
        try:
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
                written_files += 1
                for name in include_files:
                    path = prefs_root / name
                    if path.exists():
                        payload = path.read_text(encoding="utf-8")
                    else:
                        payload = "{}"
                    zf.writestr(f"prefs/{name}", payload)
                    written_files += 1
        except Exception as exc:
            self.io_status.setText(f"Export failed: {exc}")
            _emit_export_check("failed", "Export failed.", str(exc))
            if span_id and callable(publish_span_end_global) and SpanEnd:
                publish_span_end_global(
                    SpanEnd(
                        span_id=span_id,
                        status="failed",
                        ts=time.time(),
                        message=f"Export failed: {exc}",
                    )
                )
            return
        self.io_status.setText(f"Exported project to {target}")
        _emit_export_check("ok", f"Export wrote {written_files}/{expected_files} file(s).")
        if span_id and callable(publish_span_update_global) and SpanUpdate:
            progress = written_files / expected_files if expected_files else 1.0
            publish_span_update_global(
                SpanUpdate(
                    span_id=span_id,
                    progress=progress,
                    message=f"Export wrote {written_files}/{expected_files} file(s)",
                    ts=time.time(),
                )
            )
        if span_id and callable(publish_span_end_global) and SpanEnd:
            publish_span_end_global(
                SpanEnd(
                    span_id=span_id,
                    status="completed",
                    ts=time.time(),
                    message=f"Export complete: {written_files}/{expected_files} file(s)",
                )
            )

    def _prompt_export_settings(self, workspace: Dict[str, Any]) -> Optional[tuple[str, list[str]]]:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Export Project")
        layout = QtWidgets.QVBoxLayout(dialog)
        form = QtWidgets.QFormLayout()
        path_row = QtWidgets.QHBoxLayout()
        path_edit = QtWidgets.QLineEdit()
        path_edit.setText(f"{workspace.get('id') or 'project'}.zip")
        browse_btn = QtWidgets.QPushButton("Browse...")

        def _browse() -> None:
            target, _ = QtWidgets.QFileDialog.getSaveFileName(
                dialog,
                "Export project",
                path_edit.text(),
                "Project Zip (*.zip)",
            )
            if target:
                path_edit.setText(target)

        browse_btn.clicked.connect(_browse)
        path_row.addWidget(path_edit, stretch=1)
        path_row.addWidget(browse_btn)
        form.addRow("Destination", path_row)
        layout.addLayout(form)

        include_box = QtWidgets.QGroupBox("Include preference files")
        include_layout = QtWidgets.QVBoxLayout(include_box)
        checkboxes: Dict[str, QtWidgets.QCheckBox] = {}
        labels = {
            "workspace_config.json": "workspace_config.json",
            "lab_prefs.json": "lab_prefs.json",
            "policy_overrides.json": "policy_overrides.json",
            "pins.json": "pins.json",
        }
        for name in self.TEMPLATE_PREF_FILES:
            cb = QtWidgets.QCheckBox(labels.get(name, name))
            cb.setChecked(True)
            include_layout.addWidget(cb)
            checkboxes[name] = cb
        layout.addWidget(include_box)

        btn_row = QtWidgets.QHBoxLayout()
        ok_btn = QtWidgets.QPushButton("Export")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        target = path_edit.text().strip()
        if not target:
            return None
        include_files = [name for name, cb in checkboxes.items() if cb.isChecked()]
        if not include_files:
            include_files = []
        return target, include_files

    def _import_workspace(self) -> None:
        if not self.bus:
            self.io_status.setText("Runtime bus unavailable.")
            return
        source, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Import project",
            "",
            "Project Zip (*.zip)",
        )
        if not source:
            return
        expected_files = 0
        imported_files = 0
        workspace_info: Dict[str, Any] = {}
        span_id = None
        if callable(publish_span_start_global) and SpanStart:
            span_id = f"content.import.{int(time.time() * 1000)}"
            publish_span_start_global(
                SpanStart(
                    span_id=span_id,
                    label="Import project",
                    node_id="system:content_system",
                    source_id="system:content_system",
                    severity=None,
                    ts=time.time(),
                )
            )

        def _emit_import_check(status: str, message: str, error: Optional[str] = None) -> None:
            if not callable(build_check) or not callable(publish_expect_check_global):
                return
            expected = {"status": "ok", "files": expected_files}
            actual = {"status": status, "files": imported_files}
            if error:
                actual["error"] = error
            check = build_check(
                check_id="content.import.summary",
                node_id="system:content_system",
                expected=expected,
                actual=actual,
                mode="exact",
                message=message,
                context={
                    "action": "import",
                    "workspace_id": workspace_info.get("id"),
                    "source": Path(source).name,
                },
            )
            publish_expect_check_global(check)
        try:
            with zipfile.ZipFile(source, "r") as zf:
                if "manifest.json" not in zf.namelist():
                    self.io_status.setText("Import failed: manifest.json missing.")
                    _emit_import_check("failed", "Import failed: manifest.json missing.")
                    if span_id and callable(publish_span_end_global) and SpanEnd:
                        publish_span_end_global(
                            SpanEnd(
                                span_id=span_id,
                                status="failed",
                                ts=time.time(),
                                message="Import failed: manifest.json missing.",
                            )
                        )
                    return
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                fmt = manifest.get("format_version")
                if fmt not in (1, "1"):
                    self.io_status.setText("Import failed: unsupported format_version.")
                    _emit_import_check("failed", "Import failed: unsupported format_version.")
                    if span_id and callable(publish_span_end_global) and SpanEnd:
                        publish_span_end_global(
                            SpanEnd(
                                span_id=span_id,
                                status="failed",
                                ts=time.time(),
                                message="Import failed: unsupported format_version.",
                            )
                        )
                    return
                expected_entries = manifest.get("included_files") or list(self.TEMPLATE_PREF_FILES)
                expected_files = len(expected_entries)
                pref_entries = [
                    name for name in expected_entries if f"prefs/{name}" in zf.namelist()
                ]
                missing = [
                    name
                    for name in expected_entries
                    if f"prefs/{name}" not in zf.namelist()
                ]
                if missing:
                    self.io_status.setText(
                        "Import failed: prefs files missing (" + ", ".join(missing) + ")."
                    )
                    imported_files = len(pref_entries)
                    _emit_import_check(
                        "failed",
                        "Import failed: preference files missing.",
                        "missing: " + ", ".join(missing),
                    )
                    if span_id and callable(publish_span_end_global) and SpanEnd:
                        publish_span_end_global(
                            SpanEnd(
                                span_id=span_id,
                                status="failed",
                                ts=time.time(),
                                message="Import failed: preference files missing.",
                            )
                        )
                    return
                workspace_info = manifest.get("workspace") or {}
                base_id = self._slugify(str(workspace_info.get("id") or "imported"))
                existing_ids = {ws.get("id") for ws in self._workspaces if ws.get("id")}
                workspace_id = base_id
                suffix = 1
                while workspace_id in existing_ids:
                    workspace_id = f"{base_id}_{suffix}"
                    suffix += 1
                payload = {"workspace_id": workspace_id}
                if workspace_info.get("name"):
                    payload["name"] = workspace_info.get("name")
                response = self.bus.request(
                    BUS_WORKSPACE_CREATE_REQUEST,
                    payload,
                    source="app_ui",
                    timeout_ms=2000,
                )
                if not response.get("ok"):
                    self.io_status.setText(
                        f"Import failed: {response.get('error') or 'create_failed'}"
                    )
                    if span_id and callable(publish_span_end_global) and SpanEnd:
                        publish_span_end_global(
                            SpanEnd(
                                span_id=span_id,
                                status="failed",
                                ts=time.time(),
                                message=f"Import failed: {response.get('error') or 'create_failed'}",
                            )
                        )
                    return
                workspace = response.get("workspace") or {}
                prefs_root = _workspace_prefs_root_from_paths(workspace.get("paths") or {})
                prefs_root.mkdir(parents=True, exist_ok=True)
                for name in pref_entries:
                    data = zf.read(f"prefs/{name}")
                    (prefs_root / name).write_text(data.decode("utf-8"), encoding="utf-8")
                    imported_files += 1
        except Exception as exc:
            self.io_status.setText(f"Import failed: {exc}")
            _emit_import_check("failed", "Import failed.", str(exc))
            if span_id and callable(publish_span_end_global) and SpanEnd:
                publish_span_end_global(
                    SpanEnd(
                        span_id=span_id,
                        status="failed",
                        ts=time.time(),
                        message=f"Import failed: {exc}",
                    )
                )
            return
        self.io_status.setText(f"Imported project as {workspace_id}")
        _emit_import_check(
            "ok",
            f"Import applied {imported_files}/{expected_files} file(s).",
        )
        if span_id and callable(publish_span_update_global) and SpanUpdate:
            progress = imported_files / expected_files if expected_files else 1.0
            publish_span_update_global(
                SpanUpdate(
                    span_id=span_id,
                    progress=progress,
                    message=f"Import applied {imported_files}/{expected_files} file(s)",
                    ts=time.time(),
                )
            )
        if span_id and callable(publish_span_end_global) and SpanEnd:
            publish_span_end_global(
                SpanEnd(
                    span_id=span_id,
                    status="completed",
                    ts=time.time(),
                    message=f"Import complete: {imported_files}/{expected_files} file(s)",
                )
            )
        self.refresh()
        missing = self._summarize_missing_requirements(manifest)
        self._show_import_summary(workspace_id, workspace_info, pref_entries, manifest, missing)

    def _summarize_missing_requirements(self, manifest: Dict[str, Any]) -> Dict[str, List[str]]:
        inventory, _ = _request_inventory_snapshot(self.bus)
        requirements = manifest.get("requirements") or {}
        required_packs = requirements.get("enabled_component_packs") or []
        required_modules = requirements.get("installed_modules") or []
        installed_packs = set()
        installed_modules = set()
        if isinstance(inventory, dict):
            installed_packs = {
                str(item.get("id"))
                for item in inventory.get("component_packs") or []
                if item.get("id")
            }
            installed_modules = {
                str(item.get("id"))
                for item in inventory.get("modules") or []
                if item.get("id")
            }
        missing_packs: List[str] = []
        missing_modules: List[str] = []
        for pack_id in required_packs:
            if str(pack_id) not in installed_packs:
                missing_packs.append(str(pack_id))
        for module_id in required_modules:
            if str(module_id) not in installed_modules:
                missing_modules.append(str(module_id))
        return {"packs": missing_packs, "modules": missing_modules}

    def _show_import_summary(
        self,
        workspace_id: str,
        workspace_info: Dict[str, Any],
        applied_files: List[str],
        manifest: Dict[str, Any],
        missing: Dict[str, List[str]],
    ) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Project import summary")
        dialog.resize(560, 420)
        layout = QtWidgets.QVBoxLayout(dialog)
        title = QtWidgets.QLabel(f"Imported project: {workspace_id}")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)
        details = QtWidgets.QPlainTextEdit()
        details.setReadOnly(True)
        name = workspace_info.get("name") or workspace_id
        template_id = workspace_info.get("template_id") or "none"
        prefs_list = ", ".join(applied_files) if applied_files else "(none)"
        requirements = manifest.get("requirements") or {}
        packs = requirements.get("enabled_component_packs") or []
        modules = requirements.get("installed_modules") or []
        lines = [
            f"Name: {name}",
            f"Template: {template_id}",
            f"Prefs applied: {prefs_list}",
            "",
            "Requirements:",
            f"Packs: {', '.join(packs) if packs else '(none)'}",
            f"Topics: {', '.join(modules) if modules else '(none)'}",
        ]
        missing_packs = missing.get("packs") or []
        missing_modules = missing.get("modules") or []
        if missing_packs or missing_modules:
            lines.append("")
            lines.append("Missing requirements:")
            if missing_packs:
                lines.append(f"- Packs: {', '.join(missing_packs)}")
            if missing_modules:
                lines.append(f"- Topics: {', '.join(missing_modules)}")
        details.setPlainText("\n".join(lines))
        layout.addWidget(details, stretch=1)

        action_row = QtWidgets.QHBoxLayout()
        action_row.addStretch()
        pack_btn = QtWidgets.QPushButton("Open Pack Management")
        pack_btn.setEnabled(bool(self._open_component_management and missing_packs))
        pack_btn.clicked.connect(lambda: self._open_component_management())
        module_btn = QtWidgets.QPushButton("Open Topic Management")
        module_btn.setEnabled(bool(self._open_module_management and missing_modules))
        module_btn.clicked.connect(lambda: self._open_module_management())
        content_btn = QtWidgets.QPushButton("Open Content Management")
        content_btn.setEnabled(bool(self._open_content_management and missing_modules))
        content_btn.clicked.connect(lambda: self._open_content_management())
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        action_row.addWidget(pack_btn)
        action_row.addWidget(module_btn)
        action_row.addWidget(content_btn)
        action_row.addWidget(close_btn)
        layout.addLayout(action_row)
        dialog.exec()

    def _show_text_dialog(self, title: str, text: str) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(640, 420)
        layout = QtWidgets.QVBoxLayout(dialog)
        view = QtWidgets.QTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        layout.addWidget(view, stretch=1)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec()


__all__ = [
    "WorkspaceManagementScreen",
    "_request_inventory_snapshot",
    "_workspace_prefs_root_from_paths",
    "_workspace_prefs_root_from_dir",
    "_load_workspace_config_from_root",
    "_save_workspace_config_to_root",
]
