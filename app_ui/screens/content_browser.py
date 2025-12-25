from typing import Any, Callable, Dict, List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app_ui.ui_helpers.assets import read_asset_text
from app_ui.ui_helpers.component_policy import (
    WorkspaceComponentPolicy,
    _get_global_component_policy,
)
from app_ui.ui_helpers.install_worker import InstallWorker
from app_ui.ui_helpers.statuses import (
    STATUS_READY,
    STATUS_NOT_INSTALLED,
    STATUS_UNAVAILABLE,
    WORKSPACE_DISABLED_REASON,
)
from app_ui.widgets.app_header import AppHeader
from app_ui.widgets.workspace_selector import WorkspaceSelector


class ContentBrowserScreen(QtWidgets.QWidget):
    # --- [NAV-31A] ctor / dependencies
    def __init__(
        self,
        adapter: "ContentSystemAdapter",
        on_back,
        get_profile,
        open_lab,
        open_component,
        *,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
        component_policy_provider: Optional[Callable[[], "WorkspaceComponentPolicy"]] = None,
        log_handler: Optional[Callable[..., None]] = None,
    ):
        super().__init__()
        self.adapter = adapter
        self.on_back = on_back
        self.get_profile = get_profile
        self.open_lab = open_lab
        self.open_component = open_component
        self.current_part_id: Optional[str] = None
        self.current_part_info: Optional[Dict] = None
        self.current_part_detail: Optional[Dict] = None
        self.component_policy_provider = component_policy_provider
        self.log_handler = log_handler

        layout = QtWidgets.QVBoxLayout(self)
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title="Physics Content Browser",
            on_back=self.on_back,
            workspace_selector=selector,
        )
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_tree)
        header.add_action_widget(refresh_btn)
        layout.addWidget(header)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter, stretch=1)
        self._splitter_initialized = False

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Item", "Status"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnCount(2)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setMinimumWidth(360)
        self.tree.itemSelectionChanged.connect(self._on_selection)
        self.splitter.addWidget(self.tree)

        detail_widget = QtWidgets.QWidget()
        detail_layout = QtWidgets.QVBoxLayout(detail_widget)
        self.detail_title = QtWidgets.QLabel("Select a part to view details.")
        self.detail_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.detail_status = QtWidgets.QLabel("")
        self.detail_reason = QtWidgets.QLabel("")
        self.detail_reason.setStyleSheet("color: #555;")
        self.debug_label = QtWidgets.QLabel("")
        self.debug_label.setStyleSheet("color: #999;")
        self.debug_label.setVisible(False)

        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_status)
        detail_layout.addWidget(self.detail_reason)
        detail_layout.addWidget(self.debug_label)

        button_row = QtWidgets.QHBoxLayout()
        self.install_button = QtWidgets.QPushButton("Install")
        self.install_button.clicked.connect(self._install_selected)
        self.open_button = QtWidgets.QPushButton("Open")
        self.open_button.clicked.connect(self._open_selected)
        self.install_button.setEnabled(False)
        self.open_button.setEnabled(False)
        button_row.addWidget(self.install_button)
        button_row.addWidget(self.open_button)
        button_row.addStretch()
        detail_layout.addLayout(button_row)

        self.viewer = QtWidgets.QPlainTextEdit()
        self.viewer.setReadOnly(True)
        self.viewer.setPlaceholderText("Open a part to preview markdown content.")
        detail_layout.addWidget(self.viewer, stretch=1)

        self.splitter.addWidget(detail_widget)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 5)

        self.progress_dialog: Optional[QtWidgets.QProgressDialog] = None
        self.install_thread: Optional[QtCore.QThread] = None
        self.refresh_tree()

    def _component_policy(self) -> Optional[WorkspaceComponentPolicy]:
        if self.component_policy_provider:
            try:
                return self.component_policy_provider()
            except Exception:
                return None
        return _get_global_component_policy()

    def _is_component_enabled(self, component_id: Optional[str]) -> bool:
        policy = self._component_policy()
        if policy is None:
            return True
        return policy.is_component_enabled(component_id)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if self._splitter_initialized:
            return
        self._splitter_initialized = True

        def apply_sizes():
            if not self.splitter:
                return
            total = max(self.splitter.width(), 900)
            left = max(int(total * 0.38), 340)
            right = max(total - left, 500)
            self.splitter.setSizes([left, right])

        if self.isVisible():
            QtCore.QTimer.singleShot(0, apply_sizes)

    def set_profile(self, profile: str) -> None:
        self.debug_label.setVisible(profile == "Explorer" and bool(self.debug_label.text()))

    def refresh_tree(self) -> None:
        self.tree.clear()
        data = self.adapter.list_tree()
        module = data.get("module")
        if not module:
            QtWidgets.QMessageBox.warning(self, "Content", data.get("reason") or "Module data unavailable.")
            return
        disabled_parts: List[str] = []
        module_label = self._display_name(module.get("title"), module.get("module_id"), "Module")
        module_item = QtWidgets.QTreeWidgetItem([module_label, data.get("status", "")])
        module_item.setToolTip(0, module_label)
        module_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, {"type": "module"})
        self.tree.addTopLevelItem(module_item)
        for section in module.get("sections", []):
            sec_label = self._display_name(section.get("title"), section.get("section_id"), "Section")
            sec_item = QtWidgets.QTreeWidgetItem([sec_label, section.get("status", "")])
            sec_item.setToolTip(0, sec_label)
            sec_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, {"type": "section"})
            module_item.addChild(sec_item)
            for package in section.get("packages", []):
                pkg_label = self._display_name(package.get("title"), package.get("package_id"), "Package")
                pkg_item = QtWidgets.QTreeWidgetItem([pkg_label, package.get("status", "")])
                pkg_item.setToolTip(0, pkg_label)
                pkg_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, {"type": "package"})
                sec_item.addChild(pkg_item)
                for part in package.get("parts", []):
                    part_label = self._display_name(part.get("title"), part.get("part_id"), "Part")
                    status = part.get("status")
                    reason = part.get("reason")
                    component_id = part.get("component_id")
                    workspace_disabled = False
                    if component_id and not self._is_component_enabled(component_id):
                        status = STATUS_UNAVAILABLE
                        reason = WORKSPACE_DISABLED_REASON
                        workspace_disabled = True
                        disabled_parts.append(part.get("part_id") or component_id)
                    part_item = QtWidgets.QTreeWidgetItem([part_label, status])
                    part_item.setToolTip(0, part_label)
                    part_item.setData(
                        0,
                        QtCore.Qt.ItemDataRole.UserRole,
                        {
                            "type": "part",
                            "module_id": module.get("module_id"),
                            "section_id": section.get("section_id"),
                            "package_id": package.get("package_id"),
                            "part_id": part.get("part_id"),
                            "status": status,
                            "reason": reason,
                            "lab_id": (part.get("lab") or {}).get("lab_id"),
                            "component_id": component_id,
                            "workspace_disabled": workspace_disabled,
                        },
                    )
                    pkg_item.addChild(part_item)
        self.tree.expandAll()
        if disabled_parts:
            self._log_disabled_parts(disabled_parts)
        if self.current_part_id:
            if not self._reselect_part(self.current_part_id):
                self._clear_details()
        else:
            self._clear_details()

    def _clear_details(self):
        self.current_part_id = None
        self.current_part_info = None
        self.detail_title.setText("Select a part to view details.")
        self.detail_status.clear()
        self.detail_reason.clear()
        self.debug_label.clear()
        self.debug_label.setVisible(False)
        self.viewer.clear()
        self.install_button.setEnabled(False)
        self.open_button.setEnabled(False)

    def _on_selection(self) -> None:
        item = self.tree.currentItem()
        self.viewer.clear()
        if not item:
            self._clear_details()
            return
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
        if data.get("type") != "part":
            self._clear_details()
            return
        part_id = data.get("part_id")
        self.current_part_id = part_id
        self.detail_title.setText(f"Part {part_id}")
        status = data.get("status")
        reason = data.get("reason") or "—"
        workspace_disabled = bool(data.get("workspace_disabled"))
        if workspace_disabled:
            status = STATUS_UNAVAILABLE
            reason = WORKSPACE_DISABLED_REASON
        self.detail_status.setText(f"Status: {status}")
        self.detail_reason.setText(f"Reason: {reason}")
        if workspace_disabled:
            self.install_button.setEnabled(False)
            self.open_button.setEnabled(False)
        else:
            self.install_button.setEnabled(status != STATUS_READY)
            self.open_button.setEnabled(status == STATUS_READY)

        detail = self.adapter.get_part(part_id)
        self.current_part_info = detail
        self.current_part_detail = detail
        paths = (detail or {}).get("paths") or {}
        assets = paths.get("assets") or {}
        asset_info = []
        for asset, refs in assets.items():
            repo = refs.get("repo")
            store = refs.get("store")
            asset_info.append(f"{asset} -> store: {store or 'n/a'}")
        debug_text = "\n".join(asset_info)
        profile = self.get_profile()
        self.debug_label.setText(debug_text)
        self.debug_label.setVisible(bool(debug_text) and profile == "Explorer")

    def _reselect_part(self, part_id: str) -> bool:
        def walk(item: QtWidgets.QTreeWidgetItem) -> bool:
            data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
            if data.get("type") == "part" and data.get("part_id") == part_id:
                self.tree.setCurrentItem(item)
                return True
            for idx in range(item.childCount()):
                if walk(item.child(idx)):
                    return True
            return False

        for i in range(self.tree.topLevelItemCount()):
            if walk(self.tree.topLevelItem(i)):
                return True
        return False

    def _install_selected(self):
        if not self.current_part_id or self.install_thread:
            return
        self.progress_dialog = QtWidgets.QProgressDialog("Installing part...", "", 0, 0, self)
        self.progress_dialog.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        self.progress_dialog.setCancelButton(None)
        worker = InstallWorker(self.adapter, self.current_part_id)
        thread = QtCore.QThread()
        self.install_thread = thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda result: self._on_install_finished(result, worker, thread))
        worker.error.connect(lambda err: self._on_install_error(err, worker, thread))
        thread.start()

    def _on_install_finished(self, result: Dict, worker: InstallWorker, thread: QtCore.QThread):
        if self.progress_dialog:
            self.progress_dialog.close()
        thread.quit()
        thread.wait()
        worker.deleteLater()
        thread.deleteLater()
        self.install_thread = None
        status = result.get("status")
        message = result.get("reason") or "Completed."
        QtWidgets.QMessageBox.information(self, "Install", f"Status: {status}\n{message}")
        self.refresh_tree()

    def _on_install_error(self, error: str, worker: InstallWorker, thread: QtCore.QThread):
        if self.progress_dialog:
            self.progress_dialog.close()
        thread.quit()
        thread.wait()
        worker.deleteLater()
        thread.deleteLater()
        self.install_thread = None
        QtWidgets.QMessageBox.warning(self, "Install", f"Failed to install: {error}")

    def _open_selected(self):
        if not self.current_part_id:
            return
        detail = self.current_part_detail or self.adapter.get_part(self.current_part_id)
        manifest = detail.get("manifest") or {}
        content = manifest.get("content") or {}
        asset = content.get("asset_path")
        behavior = manifest.get("behavior") or {}
        component_id = detail.get("component_id") or manifest.get("component_id")
        lab_id = None
        detail_lab = (detail.get("lab") if isinstance(detail, dict) else None)
        if isinstance(detail_lab, dict):
            candidate = detail_lab.get("lab_id")
            if isinstance(candidate, str) and candidate.strip():
                lab_id = candidate.strip()
        if not lab_id:
            x_ext = manifest.get("x_extensions")
            if isinstance(x_ext, dict):
                lab_info = x_ext.get("lab")
                if isinstance(lab_info, dict):
                    candidate = lab_info.get("lab_id")
                    if isinstance(candidate, str) and candidate.strip():
                        lab_id = candidate.strip()
        if not lab_id and behavior.get("preset") == "gravity-demo":
            lab_id = "gravity"
        if not lab_id and self.current_part_id == "gravity_demo":
            lab_id = "gravity"
        if not lab_id and behavior.get("preset") == "projectile-demo":
            lab_id = "projectile"
        if not lab_id and self.current_part_id == "projectile_demo":
            lab_id = "projectile"
        if component_id:
            if detail.get("status") != STATUS_READY:
                QtWidgets.QMessageBox.information(self, "Open", "Install this part first.")
                return
            if not self._is_component_enabled(component_id):
                QtWidgets.QMessageBox.information(self, "Open", WORKSPACE_DISABLED_REASON)
                return
            self.open_component(component_id, self.current_part_id, manifest, detail)
            return

        if lab_id:
            if detail.get("status") != STATUS_READY:
                QtWidgets.QMessageBox.information(self, "Open", "Install this lab first.")
                return
            self.open_lab(lab_id, self.current_part_id, manifest, detail)
            return

        if detail.get("status") != STATUS_READY:
            QtWidgets.QMessageBox.information(self, "Open", "Part is not installed yet.")
            return
        if not asset:
            QtWidgets.QMessageBox.information(self, "Open", "Part has no content asset.")
            return
        text = read_asset_text(asset, detail.get("paths"))
        if text is not None:
            self.viewer.setPlainText(text)
            return
        QtWidgets.QMessageBox.warning(self, "Open", "Asset file not found.")

    def select_part(self, part_id: Optional[str]) -> bool:
        if not part_id:
            return False
        if self._reselect_part(part_id):
            self._on_selection()
            return True
        return False

    @staticmethod
    def _display_name(title: Optional[str], fallback: Optional[str], default: str) -> str:
        return str(title or fallback or default)

    def _log_disabled_parts(self, disabled_parts: List[str]) -> None:
        if not self.log_handler:
            return
        try:
            self.log_handler(
                "workspace",
                "H_WS_PART",
                "app_ui/screens/content_browser.py:ContentBrowserScreen.refresh_tree",
                "parts_marked_disabled",
                {"count": len(disabled_parts), "sample": disabled_parts[:3]},
            )
        except Exception:
            pass


