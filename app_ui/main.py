import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

import content_system
from . import config as ui_config
from . import kernel_bridge
from .labs import registry as lab_registry
from .labs.host import LabHost

try:
    from core_center.discovery import ensure_data_roots, discover_components
    from core_center.registry import load_registry, save_registry, upsert_records
    from core_center.storage_report import format_report_text, generate_report
    from core_center.cleanup import purge_cache, prune_dumps

    CORE_CENTER_AVAILABLE = True
    CORE_CENTER_ERROR = ""
except Exception as exc:  # pragma: no cover
    CORE_CENTER_AVAILABLE = False
    CORE_CENTER_ERROR = str(exc)

RECOMMENDED_PART_SEQUENCE = ["text_intro", "gravity_demo"]
PROFILE_GUIDE_KEYS = {
    "Learner": "learner",
    "Educator": "educator",
    "Explorer": "explorer",
}


class InstallWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(dict)
    error = QtCore.pyqtSignal(str)

    def __init__(self, adapter: "ContentSystemAdapter", part_id: str):
        super().__init__()
        self.adapter = adapter
        self.part_id = part_id

    @QtCore.pyqtSlot()
    def run(self):
        try:
            result = self.adapter.download_part(self.part_id)
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - defensive
            self.error.emit(str(exc))


class TaskWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(object)
    error = QtCore.pyqtSignal(str)

    def __init__(self, func: Callable[[], Any]):
        super().__init__()
        self.func = func

    @QtCore.pyqtSlot()
    def run(self):
        try:
            result = self.func()
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - defensive
            self.error.emit(str(exc))


def read_asset_text(asset_path: Optional[str], paths: Optional[Dict[str, Any]]) -> Optional[str]:
    if not asset_path:
        return None
    assets = (paths or {}).get("assets") or {}
    path_info = assets.get(asset_path)
    if not isinstance(path_info, dict):
        return None
    for key in ("store", "repo"):
        candidate = path_info.get(key)
        if candidate:
            candidate_path = Path(candidate)
            if candidate_path.exists():
                try:
                    return candidate_path.read_text(encoding="utf-8")
                except OSError:
                    continue
    return None


def apply_ui_config_styles(app: QtWidgets.QApplication) -> bool:
    try:
        from ui_system import manager
    except Exception as exc:
        print(f"fallback: UI pack disabled (reason: missing ui_system - {exc})")
        return False

    config = ui_config.load_ui_config()
    pack_id = config.get("active_pack_id", "default")
    try:
        manager.ensure_config()
        repo_root = Path("ui_repo/ui_v1")
        store_root = Path("ui_store/ui_v1")
        pack = manager.resolve_pack(pack_id, repo_root, store_root, prefer_store=True)
        if not pack:
            pack = manager.resolve_pack(manager.DEFAULT_PACK_ID, repo_root, store_root, prefer_store=True)
            if not pack:
                print("fallback: UI pack fallback: default (reason: no packs found)")
                return False
            qss = manager.load_qss(pack)
            manager.apply_qss(app, qss)
            print(f"fallback: UI pack fallback: {pack.id}")
            return True
        qss = manager.load_qss(pack)
        manager.apply_qss(app, qss)
        print(f"success: UI pack applied: {pack.id}")
        return True
    except Exception as exc:
        print(f"fallback: UI pack disabled (reason: {exc})")
        return False

STATUS_READY = "READY"
STATUS_NOT_INSTALLED = "NOT_INSTALLED"
STATUS_UNAVAILABLE = "UNAVAILABLE"


class ContentSystemAdapter:
    """Thin wrapper safeguarding UI from backend errors."""

    def list_tree(self) -> Dict:
        try:
            return content_system.list_tree()
        except Exception as exc:
            return {"module": None, "status": STATUS_UNAVAILABLE, "reason": str(exc)}

    def get_part_status(self, part_id: str) -> Tuple[str, Optional[str]]:
        try:
            return content_system.get_part_status(part_id)
        except Exception as exc:
            return STATUS_UNAVAILABLE, str(exc)

    def get_part(self, part_id: str) -> Dict:
        try:
            return content_system.get_part(part_id)
        except Exception as exc:
            return {"status": STATUS_UNAVAILABLE, "reason": str(exc)}

    def download_part(self, part_id: str) -> Dict:
        try:
            return content_system.download_part(part_id)
        except Exception as exc:
            return {"status": STATUS_UNAVAILABLE, "reason": str(exc)}


