import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

from PyQt6 import QtCore, QtWidgets

import content_system
from . import kernel_bridge


def _apply_ui_pack(app: QtWidgets.QApplication) -> None:
    try:
        from ui_system import manager
    except Exception as exc:
        print(f"fallback: UI pack disabled (reason: missing ui_system - {exc})")
        return

    try:
        manager.ensure_config()
        pack_id = manager.get_active_pack()
        repo_root = Path("ui_repo/ui_v1")
        store_root = Path("ui_store/ui_v1")
        pack = manager.resolve_pack(pack_id, repo_root, store_root, prefer_store=True)
        if not pack:
            pack = manager.resolve_pack(manager.DEFAULT_PACK_ID, repo_root, store_root, prefer_store=True)
            if not pack:
                print("fallback: UI pack fallback: default (reason: no packs found)")
                return
            qss = manager.load_qss(pack)
            manager.apply_qss(app, qss)
            print(f"fallback: UI pack fallback: {pack.id}")
            return
        qss = manager.load_qss(pack)
        manager.apply_qss(app, qss)
        print(f"success: UI pack applied: {pack.id}")
    except Exception as exc:
        print(f"fallback: UI pack disabled (reason: {exc})")

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
    def __init__(self, on_open_manager):
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

        button = QtWidgets.QPushButton("Module Manager")
        button.setFixedWidth(200)
        button.clicked.connect(on_open_manager)

        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(subtitle)
        layout.addSpacing(30)
        layout.addWidget(button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)


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


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PhysicsLab V1")
        self.resize(900, 600)
        self.adapter = ContentSystemAdapter()

        self.stacked = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stacked)

        self.main_menu = MainMenuScreen(self._show_module_manager)
        self.module_manager = ModuleManagerScreen(self.adapter)

        self.stacked.addWidget(self.main_menu)
        self.stacked.addWidget(self.module_manager)

    def _show_module_manager(self):
        self.stacked.setCurrentWidget(self.module_manager)


def main():
    app = QtWidgets.QApplication(sys.argv)
    _apply_ui_pack(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
