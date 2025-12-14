import json
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

import content_system
from . import kernel_bridge

CONFIG_PATH = Path("data/roaming/ui_config.json")
PROFILE_PATH = Path("data/roaming/experience_profile.json")
EXPERIENCE_PROFILES = ["Learner", "Educator", "Explorer"]


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


def load_ui_config() -> Dict:
    default = {"active_pack_id": "default", "reduced_motion": False}
    path = CONFIG_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default, indent=2), encoding="utf-8")
        return default.copy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in default.items():
            data.setdefault(key, value)
        return data
    except Exception:
        return default.copy()


def save_ui_config(data: Dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_experience_profile() -> str:
    default = EXPERIENCE_PROFILES[0]
    if not PROFILE_PATH.exists():
        return default
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        profile = data.get("profile")
        if profile in EXPERIENCE_PROFILES:
            return profile
    except Exception:
        pass
    return default


def save_experience_profile(profile: str) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps({"profile": profile}, indent=2), encoding="utf-8")


def apply_ui_config_styles(app: QtWidgets.QApplication) -> bool:
    try:
        from ui_system import manager
    except Exception as exc:
        print(f"fallback: UI pack disabled (reason: missing ui_system - {exc})")
        return False

    config = load_ui_config()
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

        if self.profile == "Explorer":
            self._add_button("Diagnostics / Developer", self.on_open_diagnostics)

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

        asset_paths = (paths or {}).get("assets") or {}
        path_info = asset_paths.get(asset)
        candidate_paths = []
        if isinstance(path_info, dict):
            repo_path = path_info.get("repo")
            store_path = path_info.get("store")
            if store_path:
                candidate_paths.append(Path(store_path))
            if repo_path:
                candidate_paths.append(Path(repo_path))

        for path in candidate_paths:
            if path and path.exists():
                try:
                    return path.read_text(encoding="utf-8")
                except OSError:
                    continue
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
        self.profile_combo.addItems(EXPERIENCE_PROFILES)
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
        config = load_ui_config()
        current_pack = config.get("active_pack_id", "default")
        self.reduced_motion_cb.setChecked(bool(config.get("reduced_motion", False)))
        current_profile = load_experience_profile()
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
            config = load_ui_config()
            config["active_pack_id"] = self.pack_combo.currentData()
            config["reduced_motion"] = self.reduced_motion_cb.isChecked()
            save_ui_config(config)

            profile = self.profile_combo.currentText()
            save_experience_profile(profile)

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
    def __init__(self, adapter: "ContentSystemAdapter", on_back, get_profile, open_simulation):
        super().__init__()
        self.adapter = adapter
        self.on_back = on_back
        self.get_profile = get_profile
        self.open_simulation = open_simulation
        self.current_part_id: Optional[str] = None
        self.current_part_info: Optional[Dict] = None

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
        module_item = QtWidgets.QTreeWidgetItem([f"Module {module.get('title')}", data.get("status", "")])
        module_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, {"type": "module"})
        self.tree.addTopLevelItem(module_item)
        for section in module.get("sections", []):
            sec_item = QtWidgets.QTreeWidgetItem([f"Section {section.get('title')}", section.get("status", "")])
            sec_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, {"type": "section"})
            module_item.addChild(sec_item)
            for package in section.get("packages", []):
                pkg_item = QtWidgets.QTreeWidgetItem([f"Package {package.get('title')}", package.get("status", "")])
                pkg_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, {"type": "package"})
                sec_item.addChild(pkg_item)
                for part in package.get("parts", []):
                    part_item = QtWidgets.QTreeWidgetItem([f"Part {part.get('title')}", part.get("status")])
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
        detail = self.adapter.get_part(self.current_part_id)
        manifest = detail.get("manifest") or {}
        content = manifest.get("content") or {}
        asset = content.get("asset_path")
        behavior = manifest.get("behavior") or {}
        if behavior.get("preset") == "gravity-demo":
            if detail.get("status") != STATUS_READY:
                QtWidgets.QMessageBox.information(self, "Open", "Install the simulation first.")
                return
            self.open_simulation(self.current_part_id, manifest, detail)
            return

        if detail.get("status") != STATUS_READY:
            QtWidgets.QMessageBox.information(self, "Open", "Part is not installed yet.")
            return
        if not asset:
            QtWidgets.QMessageBox.information(self, "Open", "Part has no content asset.")
            return
        assets = (detail.get("paths") or {}).get("assets") or {}
        path_info = assets.get(asset) or {}
        for candidate in ["store", "repo"]:
            candidate_path = path_info.get(candidate)
            if candidate_path and Path(candidate_path).exists():
                try:
                    text = Path(candidate_path).read_text(encoding="utf-8")
                    self.viewer.setPlainText(text)
                    return
                except Exception as exc:
                    QtWidgets.QMessageBox.warning(self, "Open", f"Failed to read asset: {exc}")
                    return
        QtWidgets.QMessageBox.warning(self, "Open", "Asset file not found.")