class MainMenuScreen(QtWidgets.QWidget):
    def __init__(
        self,
        on_start_physics,
        on_open_content_browser,
        on_open_settings,
        on_open_module_mgmt,
        on_open_content_mgmt,
        on_open_diagnostics,
        on_quit,
        experience_profile: str,
    ):
        super().__init__()
        self.on_start_physics = on_start_physics
        self.on_open_content_browser = on_open_content_browser
        self.on_open_settings = on_open_settings
        self.on_open_module_mgmt = on_open_module_mgmt
        self.on_open_content_mgmt = on_open_content_mgmt
        self.on_open_diagnostics = on_open_diagnostics
        self.on_quit = on_quit
        self.profile = experience_profile

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        title = QtWidgets.QLabel("PhysicsLab")
        title.setObjectName("title")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 32px; font-weight: bold;")

        subtitle = QtWidgets.QLabel("Primary Mode Active")
        subtitle.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 18px; color: #555;")

        self.profile_label = QtWidgets.QLabel(f"Experience Profile: {experience_profile}")
        self.profile_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.profile_label.setStyleSheet("font-size: 14px; color: #333;")

        self.buttons_layout = QtWidgets.QVBoxLayout()
        self.buttons_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(subtitle)
        layout.addWidget(self.profile_label)
        layout.addSpacing(30)
        layout.addLayout(self.buttons_layout)
        self._rebuild_buttons()

    def set_profile(self, profile: str) -> None:
        self.profile = profile
        self.profile_label.setText(f"Experience Profile: {profile}")
        self._rebuild_buttons()

    def _clear_buttons(self) -> None:
        while self.buttons_layout.count():
            item = self.buttons_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_button(self, label: str, callback) -> None:
        button = QtWidgets.QPushButton(label)
        button.setFixedWidth(220)
        button.clicked.connect(callback)
        self.buttons_layout.addWidget(button)

    def _rebuild_buttons(self) -> None:
        self._clear_buttons()
        self._add_button("Start Physics", self.on_start_physics)
        self._add_button("Physics Content", self.on_open_content_browser)

        if self.profile in ("Educator", "Explorer"):
            self._add_button("Module Management", self.on_open_module_mgmt)
            self._add_button("Content Management", self.on_open_content_mgmt)

        if self.profile in ("Educator", "Explorer"):
            self._add_button("System Health / Storage", self.on_open_diagnostics)

        self._add_button("Settings", self.on_open_settings)
        self._add_button("Quit", self.on_quit)


