import json
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

from PyQt6 import QtCore, QtWidgets

import content_system
from . import kernel_bridge

CONFIG_PATH = Path("data/roaming/ui_config.json")
PROFILE_PATH = Path("data/roaming/experience_profile.json")
EXPERIENCE_PROFILES = ["Learner", "Educator", "Explorer"]


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
    def __init__(self, on_open_manager, on_open_settings, experience_profile: str):
        super().__init__()
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

        button = QtWidgets.QPushButton("Module Manager")
        button.setFixedWidth(200)
        button.clicked.connect(on_open_manager)

        settings_button = QtWidgets.QPushButton("Settings")
        settings_button.setFixedWidth(200)
        settings_button.clicked.connect(on_open_settings)

        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(subtitle)
        layout.addWidget(self.profile_label)
        layout.addSpacing(30)
        layout.addWidget(button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(settings_button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

    def set_profile(self, profile: str) -> None:
        self.profile_label.setText(f"Experience Profile: {profile}")


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


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PhysicsLab V1")
        self.resize(900, 600)
        self.adapter = ContentSystemAdapter()
        self.current_profile = load_experience_profile()

        self.stacked = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stacked)

        self.main_menu = MainMenuScreen(self._show_module_manager, self._open_settings, self.current_profile)
        self.module_manager = ModuleManagerScreen(self.adapter)

        self.stacked.addWidget(self.main_menu)
        self.stacked.addWidget(self.module_manager)

    def _show_module_manager(self):
        self.stacked.setCurrentWidget(self.module_manager)

    def _open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()
        self.current_profile = load_experience_profile()
        self.main_menu.set_profile(self.current_profile)


def main():
    app = QtWidgets.QApplication(sys.argv)
    apply_ui_config_styles(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