class KernelGravityBackend:
    def __init__(self, y0: float, vy0: float):
        self.session = kernel_bridge.create_gravity_session(y0, vy0)

    def reset(self, y0: float, vy0: float):
        self.session.reset(y0, vy0)

    def step(self, dt: float):
        self.session.step(dt)

    def get_state(self) -> Tuple[float, float, float]:
        return self.session.get_state()

    def close(self):
        self.session.close()


class PythonGravityBackend:
    def __init__(self, g: float, y0: float, vy0: float):
        self.g = g
        self.reset(y0, vy0)

    def reset(self, y0: float, vy0: float):
        self.t = 0.0
        self.y = y0
        self.vy = vy0

    def step(self, dt: float):
        self.vy -= self.g * dt
        self.y += self.vy * dt
        self.t += dt

    def get_state(self) -> Tuple[float, float, float]:
        return self.t, self.y, self.vy

    def close(self):
        pass


class SimulationCanvas(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 300)
        self.max_height = 10.0
        self.current_height = 10.0

    def set_limits(self, max_height: float):
        self.max_height = max(1.0, max_height)

    def set_height(self, height: float):
        self.current_height = max(0.0, height)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#0d1a2d"))

        ground_y = self.height() - 40
        painter.setPen(QtGui.QPen(QtGui.QColor("#3a4f85"), 2))
        painter.drawLine(40, ground_y, self.width() - 40, ground_y)

        usable_height = max(ground_y - 40, 1)
        normalized = min(self.current_height / self.max_height, 1.0)
        ball_y = ground_y - normalized * usable_height
        ball_rect = QtCore.QRectF(0, 0, 30, 30)
        ball_rect.moveCenter(QtCore.QPointF(self.width() / 2, ball_y))
        painter.setBrush(QtGui.QColor("#5a74d3"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#94a9ff"), 2))
        painter.drawEllipse(ball_rect)


class SimulationScreen(QtWidgets.QWidget):
    def __init__(self, on_back, get_profile):
        super().__init__()
        self.on_back = on_back
        self.get_profile = get_profile
        self.backend = None
        self.backend_name = "python-fallback"
        self.profile = get_profile()
        self.base_dt = 0.016

        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        self.title_label = QtWidgets.QLabel("Gravity Simulation")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.backend_label = QtWidgets.QLabel("")
        back_btn = QtWidgets.QPushButton("Back")
        back_btn.clicked.connect(self._handle_back)
        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.backend_label)
        header.addWidget(back_btn)
        layout.addLayout(header)

        controls = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("Start")
        self.start_button.clicked.connect(self._toggle_timer)
        self.reset_button = QtWidgets.QPushButton("Reset")
        self.reset_button.clicked.connect(self._reset_simulation)
        controls.addWidget(self.start_button)
        controls.addWidget(self.reset_button)

        self.dt_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.dt_slider.setRange(5, 40)
        self.dt_slider.setValue(16)
        self.dt_slider.valueChanged.connect(self._update_dt_label)
        self.dt_label = QtWidgets.QLabel("dt: 0.016s")
        controls.addWidget(self.dt_slider)
        controls.addWidget(self.dt_label)
        controls.addStretch()
        layout.addLayout(controls)

        info_layout = QtWidgets.QHBoxLayout()
        self.t_label = QtWidgets.QLabel("t: 0.00 s")
        self.y_label = QtWidgets.QLabel("y: 0.00 m")
        self.v_label = QtWidgets.QLabel("vy: 0.00 m/s")
        info_layout.addWidget(self.t_label)
        info_layout.addWidget(self.y_label)
        info_layout.addWidget(self.v_label)
        layout.addLayout(info_layout)

        self.canvas = SimulationCanvas()
        layout.addWidget(self.canvas, stretch=1)

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

        self.initial_height = 10.0
        self.initial_vy = 0.0
        self.g = 9.81
        self.part_id = ""

    def load_part(self, part_id: str, manifest: Dict):
        self.stop_simulation()
        behavior = manifest.get("behavior") or {}
        params = behavior.get("parameters") or {}
        self.initial_height = float(params.get("initial_height_m", 10.0))
        self.initial_vy = float(params.get("initial_vy_m_s", 0.0))
        self.g = float(params.get("gravity_m_s2", 9.81))
        self.part_id = part_id
        self.title_label.setText(f"Gravity Simulation — {part_id}")
        self.canvas.set_limits(max(self.initial_height * 1.2, 5.0))
        self._init_backend()
        self._reset_simulation()
        self._update_profile_controls()

    def set_profile(self, profile: str):
        self.profile = profile
        self._update_profile_controls()

    def _update_profile_controls(self):
        is_learner = self.profile == "Learner"
        self.dt_slider.setVisible(not is_learner)
        self.dt_label.setVisible(not is_learner)
        self.backend_label.setVisible(self.profile == "Explorer")

    def _init_backend(self):
        if self.backend:
            self.backend.close()
            self.backend = None
        try:
            self.backend = KernelGravityBackend(self.initial_height, self.initial_vy)
            self.backend_name = "kernel"
        except Exception as exc:
            print(f"Simulation fallback: {exc}")
            self.backend = PythonGravityBackend(self.g, self.initial_height, self.initial_vy)
            self.backend_name = "python-fallback"
        self.backend_label.setText(f"Backend: {self.backend_name}")

    def _handle_back(self):
        self.stop_simulation()
        if self.backend:
            self.backend.close()
            self.backend = None
        self.on_back()

    def _toggle_timer(self):
        if self.timer.isActive():
            self.timer.stop()
            self.start_button.setText("Start")
        else:
            self.timer.start()
            self.start_button.setText("Pause")

    def _reset_simulation(self):
        if self.backend:
            self.backend.reset(self.initial_height, self.initial_vy)
            t, y, vy = self.backend.get_state()
            self._update_state(t, y, vy)
        self.canvas.set_height(self.initial_height)

    def _current_dt(self) -> float:
        if self.profile == "Learner":
            return self.base_dt
        return max(0.001, self.dt_slider.value() / 1000.0)

    def _update_dt_label(self):
        self.dt_label.setText(f"dt: {self.dt_slider.value() / 1000:.3f}s")

    def _tick(self):
        if not self.backend:
            return
        dt = self._current_dt()
        try:
            self.backend.step(dt)
            t, y, vy = self.backend.get_state()
        except Exception as exc:
            self.timer.stop()
            QtWidgets.QMessageBox.warning(self, "Simulation", f"Simulation error: {exc}")
            return
        y_display = max(0.0, y)
        if y <= 0.0 and vy < 0:
            vy = 0.0
        self._update_state(t, y_display, vy)
        self.canvas.set_height(y_display)

    def _update_state(self, t: float, y: float, vy: float):
        self.t_label.setText(f"t: {t:.2f} s")
        self.y_label.setText(f"y: {y:.2f} m")
        self.v_label.setText(f"vy: {vy:.2f} m/s")

    def stop_simulation(self):
        self.timer.stop()
        self.start_button.setText("Start")


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, initial_profile: str):
        super().__init__()
        self.setWindowTitle("PhysicsLab V1")
        self.resize(900, 600)
        self.adapter = ContentSystemAdapter()
        self.current_profile = initial_profile

        self.stacked = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stacked)

        self.main_menu = MainMenuScreen(
            self._show_module_manager,
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
            self._open_simulation,
        )
        self.simulation_screen = SimulationScreen(self._show_content_browser, lambda: self.current_profile)

        self.stacked.addWidget(self.main_menu)
        self.stacked.addWidget(self.module_manager)
        self.stacked.addWidget(self.content_browser)
        self.stacked.addWidget(self.simulation_screen)
        self._show_main_menu()

    def _show_module_manager(self):
        self.simulation_screen.stop_simulation()
        self.stacked.setCurrentWidget(self.module_manager)

    def _show_main_menu(self):
        self.simulation_screen.stop_simulation()
        self.stacked.setCurrentWidget(self.main_menu)

    def _open_content_browser(self):
        self.simulation_screen.stop_simulation()
        self.content_browser.set_profile(self.current_profile)
        self.content_browser.refresh_tree()
        self.stacked.setCurrentWidget(self.content_browser)

    def _show_content_browser(self):
        self.simulation_screen.stop_simulation()
        self.stacked.setCurrentWidget(self.content_browser)

    def _open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()
        self.current_profile = load_experience_profile()
        if self.main_menu:
            self.main_menu.set_profile(self.current_profile)
        if self.content_browser:
            self.content_browser.set_profile(self.current_profile)
        if self.simulation_screen:
            self.simulation_screen.set_profile(self.current_profile)

    def _open_module_management(self):
        PlaceholderDialog("Module Management", "Module management tools coming soon.", self).exec()

    def _open_content_management(self):
        PlaceholderDialog("Content Management", "Content management tools coming soon.", self).exec()

    def _open_diagnostics(self):
        PlaceholderDialog("Diagnostics / Developer", "Diagnostics dashboard coming soon.", self).exec()

    def _quit_app(self):
        app = QtWidgets.QApplication.instance()
        if app:
            app.quit()

    def _open_simulation(self, part_id: str, manifest: Dict, detail: Dict):
        self.simulation_screen.set_profile(self.current_profile)
        self.simulation_screen.load_part(part_id, manifest)
        self.stacked.setCurrentWidget(self.simulation_screen)


def main():
    profile = load_experience_profile()
    print(f"Experience profile: {profile}")
    app = QtWidgets.QApplication(sys.argv)
    apply_ui_config_styles(app)
    window = MainWindow(profile)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