class ModuleManagerScreen(QtWidgets.QWidget):
    def __init__(self, adapter: ContentSystemAdapter):
        super().__init__()
        self.adapter = adapter
        self.current_part_id: Optional[str] = None

        main_layout = QtWidgets.QVBoxLayout(self)

        header = QtWidgets.QLabel("Module Manager")
        header.setStyleSheet("font-size: 20px; font-weight: bold;")
        main_layout.addWidget(header)

        self.error_label = QtWidgets.QLabel()
        self.error_label.setStyleSheet("color: #b00;")
        main_layout.addWidget(self.error_label)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, stretch=1)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Item", "Status"])
        self.tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        splitter.addWidget(self.tree)

        detail_widget = QtWidgets.QWidget()
        detail_layout = QtWidgets.QVBoxLayout(detail_widget)

        self.part_title = QtWidgets.QLabel("Select a part to view details.")
        self.part_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        detail_layout.addWidget(self.part_title)

        self.part_status = QtWidgets.QLabel()
        detail_layout.addWidget(self.part_status)

        self.part_reason = QtWidgets.QLabel()
        self.part_reason.setStyleSheet("color: #444;")
        detail_layout.addWidget(self.part_reason)

        self.preview = QtWidgets.QTextEdit()
        self.preview.setReadOnly(True)
        detail_layout.addWidget(self.preview, stretch=1)

        button_row = QtWidgets.QHBoxLayout()
        self.download_button = QtWidgets.QPushButton("Download")
        self.download_button.clicked.connect(self._download_selected_part)
        button_row.addWidget(self.download_button)

        self.run_button = QtWidgets.QPushButton("Run")
        self.run_button.clicked.connect(self._run_selected_part)
        button_row.addWidget(self.run_button)
        button_row.addStretch(1)
        detail_layout.addLayout(button_row)

        splitter.addWidget(detail_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self._clear_details()
        self.refresh_tree()

    def refresh_tree(self) -> None:
        self.tree.clear()
        data = self.adapter.list_tree()

        module = data.get("module")
        reason = data.get("reason")
        if not module:
            self.error_label.setText(reason or "Module information unavailable.")
            return

        self.error_label.clear()
        module_status = data.get("status", STATUS_READY)
        module_item = QtWidgets.QTreeWidgetItem([
            f"Module {module.get('module_id')}: {module.get('title')}",
            module_status,
        ])
        self.tree.addTopLevelItem(module_item)

        for section in module.get("sections", []):
            sec_status = section.get("status", STATUS_READY)
            section_text = f"Section {section.get('section_id')}: {section.get('title')}"
            section_item = QtWidgets.QTreeWidgetItem([section_text, sec_status])
            if section.get("reason"):
                section_item.setToolTip(0, section.get("reason"))
            module_item.addChild(section_item)

            for package in section.get("packages", []):
                pkg_status = package.get("status", STATUS_READY)
                package_text = f"Package {package.get('package_id')}: {package.get('title')}"
                package_item = QtWidgets.QTreeWidgetItem([package_text, pkg_status])
                if package.get("reason"):
                    package_item.setToolTip(0, package.get("reason"))
                section_item.addChild(package_item)

                for part in package.get("parts", []):
                    part_text = f"Part {part.get('part_id')}: {part.get('title')}"
                    part_item = QtWidgets.QTreeWidgetItem([part_text, part.get("status")])
                    tooltip = part.get("reason")
                    if tooltip:
                        part_item.setToolTip(0, tooltip)
                    part_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, part.get("part_id"))
                    package_item.addChild(part_item)

        self.tree.expandAll()
        if self.current_part_id:
            self._reselect_part(self.current_part_id)

    def _reselect_part(self, part_id: str) -> None:
        def walk(item: QtWidgets.QTreeWidgetItem) -> bool:
            if item.data(0, QtCore.Qt.ItemDataRole.UserRole) == part_id:
                self.tree.setCurrentItem(item)
                return True
            for idx in range(item.childCount()):
                if walk(item.child(idx)):
                    return True
            return False

        for i in range(self.tree.topLevelItemCount()):
            if walk(self.tree.topLevelItem(i)):
                break

    def _on_tree_selection_changed(self) -> None:
        item = self.tree.currentItem()
        if not item:
            self._clear_details()
            return
        part_id = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if part_id:
            self.current_part_id = part_id
            self._show_part(part_id)
        else:
            self._clear_details()

    def _clear_details(self) -> None:
        self.current_part_id = None
        self.part_title.setText("Select a part to view details.")
        self.part_status.clear()
        self.part_reason.clear()
        self.preview.setPlainText("")
        self.download_button.setEnabled(False)
        self.run_button.setEnabled(False)

    def _show_part(self, part_id: str) -> None:
        status, reason = self.adapter.get_part_status(part_id)
        part_info = self.adapter.get_part(part_id)

        manifest = part_info.get("manifest") if isinstance(part_info, dict) else None

        title = manifest.get("title") if isinstance(manifest, dict) else part_id
        self.part_title.setText(title or part_id)
        self.part_status.setText(f"Status: {status}")
        self.part_reason.setText(f"Reason: {reason or part_info.get('reason', '') or '—'}")

        if status == STATUS_READY and self._is_gravity_demo(manifest):
            self.preview.setPlainText(
                "Run the gravity demo to see simulated positions.\nClick 'Run' to start."
            )
        else:
            preview_text = self._load_preview_text(
                manifest,
                part_info.get("paths") if isinstance(part_info, dict) else {},
            )
            self.preview.setPlainText(preview_text)

        self.download_button.setEnabled(status == STATUS_NOT_INSTALLED)
        self.kernel_error = None
        can_run = False
        if status == STATUS_READY and self._is_gravity_demo(manifest):
            try:
                kernel_bridge.ensure_kernel_available()
                can_run = True
            except kernel_bridge.KernelNotAvailable as exc:
                self.kernel_error = str(exc)
        self.run_button.setEnabled(can_run)

    def _load_preview_text(self, manifest: Optional[Dict], paths: Optional[Dict]) -> str:
        if not manifest or "content" not in manifest:
            return "Preview unavailable."

        if manifest.get("part_type") != "text":
            return "Preview available only for text-based parts."

        content = manifest.get("content") or {}
        asset = content.get("asset_path")
        if not asset:
            return "Part manifest missing asset path."

        text = read_asset_text(asset, paths)
        if text is not None:
            return text
        return "Asset not available yet."

    def _download_selected_part(self) -> None:
        if not self.current_part_id:
            return
        result = self.adapter.download_part(self.current_part_id)
        if result.get("status") == STATUS_UNAVAILABLE:
            QtWidgets.QMessageBox.warning(
                self,
                "Download Failed",
                f"Unable to download part: {result.get('reason', 'Unknown error')}",
            )
        else:
            QtWidgets.QMessageBox.information(
                self,
                "Download Complete",
                f"Part status: {result.get('status')} ({result.get('reason') or 'ok'})",
            )
        self.refresh_tree()
        self._reselect_part(self.current_part_id)

    def _is_gravity_demo(self, manifest: Optional[Dict]) -> bool:
        if not manifest:
            return False
        behavior = manifest.get("behavior")
        if not isinstance(behavior, dict):
            return False
        return behavior.get("preset") == "gravity-demo"

    def _run_selected_part(self) -> None:
        if not self.current_part_id:
            return
        if self.kernel_error:
            QtWidgets.QMessageBox.warning(self, "Kernel Error", self.kernel_error)
            return

        part_data = self.adapter.get_part(self.current_part_id)
        manifest = part_data.get("manifest") if isinstance(part_data, dict) else None
        if not manifest:
            QtWidgets.QMessageBox.warning(self, "Run Failed", "Part manifest unavailable.")
            return

        behavior = manifest.get("behavior") or {}
        params = behavior.get("parameters") or {}
        y0 = params.get("initial_height_m", 10.0)
        vy0 = 0.0
        dt = params.get("time_step_s", 0.05)
        steps = 120

        try:
            timeline = kernel_bridge.run_gravity_demo(y0=y0, vy0=vy0, dt=dt, steps=steps)
        except kernel_bridge.KernelNotAvailable as exc:
            QtWidgets.QMessageBox.warning(self, "Kernel Missing", str(exc))
            return
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Kernel Error", str(exc))
            return

        preview_lines = ["t (s)\ty (m)\tvy (m/s)"]
        for t, y, vy in timeline:
            preview_lines.append(f"{t:.2f}\t{y:.2f}\t{vy:.2f}")
        self.preview.setPlainText("\n".join(preview_lines))


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(420, 320)
        self.manager = None
        self.repo_root = Path("ui_repo/ui_v1")
        self.store_root = Path("ui_store/ui_v1")

        layout = QtWidgets.QVBoxLayout(self)

        self.pack_combo = QtWidgets.QComboBox()
        self.pack_status = QtWidgets.QLabel()
        layout.addWidget(QtWidgets.QLabel("UI Pack"))
        layout.addWidget(self.pack_combo)
        layout.addWidget(self.pack_status)

        self.reduced_motion_cb = QtWidgets.QCheckBox("Enable Reduced Motion")
        layout.addWidget(self.reduced_motion_cb)

        layout.addWidget(QtWidgets.QLabel("Experience Profile"))
        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.addItems(ui_config.EXPERIENCE_PROFILES)
        layout.addWidget(self.profile_combo)

        button_row = QtWidgets.QHBoxLayout()
        save_button = QtWidgets.QPushButton("Save")
        cancel_button = QtWidgets.QPushButton("Cancel")
        save_button.clicked.connect(self._save_settings)
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(save_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        self._populate_fields()

    def _populate_fields(self) -> None:
        config = ui_config.load_ui_config()
        current_pack = config.get("active_pack_id", "default")
        self.reduced_motion_cb.setChecked(bool(config.get("reduced_motion", False)))
        current_profile = ui_config.load_experience_profile()
        idx = self.profile_combo.findText(current_profile)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)

        try:
            from ui_system import manager
            self.manager = manager
            packs = manager.list_packs(self.repo_root, self.store_root)
            if not packs:
                self.pack_combo.addItem("Default (built-in)", "default")
                self.pack_status.setText("No packs found; using default.")
            else:
                for pack in packs:
                    label = f"{pack.name} ({pack.id}) [{pack.source}]"
                    self.pack_combo.addItem(label, pack.id)
            index = self.pack_combo.findData(current_pack)
            if index >= 0:
                self.pack_combo.setCurrentIndex(index)
        except Exception as exc:
            self.manager = None
            self.pack_combo.addItem("Default (built-in)", "default")
            self.pack_status.setText(f"UI manager unavailable: {exc}")

    def _save_settings(self) -> None:
        try:
            config = ui_config.load_ui_config()
            config["active_pack_id"] = self.pack_combo.currentData()
            config["reduced_motion"] = self.reduced_motion_cb.isChecked()
            ui_config.save_ui_config(config)

            profile = self.profile_combo.currentText()
            ui_config.save_experience_profile(profile)

            app = QtWidgets.QApplication.instance()
            applied = True
            if app:
                applied = apply_ui_config_styles(app)

            if applied:
                QtWidgets.QMessageBox.information(self, "Settings", "Settings saved.")
            else:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Settings",
                    "Settings saved, but the UI pack could not be applied. Check console for details.",
                )
            self.accept()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Settings", f"Failed to save settings: {exc}")


class PlaceholderDialog(QtWidgets.QDialog):
    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(360, 200)
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)


class ContentBrowserScreen(QtWidgets.QWidget):
    def __init__(self, adapter: "ContentSystemAdapter", on_back, get_profile, open_lab):
        super().__init__()
        self.adapter = adapter
        self.on_back = on_back
        self.get_profile = get_profile
        self.open_lab = open_lab
        self.current_part_id: Optional[str] = None
        self.current_part_info: Optional[Dict] = None
        self.current_part_detail: Optional[Dict] = None

        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Physics Content Browser")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        back_btn = QtWidgets.QPushButton("Back")
        back_btn.clicked.connect(self.on_back)
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_tree)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(refresh_btn)
        header.addWidget(back_btn)
        layout.addLayout(header)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(splitter, stretch=1)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Item", "Status"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnCount(2)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setMinimumWidth(260)
        self.tree.itemSelectionChanged.connect(self._on_selection)
        splitter.addWidget(self.tree)

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

        splitter.addWidget(detail_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self.progress_dialog: Optional[QtWidgets.QProgressDialog] = None
        self.install_thread: Optional[QtCore.QThread] = None
        self.refresh_tree()

    def set_profile(self, profile: str) -> None:
        self.debug_label.setVisible(profile == "Explorer" and bool(self.debug_label.text()))

    def refresh_tree(self) -> None:
        self.tree.clear()
        data = self.adapter.list_tree()
        module = data.get("module")
        if not module:
            QtWidgets.QMessageBox.warning(self, "Content", data.get("reason") or "Module data unavailable.")
            return
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
                    part_item = QtWidgets.QTreeWidgetItem([part_label, part.get("status")])
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
                            "status": part.get("status"),
                            "reason": part.get("reason"),
                        },
                    )
                    pkg_item.addChild(part_item)
        self.tree.expandAll()
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
        self.detail_status.setText(f"Status: {data.get('status')}")
        self.detail_reason.setText(f"Reason: {data.get('reason') or '—'}")
        self.install_button.setEnabled(data.get("status") != STATUS_READY)
        self.open_button.setEnabled(data.get("status") == STATUS_READY)

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
        lab_id = manifest.get("lab_id")
        if not lab_id and behavior.get("preset") == "gravity-demo":
            lab_id = "gravity"
        if not lab_id and self.current_part_id == "gravity_demo":
            lab_id = "gravity"
        if not lab_id and behavior.get("preset") == "projectile-demo":
            lab_id = "projectile"
        if not lab_id and self.current_part_id == "projectile_demo":
            lab_id = "projectile"
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


class SystemHealthScreen(QtWidgets.QWidget):
    def __init__(self, on_back):
        super().__init__()
        self.on_back = on_back
        self.available = CORE_CENTER_AVAILABLE
        self._task_thread: Optional[QtCore.QThread] = None
        self._task_worker: Optional[TaskWorker] = None
        self._pending_initial_refresh = True

        layout = QtWidgets.QVBoxLayout(self)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("System Health / Storage")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_report)
        self.refresh_btn = refresh_btn
        header.addWidget(refresh_btn)
        back_btn = QtWidgets.QPushButton("Back")
        back_btn.clicked.connect(self.on_back)
        header.addWidget(back_btn)
        layout.addLayout(header)

        self.status_label = QtWidgets.QLabel()
        layout.addWidget(self.status_label)

        folders_row = QtWidgets.QHBoxLayout()
        open_data_btn = QtWidgets.QPushButton("Open data folder")
        open_data_btn.clicked.connect(lambda: self._open_folder(Path("data")))
        folders_row.addWidget(open_data_btn)
        open_store_btn = QtWidgets.QPushButton("Open content store")
        open_store_btn.clicked.connect(lambda: self._open_folder(Path("content_store")))
        folders_row.addWidget(open_store_btn)
        folders_row.addStretch()
        layout.addLayout(folders_row)

        cleanup_row = QtWidgets.QHBoxLayout()
        self.purge_btn = QtWidgets.QPushButton("Purge cache")
        self.purge_btn.clicked.connect(self._purge_cache)
        cleanup_row.addWidget(self.purge_btn)
        self.prune_btn = QtWidgets.QPushButton("Prune dumps")
        self.prune_btn.clicked.connect(self._prune_dumps)
        cleanup_row.addWidget(self.prune_btn)
        cleanup_row.addStretch()
        layout.addLayout(cleanup_row)

        self.report_view = QtWidgets.QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setPlaceholderText("Storage report will appear here.")
        layout.addWidget(self.report_view, stretch=1)

        if not self.available:
            self._set_status(f"Core Center unavailable: {CORE_CENTER_ERROR or 'not installed'}")
            self._set_control_enabled(False)
        else:
            self._set_status("Ready to run Core Center diagnostics.")

    def prepare(self) -> None:
        if self.available and self._pending_initial_refresh:
            self._refresh_report()

    def _set_control_enabled(self, enabled: bool) -> None:
        self.refresh_btn.setEnabled(enabled)
        self.purge_btn.setEnabled(enabled)
        self.prune_btn.setEnabled(enabled)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _refresh_report(self) -> None:
        if not self.available or self._task_thread:
            return
        self._set_status("Refreshing storage report...")

        def job():
            ensure_data_roots()
            registry_path = Path("data/roaming/registry.json")
            existing = load_registry(registry_path)
            discovered = discover_components()
            merged = upsert_records(existing, discovered)
            save_registry(registry_path, merged)
            report = generate_report(merged)
            text = format_report_text(report)
            return {"text": text}

        self._run_task(job, self._update_report)

    def _purge_cache(self) -> None:
        if not self.available or self._task_thread:
            return
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Purge cache",
            "This will delete all files under data/cache/.\nContinue?",
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._set_status("Purging data/cache...")

        def job():
            ensure_data_roots()
            return purge_cache(Path("data/cache"))

        self._run_task(job, lambda result: self._show_cleanup_result("Cache purge", result))

    def _prune_dumps(self) -> None:
        if not self.available or self._task_thread:
            return
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Prune dumps",
            "Older crash dumps will be removed. Keep going?",
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._set_status("Pruning data/dumps...")

        def job():
            ensure_data_roots()
            return prune_dumps(Path("data/dumps"), max_age_days=30, max_total_bytes=50 * 1024 * 1024)

        self._run_task(job, lambda result: self._show_cleanup_result("Dump pruning", result))

    def _update_report(self, result: Dict) -> None:
        text = result.get("text") or "No data."
        self.report_view.setPlainText(text)
        self._set_status("Storage report updated.")
        self._pending_initial_refresh = False

    def _show_cleanup_result(self, label: str, result: Dict) -> None:
        bytes_freed = result.get("bytes_freed", 0)
        removed = len(result.get("removed", []))
        QtWidgets.QMessageBox.information(
            self,
            label,
            f"{label} complete.\nRemoved entries: {removed}\nBytes freed: {bytes_freed}",
        )
        self._set_status(f"{label} finished.")
        self._refresh_report()

    def _run_task(self, job: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        worker = TaskWorker(job)
        thread = QtCore.QThread()
        self._task_worker = worker
        self._task_thread = thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda result: self._handle_task_finished(result, callback))
        worker.error.connect(self._handle_task_error)
        thread.start()
        self._set_control_enabled(False)

    def _handle_task_finished(self, result: Any, callback: Callable[[Any], None]) -> None:
        self._teardown_task()
        try:
            callback(result)
        except Exception as exc:  # pragma: no cover - defensive
            QtWidgets.QMessageBox.warning(self, "System Health", f"Operation failed: {exc}")
        self._set_control_enabled(True)

    def _handle_task_error(self, error: str) -> None:
        self._teardown_task()
        QtWidgets.QMessageBox.warning(self, "System Health", f"Operation failed: {error}")
        self._set_control_enabled(True)
        self._set_status("Idle.")

    def _teardown_task(self) -> None:
        if self._task_thread:
            self._task_thread.quit()
            self._task_thread.wait()
            self._task_thread.deleteLater()
            self._task_thread = None
        if self._task_worker:
            self._task_worker.deleteLater()
            self._task_worker = None

    def _open_folder(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            url = QtCore.QUrl.fromLocalFile(str(path.resolve()))
            QtGui.QDesktopServices.openUrl(url)
        except Exception as exc:  # pragma: no cover - defensive
            QtWidgets.QMessageBox.warning(self, "System Health", f"Unable to open folder: {exc}")



class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, initial_profile: str):
        super().__init__()
        self.setWindowTitle("PhysicsLab V1")
        self.resize(900, 600)
        self.adapter = ContentSystemAdapter()
        self.current_profile = initial_profile

        self.stacked = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stacked)
        self.lab_widget: Optional[QtWidgets.QWidget] = None
        self.lab_host_widget: Optional[QtWidgets.QWidget] = None

        self.main_menu = MainMenuScreen(
            self._start_physics,
            self._open_content_browser,
            self._open_settings,
            self._open_module_management,
            self._open_content_management,
            self._open_diagnostics,
            self._quit_app,
            self.current_profile,
        )
        self.module_manager = ModuleManagerScreen(self.adapter)
        self.content_browser = ContentBrowserScreen(
            self.adapter,
            self._show_main_menu,
            lambda: self.current_profile,
            self._open_lab,
        )
        self.system_health = SystemHealthScreen(self._show_main_menu)

        self.stacked.addWidget(self.main_menu)
        self.stacked.addWidget(self.module_manager)
        self.stacked.addWidget(self.content_browser)
        self.stacked.addWidget(self.system_health)
        self._show_main_menu()

    def _show_module_manager(self):
        self._dispose_lab_widget()
        self.stacked.setCurrentWidget(self.module_manager)

    def _show_main_menu(self):
        self._dispose_lab_widget()
        self.stacked.setCurrentWidget(self.main_menu)

    def _start_physics(self):
        for part_id in RECOMMENDED_PART_SEQUENCE:
            if self._open_content_browser(focus_part=part_id):
                return
        self._open_content_browser()

    def _open_content_browser(self, focus_part: Optional[str] = None) -> bool:
        self._dispose_lab_widget()
        self.content_browser.set_profile(self.current_profile)
        self.content_browser.refresh_tree()
        selected = False
        if focus_part:
            selected = self.content_browser.select_part(focus_part)
        self.stacked.setCurrentWidget(self.content_browser)
        return selected

    def _show_content_browser(self):
        self._dispose_lab_widget()
        self.stacked.setCurrentWidget(self.content_browser)

    def _open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()
        self.current_profile = ui_config.load_experience_profile()
        if self.main_menu:
            self.main_menu.set_profile(self.current_profile)
        if self.content_browser:
            self.content_browser.set_profile(self.current_profile)

    def _open_module_management(self):
        PlaceholderDialog("Module Management", "Module management tools coming soon.", self).exec()

    def _open_content_management(self):
        PlaceholderDialog("Content Management", "Content management tools coming soon.", self).exec()

    def _open_diagnostics(self):
        self._dispose_lab_widget()
        if self.system_health:
            self.system_health.prepare()
            self.stacked.setCurrentWidget(self.system_health)

    def _quit_app(self):
        app = QtWidgets.QApplication.instance()
        if app:
            app.quit()

    def _dispose_lab_widget(self):
        if self.lab_widget is not None:
            if hasattr(self.lab_widget, "stop_simulation"):
                try:
                    self.lab_widget.stop_simulation()
                except Exception:
                    pass
            self.lab_widget = None
        if self.lab_host_widget is not None:
            self.stacked.removeWidget(self.lab_host_widget)
            self.lab_host_widget.deleteLater()
            self.lab_host_widget = None

    def _open_lab(self, lab_id: str, part_id: str, manifest: Dict, detail: Dict):
        plugin = lab_registry.get_lab(lab_id)
        if not plugin:
            QtWidgets.QMessageBox.warning(self, "Lab", f"Lab '{lab_id}' not available.")
            return
        self._dispose_lab_widget()
        try:
            widget = plugin.create_widget(self._show_content_browser, lambda: self.current_profile)
            if not isinstance(widget, QtWidgets.QWidget):
                raise TypeError("Lab widgets must extend QWidget")
            if hasattr(widget, "set_profile"):
                widget.set_profile(self.current_profile)
            reduced_motion = ui_config.get_reduced_motion()
            if hasattr(widget, "set_reduced_motion"):
                try:
                    widget.set_reduced_motion(reduced_motion)
                except Exception:
                    pass
            if hasattr(widget, "load_part"):
                widget.load_part(part_id, manifest, detail)
            guide_text = self._load_lab_guide_text(manifest, detail, self.current_profile)
            host = LabHost(widget, guide_text, reduced_motion)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Lab", f"Failed to open lab: {exc}")
            return
        self.lab_widget = widget
        self.lab_host_widget = host
        self.stacked.addWidget(host)
        self.stacked.setCurrentWidget(host)

    def _load_lab_guide_text(self, manifest: Dict, detail: Dict, profile: str) -> str:
        fallback = "Guide coming soon for this lab."
        if not isinstance(manifest, dict):
            return fallback
        guides = (manifest.get("x_extensions") or {}).get("guides")
        if not isinstance(guides, dict):
            return fallback
        key = PROFILE_GUIDE_KEYS.get(profile, "learner")
        asset_path = guides.get(key)
        if not asset_path:
            for alt in ("learner", "educator", "explorer"):
                asset_path = guides.get(alt)
                if asset_path:
                    break
        if not asset_path:
            asset_path = next(iter(guides.values()), None)
        if not asset_path:
            return fallback
        paths = detail.get("paths") if isinstance(detail, dict) else {}
        text = read_asset_text(asset_path, paths)
        if text is not None:
            return text
        return "Guide asset missing or unreadable. Reinstall the part if this persists."


def main():
    profile = ui_config.load_experience_profile()
    print(f"Experience profile: {profile}")
    app = QtWidgets.QApplication(sys.argv)
    apply_ui_config_styles(app)
    window = MainWindow(profile)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
