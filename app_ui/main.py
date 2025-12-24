# =============================================================================
# NAV INDEX (search these tags)
# [NAV-00] Imports / constants
# [NAV-01] Small utilities (font safety, path helpers, etc.)
# [NAV-10] Navigation controller / routing helpers
# [NAV-20] AppHeader + workspace selector wiring
# [NAV-30] Screens: MainMenuScreen
# [NAV-31] Screens: ContentBrowserScreen
# [NAV-32] Screens: SystemHealthScreen
# [NAV-33] Screens: WorkspaceManagementScreen (app_ui/screens/workspace_management.py)
# [NAV-34] Screens: ModuleManagementScreen
# [NAV-35] Screens: ComponentManagementScreen
# [NAV-36] Screens: ContentManagementScreen
# [NAV-37] Screens: ComponentSandboxScreen
# [NAV-38] Screens: ComponentHostScreen
# [NAV-39] Screens: LabHostScreen
# [NAV-90] MainWindow
# [NAV-99] main() entrypoint
# =============================================================================

# === [NAV-00] Imports / constants ============================================
# region NAV-00 Imports / constants
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

import content_system
from . import config as ui_config
from . import kernel_bridge
from .labs import registry as lab_registry
from .labs.host import LabHost
from .labs.host import DEFAULT_POLICY as LAB_DEFAULT_POLICY
from .widgets.app_header import AppHeader
from .widgets.workspace_selector import WorkspaceSelector
from app_ui.screens.workspace_management import (
    WorkspaceManagementScreen,
    _load_workspace_config_from_root,
    _request_inventory_snapshot,
    _save_workspace_config_to_root,
    _workspace_prefs_root_from_dir,
    _workspace_prefs_root_from_paths,
)
from diagnostics.fs_ops import safe_copytree, safe_rmtree

DEBUG_LOG_PATH = Path(r"c:\Users\ahmed\Downloads\PhysicsLab\.cursor\debug.log")
DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
# endregion


# === [NAV-01] Small utilities ================================================
# region NAV-01 Small utilities
def _agent_debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: Dict[str, Any]) -> None:
    # region agent log
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as _fh:
            _fh.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": run_id,
                        "hypothesisId": hypothesis_id,
                        "location": location,
                        "message": message,
                        "data": data,
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # endregion




# === [NAV-20] AppHeader + workspace selector wiring ==========================
# region NAV-20 WorkspaceComponentPolicy
class WorkspaceComponentPolicy:
    def __init__(self) -> None:
        self.enabled_pack_ids: set[str] = set()
        self.available_pack_ids: set[str] = set()
        self.disabled_component_ids: set[str] = set()

    def update(
        self,
        *,
        enabled_pack_ids: set[str],
        available_pack_ids: set[str],
        disabled_component_ids: set[str],
    ) -> None:
        self.enabled_pack_ids = set(enabled_pack_ids)
        self.available_pack_ids = set(available_pack_ids)
        self.disabled_component_ids = set(disabled_component_ids)

    def is_pack_enabled(self, pack_id: Optional[str]) -> bool:
        if not pack_id:
            return True
        if not self.enabled_pack_ids:
            return pack_id in self.available_pack_ids if self.available_pack_ids else True
        return pack_id in self.enabled_pack_ids

    def is_component_enabled(self, component_id: Optional[str]) -> bool:
        if not component_id:
            return True
        return component_id not in self.disabled_component_ids
# endregion


_WORKSPACE_COMPONENT_POLICY: Optional[WorkspaceComponentPolicy] = None


def _set_global_component_policy(policy: WorkspaceComponentPolicy) -> None:
    global _WORKSPACE_COMPONENT_POLICY
    _WORKSPACE_COMPONENT_POLICY = policy


def _get_global_component_policy() -> Optional[WorkspaceComponentPolicy]:
    return _WORKSPACE_COMPONENT_POLICY


def _ensure_safe_font(app: QtWidgets.QApplication, min_point_size: int = 10) -> None:
    try:
        font = app.font()
        point_size = font.pointSize()
        pixel_size = font.pixelSize()
        if point_size is None or point_size <= 0:
            if isinstance(pixel_size, int) and pixel_size > 0:
                return
            safe_size = max(1, int(min_point_size))
            if safe_size > 0:
                font.setPointSize(safe_size)
                app.setFont(font)
        elif point_size < min_point_size:
            safe_size = max(1, int(min_point_size))
            font.setPointSize(safe_size)
            app.setFont(font)
    except Exception:
        pass

try:
    from runtime_bus import topics as BUS_TOPICS
    from runtime_bus.bus import get_global_bus

    RUNTIME_BUS_AVAILABLE = True
    RUNTIME_BUS_ERROR = ""
except Exception as exc:  # pragma: no cover
    BUS_TOPICS = None
    get_global_bus = None
    RUNTIME_BUS_AVAILABLE = False
    RUNTIME_BUS_ERROR = str(exc)

if RUNTIME_BUS_AVAILABLE and get_global_bus:
    APP_BUS = get_global_bus()
else:
    APP_BUS = None

try:
    from core_center.discovery import ensure_data_roots, discover_components
    from core_center.registry import load_registry, save_registry, upsert_records
    from core_center.storage_report import format_report_text, generate_report
    from core_center.cleanup import purge_cache, prune_dumps
    from core_center import bus_endpoints as CORE_CENTER_BUS_ENDPOINTS

    CORE_CENTER_AVAILABLE = True
    CORE_CENTER_ERROR = ""
except Exception as exc:  # pragma: no cover
    CORE_CENTER_AVAILABLE = False
    CORE_CENTER_ERROR = str(exc)
    CORE_CENTER_BUS_ENDPOINTS = None

try:
    from component_runtime import packs as component_packs
    from component_runtime import registry as component_registry
    from component_runtime.context import ComponentContext, StorageRoots
    from component_runtime.host import ComponentHost
    from component_runtime import demo_component as _component_demo  # noqa: F401

    COMPONENT_RUNTIME_AVAILABLE = True
    COMPONENT_RUNTIME_ERROR = ""
except Exception as exc:  # pragma: no cover
    component_packs = None
    component_registry = None
    ComponentContext = None
    StorageRoots = None
    ComponentHost = None
    COMPONENT_RUNTIME_AVAILABLE = False
    COMPONENT_RUNTIME_ERROR = str(exc)

BUS_COMM_REPORT_REQUEST = (
    getattr(BUS_TOPICS, "RUNTIME_BUS_REPORT_REQUEST", "runtime.bus.report.request")
    if BUS_TOPICS
    else "runtime.bus.report.request"
)
BUS_JOBS_LIST_REQUEST = (
    BUS_TOPICS.CORE_JOBS_LIST_REQUEST if BUS_TOPICS else "core.jobs.list.request"
)
BUS_WORKSPACE_GET_ACTIVE = (
    BUS_TOPICS.CORE_WORKSPACE_GET_ACTIVE_REQUEST if BUS_TOPICS else "core.workspace.get_active.request"
)
BUS_WORKSPACE_CREATE = (
    BUS_TOPICS.CORE_WORKSPACE_CREATE_REQUEST if BUS_TOPICS else "core.workspace.create.request"
)

if APP_BUS:
    def _handle_bus_comm_report(envelope):
        try:
            stats = APP_BUS.get_stats()
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"diagnostics_failed: {exc}"}
        text_lines = [
            "Runtime Bus Diagnostics",
            f"Subscribers: {stats.get('subscriber_count', 0)}",
            f"Request handlers: {stats.get('request_handler_count', 0)}",
            f"Sticky topics: {stats.get('sticky_topic_count', 0)}",
        ]
        sticky = stats.get("sticky_topics") or []
        if sticky:
            text_lines.append(f"Sticky list: {', '.join(sticky)}")
        topics = stats.get("subscriptions_by_topic") or {}
        if topics:
            text_lines.append("Subscriptions by topic:")
            for name, count in sorted(topics.items()):
                text_lines.append(f"  - {name}: {count}")
        requests = stats.get("request_topics") or []
        if requests:
            text_lines.append("Request handlers:")
            for topic in sorted(requests):
                text_lines.append(f"  - {topic}")
        return {"ok": True, "text": "\n".join(text_lines), "json": stats}

    try:
        APP_BUS.register_handler(BUS_COMM_REPORT_REQUEST, _handle_bus_comm_report)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"runtime bus: failed to register diagnostics handler ({exc})")

if APP_BUS and CORE_CENTER_BUS_ENDPOINTS:
    try:
        CORE_CENTER_BUS_ENDPOINTS.register_core_center_endpoints(APP_BUS)
    except Exception as exc:  # pragma: no cover - optional log
        print(f"runtime bus: failed to register core_center endpoints ({exc})")

RECOMMENDED_PART_SEQUENCE = ["text_intro", "gravity_demo"]
PROFILE_GUIDE_KEYS = {
    "Learner": "learner",
    "Educator": "educator",
    "Explorer": "explorer",
}

# === [NAV-01] Small utilities ================================================
# region NAV-01 Workers
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
# endregion
# === [NAV-01] Small utilities ================================================
# region NAV-01 Asset helpers / UI config
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
            _ensure_safe_font(app)
            print(f"fallback: UI pack fallback: {pack.id}")
            return True
        qss = manager.load_qss(pack)
        manager.apply_qss(app, qss)
        _ensure_safe_font(app)
        print(f"success: UI pack applied: {pack.id}")
        return True
    except Exception as exc:
        print(f"fallback: UI pack disabled (reason: {exc})")
        return False

STATUS_READY = "READY"
STATUS_NOT_INSTALLED = "NOT_INSTALLED"
STATUS_UNAVAILABLE = "UNAVAILABLE"
WORKSPACE_DISABLED_REASON = "Disabled by workspace. Enable pack in Workspace Management."
# endregion


# === [NAV-01] Small utilities ================================================
# region NAV-01 ContentSystemAdapter
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
# endregion


# === [NAV-30] Screens: MainMenuScreen =======================================
# region NAV-30 MainMenuScreen
class MainMenuScreen(QtWidgets.QWidget):
    def __init__(
        self,
        on_start_physics,
        on_open_content_browser,
        on_open_settings,
        on_open_module_mgmt,
        on_open_content_mgmt,
        on_open_diagnostics,
        on_open_workspace_mgmt,
        on_open_component_mgmt,
        on_open_component_sandbox,
        on_quit,
        experience_profile: str,
        *,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
    ):
        super().__init__()
        self.on_start_physics = on_start_physics
        self.on_open_content_browser = on_open_content_browser
        self.on_open_settings = on_open_settings
        self.on_open_module_mgmt = on_open_module_mgmt
        self.on_open_content_mgmt = on_open_content_mgmt
        self.on_open_diagnostics = on_open_diagnostics
        self.on_open_workspace_mgmt = on_open_workspace_mgmt
        self.on_open_component_mgmt = on_open_component_mgmt
        self.on_open_component_sandbox = on_open_component_sandbox
        self.on_quit = on_quit
        self.profile = experience_profile

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        if workspace_selector_factory:
            header = AppHeader(
                title="PhysicsLab",
                on_back=None,
                workspace_selector=workspace_selector_factory(),
            )
            layout.addWidget(header)

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
        self._add_button("Quick Start", self.on_start_physics)
        self._add_button("Physics Content", self.on_open_content_browser)

        if self.profile in ("Educator", "Explorer"):
            self._add_button("Module Management", self.on_open_module_mgmt)
            self._add_button("Content Management", self.on_open_content_mgmt)

        if self.profile in ("Educator", "Explorer"):
            self._add_button("System Health / Storage", self.on_open_diagnostics)

        if self.profile == "Explorer" and self.on_open_workspace_mgmt:
            self._add_button("Workspace Management", self.on_open_workspace_mgmt)

        if self.profile == "Explorer" and self.on_open_component_mgmt:
            self._add_button("Component Management", self.on_open_component_mgmt)

        if self.profile == "Explorer" and self.on_open_component_sandbox and COMPONENT_RUNTIME_AVAILABLE:
            self._add_button("Component Sandbox", self.on_open_component_sandbox)

        self._add_button("Settings", self.on_open_settings)
        self._add_button("Quit", self.on_quit)
# endregion


# === [NAV-10] Navigation controller / routing helpers ========================
# region NAV-10 ModuleManagerScreen (legacy)
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


# endregion


# === [NAV-20] AppHeader + workspace selector wiring ==========================
# region NAV-20 SettingsDialog
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


# endregion


# === [NAV-20] AppHeader + workspace selector wiring ==========================
# region NAV-20 PlaceholderDialog
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


# endregion


# === [NAV-31] Screens: ContentBrowserScreen =================================
# region NAV-31 ContentBrowserScreen
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
            _agent_debug_log(
                "workspace",
                "H_WS_PART",
                "app_ui/main.py:ContentBrowserScreen.refresh_tree",
                "parts_marked_disabled",
                {"count": len(disabled_parts), "sample": disabled_parts[:3]},
            )
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


BUS_REPORT_REQUEST = (
    BUS_TOPICS.CORE_STORAGE_REPORT_REQUEST if BUS_TOPICS else "core.storage.report.request"
)
BUS_REPORT_READY = (
    BUS_TOPICS.CORE_STORAGE_REPORT_READY if BUS_TOPICS else "core.storage.report.ready"
)
BUS_CLEANUP_REQUEST = (
    BUS_TOPICS.CORE_CLEANUP_REQUEST if BUS_TOPICS else "core.cleanup.request"
)
BUS_CLEANUP_COMPLETED = (
    BUS_TOPICS.CORE_CLEANUP_COMPLETED if BUS_TOPICS else "core.cleanup.completed"
)
BUS_JOB_COMPLETED = BUS_TOPICS.JOB_COMPLETED if BUS_TOPICS else "job.completed"
BUS_JOB_PROGRESS = BUS_TOPICS.JOB_PROGRESS if BUS_TOPICS else "job.progress"
BUS_REGISTRY_REQUEST = (
    BUS_TOPICS.CORE_REGISTRY_GET_REQUEST if BUS_TOPICS else "core.registry.get.request"
)
BUS_INVENTORY_REQUEST = (
    BUS_TOPICS.CORE_INVENTORY_GET_REQUEST if BUS_TOPICS else "core.inventory.get.request"
)
BUS_JOBS_GET_REQUEST = BUS_TOPICS.CORE_JOBS_GET_REQUEST if BUS_TOPICS else "core.jobs.get.request"
BUS_RUNS_LIST_REQUEST = (
    BUS_TOPICS.CORE_RUNS_LIST_REQUEST if BUS_TOPICS else "core.runs.list.request"
)
BUS_RUNS_DELETE_REQUEST = (
    BUS_TOPICS.CORE_RUNS_DELETE_REQUEST if BUS_TOPICS else "core.runs.delete.request"
)
BUS_RUNS_PRUNE_REQUEST = (
    BUS_TOPICS.CORE_RUNS_PRUNE_REQUEST if BUS_TOPICS else "core.runs.prune.request"
)
BUS_RUNS_DELETE_MANY_REQUEST = (
    BUS_TOPICS.CORE_RUNS_DELETE_MANY_REQUEST if BUS_TOPICS else "core.runs.delete_many.request"
)
BUS_MODULE_INSTALL_REQUEST = (
    BUS_TOPICS.CORE_CONTENT_MODULE_INSTALL_REQUEST
    if BUS_TOPICS
    else "core.content.module.install.request"
)
BUS_MODULE_UNINSTALL_REQUEST = (
    BUS_TOPICS.CORE_CONTENT_MODULE_UNINSTALL_REQUEST
    if BUS_TOPICS
    else "core.content.module.uninstall.request"
)
BUS_COMPONENT_PACK_INSTALL_REQUEST = (
    BUS_TOPICS.CORE_COMPONENT_PACK_INSTALL_REQUEST
    if BUS_TOPICS
    else "core.component_pack.install.request"
)
BUS_COMPONENT_PACK_UNINSTALL_REQUEST = (
    BUS_TOPICS.CORE_COMPONENT_PACK_UNINSTALL_REQUEST
    if BUS_TOPICS
    else "core.component_pack.uninstall.request"
)
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
BUS_WORKSPACE_ACTIVE_CHANGED = (
    getattr(BUS_TOPICS, "WORKSPACE_ACTIVE_CHANGED", "workspace.active.changed")
    if BUS_TOPICS
    else "workspace.active.changed"
)
BUS_MODULE_PROGRESS = (
    BUS_TOPICS.CONTENT_INSTALL_PROGRESS if BUS_TOPICS else "content.install.progress"
)
BUS_MODULE_COMPLETED = (
    BUS_TOPICS.CONTENT_INSTALL_COMPLETED if BUS_TOPICS else "content.install.completed"
)

CORE_JOB_REPORT = "core.report.generate"
CORE_JOB_MODULE_INSTALL = "core.module.install"
CORE_JOB_MODULE_UNINSTALL = "core.module.uninstall"
CORE_JOB_CLEANUP_CACHE = "core.cleanup.cache"
CORE_JOB_CLEANUP_DUMPS = "core.cleanup.dumps"


# endregion


# === [NAV-10] Navigation controller / routing helpers ========================
# region NAV-10 Bus dispatch bridge
class _BusDispatchBridge(QtCore.QObject):
    envelope_dispatched = QtCore.pyqtSignal(object, object)

    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self.envelope_dispatched.connect(
            self._invoke_handler,
            QtCore.Qt.ConnectionType.QueuedConnection,
        )

    @QtCore.pyqtSlot(object, object)
    def _invoke_handler(self, handler: Callable[[Any], None], envelope: Any) -> None:
        try:
            handler(envelope)
        except Exception:  # pragma: no cover - defensive
            pass


# endregion


# === [NAV-32] Screens: SystemHealthScreen ===================================
# region NAV-32 SystemHealthScreen
class SystemHealthScreen(QtWidgets.QWidget):
    # --- [NAV-32A] ctor / dependencies
    cleanup_event = QtCore.pyqtSignal(dict)
    module_progress_event = QtCore.pyqtSignal(dict)
    module_completed_event = QtCore.pyqtSignal(dict)

    def __init__(
        self,
        on_back,
        cleanup_enabled: bool = False,
        *,
        bus=None,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
    ):
        super().__init__()
        self.on_back = on_back
        self.bus = bus
        self.direct_available = bool(cleanup_enabled)
        self.refresh_capability = bool(self.bus or self.direct_available)
        self._task_thread: Optional[QtCore.QThread] = None
        self._task_worker: Optional[TaskWorker] = None
        self._pending_initial_refresh = True
        self.pending_report_job: Optional[str] = None
        self.pending_cleanup_job_id: Optional[str] = None
        self.pending_cleanup_kind: Optional[str] = None
        self._cleanup_running = False
        self._module_job_running = False
        self.pending_module_job_id: Optional[str] = None
        self.pending_module_action: Optional[str] = None
        self.pending_module_id: str = "physics_v1"
        self._module_installed: Optional[bool] = None
        self._inventory_checked = False
        self._module_poll_timer: Optional[QtCore.QTimer] = None
        self._module_poll_deadline: float = 0.0
        self._is_explorer = False
        self._bus_subscriptions: list[str] = []
        self._bus_subscribed = False
        self._module_signals_connected = False
        self._runs_active_lab_id: Optional[str] = None
        self._runs_bulk_edit = False
        self._connect_ui_signals()
        self._bus_dispatch_bridge = _BusDispatchBridge(self)

        layout = QtWidgets.QVBoxLayout(self)

        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title="System Health / Storage",
            on_back=self.on_back,
            workspace_selector=selector,
        )
        layout.addWidget(header)

        segment_row = QtWidgets.QHBoxLayout()
        self._segment_buttons: list[QtWidgets.QPushButton] = []

        def _make_segment(label: str, index: int) -> QtWidgets.QPushButton:
            btn = QtWidgets.QPushButton(label)
            btn.setCheckable(True)
            btn.setObjectName("segmentButton")
            btn.clicked.connect(lambda _=False, i=index: self._set_segment(i))
            self._segment_buttons.append(btn)
            return btn

        self._segment_overview_btn = _make_segment("Overview", 0)
        self._segment_runs_btn = _make_segment("Runs", 1)
        self._segment_maintenance_btn = _make_segment("Maintenance", 2)
        self._segment_modules_btn = _make_segment("Modules", 3)
        self._segment_jobs_btn = _make_segment("Jobs", 4)
        for btn in self._segment_buttons:
            segment_row.addWidget(btn)
        segment_row.addStretch()
        layout.addLayout(segment_row)

        self._stack = QtWidgets.QStackedWidget()
        layout.addWidget(self._stack, stretch=1)

        page_overview = QtWidgets.QWidget()
        page_overview_layout = QtWidgets.QVBoxLayout(page_overview)
        page_overview_layout.setContentsMargins(0, 0, 0, 0)

        overview_top = QtWidgets.QHBoxLayout()
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_report)
        self.refresh_btn = refresh_btn
        overview_top.addWidget(refresh_btn)
        open_data_btn = QtWidgets.QPushButton("Open data folder")
        open_data_btn.clicked.connect(lambda: self._open_folder(Path("data")))
        overview_top.addWidget(open_data_btn)
        open_store_btn = QtWidgets.QPushButton("Open content store")
        open_store_btn.clicked.connect(lambda: self._open_folder(Path("content_store")))
        overview_top.addWidget(open_store_btn)
        overview_top.addStretch()
        page_overview_layout.addLayout(overview_top)

        self.status_label = QtWidgets.QLabel()
        page_overview_layout.addWidget(self.status_label)

        self.report_view = QtWidgets.QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setPlaceholderText("Storage report will appear here.")
        page_overview_layout.addWidget(self.report_view, stretch=1)
        self._stack.addWidget(page_overview)

        page_runs = QtWidgets.QWidget()
        page_runs_layout = QtWidgets.QVBoxLayout(page_runs)
        page_runs_layout.setContentsMargins(0, 0, 0, 0)

        runs_toolbar = QtWidgets.QHBoxLayout()
        self.runs_refresh_btn = QtWidgets.QPushButton("Refresh")
        self.runs_refresh_btn.clicked.connect(self._refresh_runs_list)
        runs_toolbar.addWidget(self.runs_refresh_btn)
        self.runs_prune_btn = QtWidgets.QPushButton("Prune…")
        self.runs_prune_btn.clicked.connect(self._open_prune_runs_dialog)
        runs_toolbar.addWidget(self.runs_prune_btn)
        self.runs_delete_selected_btn = QtWidgets.QPushButton("Delete Selected")
        self.runs_delete_selected_btn.clicked.connect(self._delete_selected_runs)
        runs_toolbar.addWidget(self.runs_delete_selected_btn)
        self.runs_delete_all_btn = QtWidgets.QPushButton("Delete All (Lab)")
        self.runs_delete_all_btn.clicked.connect(self._delete_all_runs_for_lab)
        runs_toolbar.addWidget(self.runs_delete_all_btn)
        self.runs_select_all_btn = QtWidgets.QPushButton("Select all (Lab)")
        self.runs_select_all_btn.clicked.connect(self._select_all_runs_for_lab)
        runs_toolbar.addWidget(self.runs_select_all_btn)
        self.runs_clear_btn = QtWidgets.QPushButton("Clear (Lab)")
        self.runs_clear_btn.clicked.connect(self._clear_runs_for_lab)
        runs_toolbar.addWidget(self.runs_clear_btn)
        self.runs_delete_all_workspace_btn = QtWidgets.QPushButton("Delete All (Workspace)")
        self.runs_delete_all_workspace_btn.clicked.connect(self._delete_all_runs_for_workspace)
        runs_toolbar.addWidget(self.runs_delete_all_workspace_btn)
        self.runs_workspace_label = QtWidgets.QLabel("Workspace: ?")
        self.runs_workspace_label.setStyleSheet("color: #444;")
        runs_toolbar.addWidget(self.runs_workspace_label)
        runs_toolbar.addStretch()
        page_runs_layout.addLayout(runs_toolbar)

        self.runs_status = QtWidgets.QLabel("")
        self.runs_status.setStyleSheet("color: #555;")
        page_runs_layout.addWidget(self.runs_status)

        self.runs_tree = QtWidgets.QTreeWidget()
        self.runs_tree.setColumnCount(5)
        self.runs_tree.setHeaderLabels(["Run", "Created", "Size", "Root", "Actions"])
        header_view = self.runs_tree.header()
        header_view.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.runs_tree.itemChanged.connect(self._on_runs_item_changed)
        self.runs_tree.currentItemChanged.connect(self._on_runs_current_item_changed)
        self.runs_tree.itemClicked.connect(self._on_runs_item_clicked)
        page_runs_layout.addWidget(self.runs_tree, stretch=1)
        self._stack.addWidget(page_runs)

        page_maintenance = QtWidgets.QWidget()
        page_maintenance_layout = QtWidgets.QVBoxLayout(page_maintenance)
        page_maintenance_layout.setContentsMargins(0, 0, 0, 0)

        cleanup_row = QtWidgets.QHBoxLayout()
        self.purge_btn = QtWidgets.QPushButton("Purge cache")
        self.purge_btn.clicked.connect(self._purge_cache)
        cleanup_row.addWidget(self.purge_btn)
        self.prune_btn = QtWidgets.QPushButton("Prune dumps")
        self.prune_btn.clicked.connect(self._prune_dumps)
        cleanup_row.addWidget(self.prune_btn)
        cleanup_row.addStretch()
        page_maintenance_layout.addLayout(cleanup_row)

        self.completion_panel = QtWidgets.QFrame()
        self.completion_panel.setVisible(False)
        self.completion_panel.setStyleSheet("QFrame { border: 1px solid #ccc; border-radius: 4px; padding: 6px; }")
        panel_layout = QtWidgets.QHBoxLayout(self.completion_panel)
        panel_layout.setContentsMargins(8, 4, 8, 4)
        self.completion_title = QtWidgets.QLabel("")
        self.completion_details = QtWidgets.QLabel("")
        self.completion_details.setWordWrap(True)
        dismiss_btn = QtWidgets.QPushButton("Dismiss")
        dismiss_btn.setFixedWidth(80)
        dismiss_btn.clicked.connect(lambda: self.completion_panel.setVisible(False))
        text_box = QtWidgets.QVBoxLayout()
        text_box.addWidget(self.completion_title)
        text_box.addWidget(self.completion_details)
        panel_layout.addLayout(text_box)
        panel_layout.addStretch()
        panel_layout.addWidget(dismiss_btn)
        page_maintenance_layout.addWidget(self.completion_panel)
        page_maintenance_layout.addStretch()
        self._stack.addWidget(page_maintenance)

        page_modules = QtWidgets.QWidget()
        page_modules_layout = QtWidgets.QVBoxLayout(page_modules)
        page_modules_layout.setContentsMargins(0, 0, 0, 0)

        module_row = QtWidgets.QHBoxLayout()
        self.install_btn = QtWidgets.QPushButton("Install module (local)")
        self.install_btn.clicked.connect(lambda: self._start_module_job("install"))
        self.uninstall_btn = QtWidgets.QPushButton("Uninstall module (local)")
        self.uninstall_btn.clicked.connect(lambda: self._start_module_job("uninstall"))
        module_row.addWidget(self.install_btn)
        module_row.addWidget(self.uninstall_btn)
        module_row.addStretch()
        page_modules_layout.addLayout(module_row)

        self.module_panel = QtWidgets.QFrame()
        self.module_panel.setVisible(False)
        self.module_panel.setStyleSheet("QFrame { border: 1px solid #ddd; border-radius: 4px; padding: 6px; }")
        module_layout = QtWidgets.QVBoxLayout(self.module_panel)
        module_header = QtWidgets.QHBoxLayout()
        self.module_title = QtWidgets.QLabel("Module Status")
        self.module_title.setStyleSheet("font-weight: bold;")
        module_header.addWidget(self.module_title)
        module_header.addStretch()
        module_dismiss = QtWidgets.QPushButton("Dismiss")
        module_dismiss.setFixedWidth(80)
        module_dismiss.clicked.connect(lambda: self.module_panel.setVisible(False))
        module_header.addWidget(module_dismiss)
        module_layout.addLayout(module_header)
        self.module_details = QtWidgets.QLabel("")
        self.module_details.setWordWrap(True)
        module_layout.addWidget(self.module_details)
        page_modules_layout.addWidget(self.module_panel)
        page_modules_layout.addStretch()
        self._stack.addWidget(page_modules)

        page_jobs = QtWidgets.QWidget()
        page_jobs_layout = QtWidgets.QVBoxLayout(page_jobs)
        page_jobs_layout.setContentsMargins(0, 0, 0, 0)

        comm_row = QtWidgets.QHBoxLayout()
        self.comm_btn = QtWidgets.QPushButton("Job History")
        self.comm_btn.clicked.connect(self._show_comm_report)
        self.comm_btn.setVisible(False)
        comm_row.addWidget(self.comm_btn)
        comm_row.addStretch()
        page_jobs_layout.addLayout(comm_row)

        self.comm_panel = QtWidgets.QFrame()
        self.comm_panel.setVisible(False)
        self.comm_panel.setStyleSheet("QFrame { border: 1px solid #ddd; border-radius: 4px; padding: 6px; }")
        comm_panel_layout = QtWidgets.QVBoxLayout(self.comm_panel)
        comm_header = QtWidgets.QHBoxLayout()
        self.comm_title = QtWidgets.QLabel("Communication Report")
        self.comm_title.setStyleSheet("font-weight: bold;")
        self.comm_close = QtWidgets.QPushButton("Dismiss")
        self.comm_close.setFixedWidth(80)
        self.comm_close.clicked.connect(lambda: self.comm_panel.setVisible(False))
        comm_header.addWidget(self.comm_title)
        comm_header.addStretch()
        comm_header.addWidget(self.comm_close)
        comm_panel_layout.addLayout(comm_header)
        self.comm_text = QtWidgets.QPlainTextEdit()
        self.comm_text.setReadOnly(True)
        self.comm_text.setPlaceholderText("Communication report output")
        self.comm_text.setMaximumHeight(140)
        comm_panel_layout.addWidget(self.comm_text)
        page_jobs_layout.addWidget(self.comm_panel)
        page_jobs_layout.addStretch()
        self._stack.addWidget(page_jobs)

        self._set_segment(0)

        if not self.refresh_capability:
            self._set_status(f"Core Center unavailable: {CORE_CENTER_ERROR or 'not installed'}")
        elif self.bus:
            self._set_status("Ready to request storage report via runtime bus.")
        else:
            self._set_status("Ready to run Core Center diagnostics.")

        self._set_control_enabled(True)
        self._init_bus_subscriptions()
        self._update_comm_controls()

    def prepare(self) -> None:
        if self.refresh_capability and self._pending_initial_refresh:
            self._refresh_report()
        self._update_comm_controls()
        if self.bus and not self._inventory_checked:
            self._refresh_inventory()

    def _set_segment(self, index: int) -> None:
        if index < 0 or index >= self._stack.count():
            return
        self._stack.setCurrentIndex(index)
        for idx, btn in enumerate(self._segment_buttons):
            btn.setChecked(idx == index)
    def _set_control_enabled(self, enabled: bool) -> None:
        enable_refresh = bool(self.refresh_capability and enabled)
        self.refresh_btn.setEnabled(enable_refresh)
        cleanup_available = bool(self.bus or self.direct_available)
        cleanup_enabled = bool(enabled and cleanup_available and not self._cleanup_running)
        self.purge_btn.setEnabled(cleanup_enabled)
        self.prune_btn.setEnabled(cleanup_enabled)
        runs_available = bool(self.bus)
        if hasattr(self, "runs_refresh_btn"):
            self.runs_refresh_btn.setEnabled(bool(enabled and runs_available))
        if hasattr(self, "runs_prune_btn"):
            self.runs_prune_btn.setEnabled(bool(enabled and runs_available))
        if hasattr(self, "runs_delete_selected_btn"):
            self.runs_delete_selected_btn.setEnabled(bool(enabled and runs_available))
        if hasattr(self, "runs_delete_all_btn"):
            self.runs_delete_all_btn.setEnabled(bool(enabled and runs_available))
        if hasattr(self, "runs_select_all_btn"):
            self.runs_select_all_btn.setEnabled(bool(enabled and runs_available))
        if hasattr(self, "runs_clear_btn"):
            self.runs_clear_btn.setEnabled(bool(enabled and runs_available))
        if hasattr(self, "runs_delete_all_workspace_btn"):
            self.runs_delete_all_workspace_btn.setEnabled(bool(enabled and runs_available))
        module_enabled = bool(
            enabled and self.bus and self._is_explorer and not self._module_job_running
        )
        install_allowed = module_enabled
        uninstall_allowed = module_enabled
        if self._module_installed is True:
            install_allowed = False
        elif self._module_installed is False:
            uninstall_allowed = False
        if hasattr(self, "install_btn"):
            self.install_btn.setEnabled(install_allowed)
        if hasattr(self, "uninstall_btn"):
            self.uninstall_btn.setEnabled(uninstall_allowed)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _update_module_button_labels(self) -> None:
        module_id = self.pending_module_id or "module"
        if hasattr(self, "install_btn"):
            self.install_btn.setText(f"Install {module_id} module (local)")
        if hasattr(self, "uninstall_btn"):
            self.uninstall_btn.setText(f"Uninstall {module_id} module (local)")

    def _refresh_inventory(self) -> None:
        self._inventory_checked = True
        if not self.bus:
            self._module_installed = None
            self._update_module_button_labels()
            self._set_control_enabled(True)
            return
        try:
            response = self.bus.request(
                BUS_INVENTORY_REQUEST,
                {},
                source="app_ui",
                timeout_ms=1500,
            )
        except Exception:
            self._module_installed = None
            self._update_module_button_labels()
            self._set_control_enabled(True)
            return
        if not response.get("ok"):
            self._module_installed = None
            self._update_module_button_labels()
            self._set_control_enabled(True)
            return
        inventory = response.get("inventory") or {}
        modules = inventory.get("modules") or []
        module_ids = [m.get("id") for m in modules if m.get("id")]
        preferred = "physics_v1"
        if preferred in module_ids:
            self.pending_module_id = preferred
        elif module_ids:
            self.pending_module_id = module_ids[0]
        self._module_installed = bool(module_ids)
        self._update_module_button_labels()
        self._set_control_enabled(True)

    def _update_comm_controls(self) -> None:
        profile = ui_config.load_experience_profile()
        is_explorer = profile == "Explorer"
        self._is_explorer = is_explorer
        available = bool(self.bus and is_explorer)
        self.comm_btn.setVisible(available)
        if not available:
            self.comm_panel.setVisible(False)
        module_available = bool(self.bus and is_explorer)
        if hasattr(self, "install_btn"):
            self.install_btn.setVisible(module_available)
        if hasattr(self, "uninstall_btn"):
            self.uninstall_btn.setVisible(module_available)
        if not module_available and hasattr(self, "module_panel"):
            self.module_panel.setVisible(False)
        self._set_control_enabled(True)
        self._update_module_button_labels()

    def _refresh_runs_list(self) -> None:
        if not self.bus:
            self.runs_status.setText("Runtime bus unavailable.")
            return
        try:
            response = self.bus.request(
                BUS_RUNS_LIST_REQUEST,
                {},
                source="app_ui",
                timeout_ms=2000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.runs_status.setText(f"Runs list failed: {exc}")
            return
        if not response.get("ok"):
            self.runs_status.setText(f"Runs list failed: {response.get('error') or 'unknown'}")
            return
        labs = response.get("labs") or {}
        self._render_runs_list(labs)
        self.runs_status.setText("Runs list updated.")
        self._update_runs_workspace_label()

    def _render_runs_list(self, labs: Dict[str, Any]) -> None:
        self._runs_syncing = True
        self.runs_tree.clear()
        self._runs_active_lab_id = None
        for lab_id, runs in sorted(labs.items()):
            lab_item = QtWidgets.QTreeWidgetItem([lab_id, "", "", "", ""])
            lab_item.setFlags(lab_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            lab_item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
            lab_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, {"type": "lab", "lab_id": lab_id})
            self.runs_tree.addTopLevelItem(lab_item)
            for run in runs or []:
                run_id = run.get("run_id") or "run"
                created = run.get("created_at") or ""
                size_bytes = run.get("size_bytes") or 0
                size_text = f"{size_bytes/1024/1024:.2f} MB" if size_bytes else "0 MB"
                root_kind = run.get("root_kind") or "runs"
                run_item = QtWidgets.QTreeWidgetItem([run_id, created, size_text, root_kind, ""])
                run_item.setFlags(run_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                run_item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
                run_item.setData(
                    0,
                    QtCore.Qt.ItemDataRole.UserRole,
                    {
                        "type": "run",
                        "lab_id": lab_id,
                        "run_id": run_id,
                        "root_kind": root_kind,
                        "path": run.get("path"),
                        "size_bytes": size_bytes,
                    },
                )
                lab_item.addChild(run_item)

                action_widget = QtWidgets.QWidget()
                action_layout = QtWidgets.QHBoxLayout(action_widget)
                action_layout.setContentsMargins(0, 0, 0, 0)
                open_btn = QtWidgets.QPushButton("Open")
                open_btn.clicked.connect(lambda _=False, p=run.get("path"): self._open_folder(Path(p) if p else Path(".")))
                delete_btn = QtWidgets.QPushButton("Delete")
                delete_btn.clicked.connect(lambda _=False, info=run_item.data(0, QtCore.Qt.ItemDataRole.UserRole): self._delete_run(info))
                action_layout.addWidget(open_btn)
                action_layout.addWidget(delete_btn)
                self.runs_tree.setItemWidget(run_item, 4, action_widget)
        self.runs_tree.expandAll()
        self._runs_syncing = False
        self._update_runs_delete_buttons()

    def _update_runs_workspace_label(self) -> None:
        if not hasattr(self, "runs_workspace_label"):
            return
        workspace_id = "default"
        if self.bus and BUS_WORKSPACE_GET_ACTIVE_REQUEST:
            try:
                response = self.bus.request(
                    BUS_WORKSPACE_GET_ACTIVE_REQUEST,
                    {},
                    source="app_ui",
                    timeout_ms=1000,
                )
            except Exception:
                response = {"ok": False}
            if response.get("ok"):
                workspace = response.get("workspace")
                if isinstance(workspace, dict):
                    workspace_id = workspace.get("id") or workspace_id
                elif isinstance(response.get("id"), str):
                    workspace_id = response.get("id")
        self.runs_workspace_label.setText(f"Workspace: {workspace_id}")

    def _on_runs_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        if getattr(self, "_runs_syncing", False) or column != 0:
            return
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
        if data.get("type") == "lab":
            state = item.checkState(0)
            for idx in range(item.childCount()):
                child = item.child(idx)
                child.setCheckState(0, state)
        elif data.get("type") == "run":
            parent = item.parent()
            if parent is not None:
                states = [parent.child(i).checkState(0) for i in range(parent.childCount())]
                if all(s == QtCore.Qt.CheckState.Checked for s in states):
                    parent.setCheckState(0, QtCore.Qt.CheckState.Checked)
                elif all(s == QtCore.Qt.CheckState.Unchecked for s in states):
                    parent.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
                else:
                    parent.setCheckState(0, QtCore.Qt.CheckState.PartiallyChecked)
        self._set_runs_active_lab_from_item(item)
        self._update_runs_delete_buttons()

    def _on_runs_current_item_changed(
        self,
        current: Optional[QtWidgets.QTreeWidgetItem],
        previous: Optional[QtWidgets.QTreeWidgetItem],
    ) -> None:
        self._set_runs_active_lab_from_item(current)
        self._update_runs_delete_buttons()

    def _on_runs_item_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        self._set_runs_active_lab_from_item(item)
        self._update_runs_delete_buttons()

    def _set_runs_active_lab_from_item(self, item: Optional[QtWidgets.QTreeWidgetItem]) -> None:
        if item is None or getattr(self, "_runs_bulk_edit", False):
            return
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
        if data.get("type") == "lab":
            self._runs_active_lab_id = data.get("lab_id")
        elif data.get("type") == "run":
            self._runs_active_lab_id = data.get("lab_id")

    def _selected_run_items(self) -> list[Dict[str, Any]]:
        items: list[Dict[str, Any]] = []
        root = self.runs_tree.invisibleRootItem()
        for i in range(root.childCount()):
            lab_item = root.child(i)
            for j in range(lab_item.childCount()):
                run_item = lab_item.child(j)
                if run_item.checkState(0) == QtCore.Qt.CheckState.Checked:
                    info = run_item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
                    if info.get("type") == "run":
                        items.append(info)
        return items

    def _all_run_items(self) -> list[Dict[str, Any]]:
        items: list[Dict[str, Any]] = []
        root = self.runs_tree.invisibleRootItem()
        for i in range(root.childCount()):
            lab_item = root.child(i)
            for j in range(lab_item.childCount()):
                run_item = lab_item.child(j)
                info = run_item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
                if info.get("type") == "run":
                    items.append(info)
        return items

    def _current_lab_group(self) -> Optional[QtWidgets.QTreeWidgetItem]:
        if self._runs_active_lab_id:
            root = self.runs_tree.invisibleRootItem()
            for i in range(root.childCount()):
                lab_item = root.child(i)
                data = lab_item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
                if data.get("lab_id") == self._runs_active_lab_id:
                    return lab_item
        item = self.runs_tree.currentItem()
        if not item:
            return None
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
        if data.get("type") == "lab":
            return item
        if data.get("type") == "run":
            return item.parent()
        return None

    def _update_runs_delete_buttons(self) -> None:
        selected = self._selected_run_items()
        has_selected = bool(selected)
        lab_group = self._current_lab_group()
        has_lab = lab_group is not None and lab_group.childCount() > 0
        if hasattr(self, "runs_delete_selected_btn"):
            self.runs_delete_selected_btn.setEnabled(bool(self.bus and has_selected))
        if hasattr(self, "runs_delete_all_btn"):
            self.runs_delete_all_btn.setEnabled(bool(self.bus and has_lab))
        if hasattr(self, "runs_select_all_btn"):
            self.runs_select_all_btn.setEnabled(bool(self.bus and has_lab))
        if hasattr(self, "runs_clear_btn"):
            self.runs_clear_btn.setEnabled(bool(self.bus and has_lab))
        if hasattr(self, "runs_delete_all_workspace_btn"):
            self.runs_delete_all_workspace_btn.setEnabled(bool(self.bus and bool(self._all_run_items())))

    def _delete_selected_runs(self) -> None:
        if not self.bus:
            return
        items = self._selected_run_items()
        if not items:
            self.runs_status.setText("No runs selected.")
            return
        total_bytes = sum(item.get("size_bytes") or 0 for item in items)
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete selected runs",
            f"Delete {len(items)} runs (~{total_bytes/1024/1024:.2f} MB)?",
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._delete_runs_batch(items)

    def _select_all_runs_for_lab(self) -> None:
        lab_item = self._current_lab_group()
        if lab_item is None:
            self.runs_status.setText("Select a lab group first.")
            return
        self._runs_bulk_edit = True
        self._runs_syncing = True
        lab_item.setCheckState(0, QtCore.Qt.CheckState.Checked)
        for i in range(lab_item.childCount()):
            child = lab_item.child(i)
            child.setCheckState(0, QtCore.Qt.CheckState.Checked)
        self._runs_syncing = False
        self._runs_bulk_edit = False
        self._set_runs_active_lab_from_item(lab_item)
        self._update_runs_delete_buttons()

    def _clear_runs_for_lab(self) -> None:
        lab_item = self._current_lab_group()
        if lab_item is None:
            self.runs_status.setText("Select a lab group first.")
            return
        self._runs_bulk_edit = True
        self._runs_syncing = True
        lab_item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        for i in range(lab_item.childCount()):
            child = lab_item.child(i)
            child.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        self._runs_syncing = False
        self._runs_bulk_edit = False
        self._set_runs_active_lab_from_item(lab_item)
        self._update_runs_delete_buttons()

    def _delete_all_runs_for_lab(self) -> None:
        if not self.bus:
            return
        lab_item = self._current_lab_group()
        if lab_item is None:
            self.runs_status.setText("Select a lab group first.")
            return
        items = []
        for i in range(lab_item.childCount()):
            run_item = lab_item.child(i)
            info = run_item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
            if info.get("type") == "run":
                items.append(info)
        if not items:
            self.runs_status.setText("No runs in this lab.")
            return
        total_bytes = sum(item.get("size_bytes") or 0 for item in items)
        lab_id = (lab_item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}).get("lab_id") or "lab"
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete all runs",
            f"Delete all {len(items)} runs for {lab_id} (~{total_bytes/1024/1024:.2f} MB)?",
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._delete_runs_batch(items)

    def _delete_all_runs_for_workspace(self) -> None:
        if not self.bus:
            return
        items = self._all_run_items()
        if not items:
            self.runs_status.setText("No runs in this workspace.")
            return
        total_bytes = sum(item.get("size_bytes") or 0 for item in items)
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete all runs",
            f"Delete all runs in this workspace ({len(items)} runs, ~{total_bytes/1024/1024:.2f} MB)?",
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._delete_runs_batch(items)

    def _delete_runs_batch(self, items: list[Dict[str, Any]]) -> None:
        try:
            response = self.bus.request(
                BUS_RUNS_DELETE_MANY_REQUEST,
                {"items": items},
                source="app_ui",
                timeout_ms=5000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.runs_status.setText(f"Delete failed: {exc}")
            return
        ok_count = response.get("ok_count", 0)
        fail_count = response.get("fail_count", 0)
        freed = response.get("freed_bytes", 0)
        self.runs_status.setText(
            f"Deleted {ok_count} runs, failed {fail_count}, freed {freed} bytes."
        )
        self._refresh_runs_list()

    def _delete_run(self, info: Optional[Dict[str, Any]]) -> None:
        if not self.bus or not info:
            return
        lab_id = info.get("lab_id")
        run_id = info.get("run_id")
        root_kind = info.get("root_kind") or "runs"
        if not lab_id or not run_id:
            return
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete run",
            f"Delete run {run_id} for {lab_id}?",
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            response = self.bus.request(
                BUS_RUNS_DELETE_REQUEST,
                {"lab_id": lab_id, "run_id": run_id, "root_kind": root_kind},
                source="app_ui",
                timeout_ms=2000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.runs_status.setText(f"Delete failed: {exc}")
            return
        if not response.get("ok"):
            self.runs_status.setText(f"Delete failed: {response.get('error') or 'unknown'}")
            return
        self.runs_status.setText(f"Deleted run {run_id}.")
        self._refresh_runs_list()

    def _open_prune_runs_dialog(self) -> None:
        if not self.bus:
            self.runs_status.setText("Runtime bus unavailable.")
            return
        keep_default = 10
        older_default = 0
        max_mb_default = 0
        try:
            policy = self.bus.request(
                getattr(BUS_TOPICS, "CORE_POLICY_GET_REQUEST", "core.policy.get.request") if BUS_TOPICS else "core.policy.get.request",
                {},
                source="app_ui",
                timeout_ms=1000,
            )
            if policy.get("ok"):
                runs = (policy.get("policy") or {}).get("runs") or {}
                cleanup = runs.get("cleanup") or {}
                keep_default = cleanup.get("keep_last_per_lab", keep_default)
                older_default = cleanup.get("delete_older_than_days", older_default)
                max_mb_default = cleanup.get("max_total_mb", max_mb_default)
        except Exception:
            pass

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Prune runs")
        layout = QtWidgets.QFormLayout(dialog)

        keep_spin = QtWidgets.QSpinBox()
        keep_spin.setMinimum(0)
        keep_spin.setMaximum(1000)
        keep_spin.setValue(int(keep_default or 0))
        layout.addRow("Keep last per lab", keep_spin)

        older_spin = QtWidgets.QSpinBox()
        older_spin.setMinimum(0)
        older_spin.setMaximum(3650)
        older_spin.setValue(int(older_default or 0))
        layout.addRow("Delete older than days", older_spin)

        max_mb_spin = QtWidgets.QSpinBox()
        max_mb_spin.setMinimum(0)
        max_mb_spin.setMaximum(102400)
        max_mb_spin.setValue(int(max_mb_default or 0))
        layout.addRow("Max total MB (0 = ignore)", max_mb_spin)

        btn_row = QtWidgets.QHBoxLayout()
        ok_btn = QtWidgets.QPushButton("Prune")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addRow(btn_row)

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        try:
            response = self.bus.request(
                BUS_RUNS_PRUNE_REQUEST,
                {
                    "use_policy": False,
                    "keep_last_per_lab": keep_spin.value(),
                    "delete_older_than_days": older_spin.value(),
                    "max_total_mb": max_mb_spin.value(),
                },
                source="app_ui",
                timeout_ms=5000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.runs_status.setText(f"Prune failed: {exc}")
            return
        if not response.get("ok"):
            self.runs_status.setText(f"Prune failed: {response.get('error') or 'unknown'}")
            return
        summary = response.get("summary") or {}
        deleted = summary.get("deleted_count", 0)
        freed = summary.get("freed_bytes", 0)
        self.runs_status.setText(f"Pruned {deleted} runs, freed {freed} bytes.")
        self._refresh_runs_list()

    def _show_comm_report(self) -> None:
        if not self.bus:
            QtWidgets.QMessageBox.information(self, "Job History", "Runtime bus unavailable.")
            return
        self._set_status("Requesting recent jobs...")
        try:
            response = self.bus.request(
                BUS_JOBS_LIST_REQUEST,
                {"limit": 10},
                source="app_ui",
                timeout_ms=2000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._display_comm_report(f"Request failed: {exc}", ok=False)
            self._set_status(f"Job history request failed ({exc}).")
            return
        if response.get("ok"):
            jobs = response.get("jobs") or []
            lines = []
            for job in jobs[:10]:
                status = (job.get("status") or "unknown").upper()
                job_type = job.get("job_type") or "?"
                started = job.get("started_at") or "-"
                finished = job.get("finished_at") or "-"
                ok_flag = job.get("ok")
                state = "pending" if ok_flag is None else ("ok" if ok_flag else f"err:{job.get('error','')}")
                summary = job.get("result_summary")
                summary_text = f" | {summary}" if summary else ""
                lines.append(f"{status:<9} {job_type:<20} start {started} end {finished} [{state}]{summary_text}")
            text = "\n".join(lines) if lines else "No recent jobs."
            self._display_comm_report(text, ok=True)
            self._set_status("Job history updated.")
        else:
            error = response.get("error") or "unavailable"
            self._display_comm_report(f"Job history unavailable ({error}).", ok=False)
            self._set_status(f"Job history unavailable ({error}).")

    def _display_comm_report(self, text: str, ok: bool) -> None:
        color = "#2e7d32" if ok else "#b71c1c"
        self.comm_title.setStyleSheet(f"font-weight: bold; color: {color};")
        self.comm_text.setPlainText(text)
        self.comm_panel.setVisible(True)

    def _init_bus_subscriptions(self) -> None:
        if not self.bus or self._bus_subscribed:
            return
        self._subscribe_bus(BUS_REPORT_READY, self._on_report_ready_event, replay_last=True)
        self._subscribe_bus(BUS_JOB_PROGRESS, self._on_job_progress_event)
        self._subscribe_bus(BUS_JOB_COMPLETED, self._on_job_completed_event)
        self._subscribe_bus(BUS_CLEANUP_COMPLETED, self._on_cleanup_completed_event, replay_last=True)
        self._subscribe_bus(BUS_MODULE_PROGRESS, self._on_module_progress_event)
        self._subscribe_bus(BUS_MODULE_COMPLETED, self._on_module_completed_event)
        self._bus_subscribed = True

    def _subscribe_bus(
        self,
        topic: Optional[str],
        handler: Callable[[Any], None],
        *,
        replay_last: bool = False,
    ) -> None:
        if not (self.bus and topic):
            return

        def _wrapped(envelope):
            handler_name = getattr(handler, "__name__", repr(handler))
            self._bus_dispatch_bridge.envelope_dispatched.emit(handler, envelope)

        sub_id = self.bus.subscribe(topic, _wrapped, replay_last=replay_last)
        self._bus_subscriptions.append(sub_id)

    def _connect_ui_signals(self) -> None:
        if self._module_signals_connected:
            return
        self.module_progress_event.connect(self._handle_module_progress_ui)
        self.module_completed_event.connect(self._handle_module_completed_ui)
        self.cleanup_event.connect(self._handle_cleanup_completed_ui)
        self._module_signals_connected = True

    def _refresh_report(self) -> None:
        if not self.refresh_capability:
            return
        if self.bus:
            if self.pending_report_job:
                self._set_status(f"Report job already running ({self.pending_report_job}).")
                return
            self._set_status("Requesting storage report job...")
            self._start_report_job_via_bus()
            return
        if self._task_thread:
            return
        self._set_status("Refreshing storage report...")
        self._run_task(self._generate_report_direct, self._update_report)

    def _start_report_job_via_bus(self) -> None:
        if not self.bus:
            return
        try:
            response = self.bus.request(
                BUS_REPORT_REQUEST,
                {},
                source="app_ui",
                timeout_ms=2000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._set_status(f"Bus request failed ({exc}); running directly.")
            self._run_task(self._generate_report_direct, self._update_report)
            return
        if response.get("ok") and response.get("job_id"):
            self.pending_report_job = response["job_id"]
            self._set_status("Generating storage report...")
        else:
            error = response.get("error") or "unknown"
            self._set_status(f"Report request failed ({error}); running directly.")
            self._run_task(self._generate_report_direct, self._update_report)

    def _generate_report_direct(self) -> Dict[str, Any]:
        ensure_data_roots()
        registry_path = Path("data/roaming/registry.json")
        existing = load_registry(registry_path)
        discovered = discover_components()
        merged = upsert_records(existing, discovered, drop_missing=True)
        save_registry(registry_path, merged)
        report = generate_report(merged)
        text = format_report_text(report)
        return {"text": text}

    def _purge_cache(self) -> None:
        self._trigger_cleanup("cache")

    def _prune_dumps(self) -> None:
        self._trigger_cleanup("dumps")

    def _trigger_cleanup(self, kind: str) -> None:
        if not (self.bus or self.direct_available):
            QtWidgets.QMessageBox.information(self, "Cleanup", "Core Center unavailable.")
            return
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Cleanup",
            f"This will clean data/{kind}. Continue?",
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        if self.bus:
            self._start_cleanup_job(kind)
            return
        if self._task_thread:
            return
        label = "Cache purge" if kind == "cache" else "Dump pruning"
        self._set_status(f"{label} running...")
        self._set_cleanup_job_state("direct", kind, running=True)

        def job():
            ensure_data_roots()
            if kind == "cache":
                return purge_cache(Path("data/cache"))
            return prune_dumps(Path("data/dumps"), max_age_days=30, max_total_bytes=50 * 1024 * 1024)

        self._run_task(job, lambda result: self._show_cleanup_result(label, result, kind))

    def _start_cleanup_job(self, kind: str) -> None:
        if not self.bus:
            return
        print(f"[system_health] cleanup request kind={kind}")
        try:
            response = self.bus.request(
                BUS_CLEANUP_REQUEST,
                {"kind": kind},
                source="app_ui",
                timeout_ms=2000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._set_status(f"Cleanup request failed ({exc}); running directly.")
            self._trigger_cleanup_direct(kind)
            return
        if response.get("ok") and response.get("job_id"):
            job_id = response["job_id"]
            print(f"[system_health] cleanup job_id={job_id}")
            self._set_cleanup_job_state(job_id, kind, running=True)
            self._set_status(f"{kind.title()} cleanup running...")
        else:
            error = response.get("error") or "unknown"
            self._set_status(f"Cleanup request failed ({error}); running directly.")
            self._set_cleanup_job_state(None, None, running=False)
            self._trigger_cleanup_direct(kind)

    def _trigger_cleanup_direct(self, kind: str) -> None:

        if self._task_thread:
            return
        label = "Cache purge" if kind == "cache" else "Dump pruning"
        self._set_status(f"{label} running...")
        self._set_cleanup_job_state("direct", kind, running=True)

        def job():
            ensure_data_roots()
            if kind == "cache":
                return purge_cache(Path("data/cache"))
            return prune_dumps(Path("data/dumps"), max_age_days=30, max_total_bytes=50 * 1024 * 1024)

        self._run_task(job, lambda result: self._show_cleanup_result(label, result, kind))

    def _update_report(self, result: Dict) -> None:
        text = result.get("text") or "No data."
        self.report_view.setPlainText(text)
        self._set_status("Storage report updated.")
        self._pending_initial_refresh = False

    def _show_cleanup_result(self, label: str, result: Dict, kind: str) -> None:
        bytes_freed = result.get("bytes_freed", 0)
        removed = len(result.get("removed", []))
        self._set_cleanup_job_state(None, None, running=False)
        details = (
            f"Kind: {kind}\nRemoved entries: {removed}\nBytes freed: {bytes_freed}\n"
            f"Path: {self._cleanup_path_for_kind(kind)}"
        )
        self._show_completion_panel(
            title=f"{label} completed",
            details=details,
            ok=True,
            removed=result.get("removed"),
        )
        self._set_status(f"{label} finished.")
        self._refresh_report()

    def _on_report_ready_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        job_id = payload.get("job_id")
        if self.pending_report_job and job_id and job_id != self.pending_report_job:
            return
        ok = payload.get("ok", True)
        if ok:
            text = payload.get("text") or "No data."
            self.report_view.setPlainText(text)
            self._pending_initial_refresh = False
            self._set_status("Storage report updated via runtime bus.")
        else:
            error = payload.get("error") or "failed"
            self.report_view.setPlainText("")
            self._set_status(f"Storage report failed: {error}")
            QtWidgets.QMessageBox.warning(self, "System Health", f"Storage report failed: {error}")
        self.pending_report_job = None

    def _on_job_progress_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if payload.get("job_id") != self.pending_report_job:
            return
        percent = payload.get("percent")
        stage = payload.get("stage") or ""
        try:
            if percent is not None:
                value = float(percent)
                self._set_status(f"Report job {value:.0f}% - {stage}")
                return
        except (TypeError, ValueError):
            pass
        self._set_status(f"Report job update - {stage}")

    def _on_job_completed_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        job_id = payload.get("job_id")
        job_type = payload.get("job_type")
        if job_type == CORE_JOB_REPORT and job_id == self.pending_report_job:
            if payload.get("ok"):
                return
            error = payload.get("error") or "failed"
            self.pending_report_job = None
            self._set_status(f"Report job failed: {error}")
            QtWidgets.QMessageBox.warning(self, "System Health", f"Report job failed: {error}")

    def _set_cleanup_job_state(self, job_id: Optional[str], kind: Optional[str], running: bool = False) -> None:
        self.pending_cleanup_job_id = job_id
        self.pending_cleanup_kind = kind
        self._cleanup_running = bool(running)
        self._set_control_enabled(True)

    def _on_cleanup_completed_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        self.cleanup_event.emit(payload)

    def _on_module_progress_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        self.module_progress_event.emit(payload)

    def _on_module_completed_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        self.module_completed_event.emit(payload)

    def _handle_cleanup_completed_ui(self, payload: Dict[str, Any]) -> None:
        if payload is None:
            return
        job_id = payload.get("job_id")
        if job_id and self.pending_cleanup_job_id and job_id != self.pending_cleanup_job_id:
            return
        kind = payload.get("kind") or self.pending_cleanup_kind or "cleanup"
        ok = payload.get("ok", True)
        freed = payload.get("freed_bytes", 0)
        path = payload.get("path") or self._cleanup_path_for_kind(kind)
        label = f"{kind.title()} cleanup"
        self._set_cleanup_job_state(None, None, running=False)
        removed = None
        result_block = payload.get("result")
        if isinstance(result_block, dict):
            removed = result_block.get("removed")
        elif "removed" in payload:
            removed = payload.get("removed")
        if ok:
            details = f"Kind: {kind}\nBytes freed: {freed}\nPath: {path}"
            self._show_completion_panel(f"{label} completed", details, ok=True, removed=removed)
            self._set_status(f"{label} finished.")
            if self.refresh_capability and not self.pending_report_job:
                self._refresh_report()
        else:
            error = payload.get("error") or "failed"
            details = f"Kind: {kind}\nError: {error}\nPath: {path}"
            self._show_completion_panel(f"{label} failed", details, ok=False, removed=removed)
            self._set_status(f"{label} failed.")

    def _cleanup_path_for_kind(self, kind: str) -> str:
        if kind == "cache":
            return "data/cache"
        if kind == "dumps":
            return "data/dumps"
        return "data"

    def _show_completion_panel(self, title: str, details: str, ok: bool, removed=None) -> None:
        extra = ""
        if removed:
            if isinstance(removed, dict):
                removed = removed.values()
            if isinstance(removed, (list, tuple, set)):
                removed_list = list(removed)
                if removed_list:
                    trimmed = removed_list[:5]
                    extra_lines = "\n".join(f"- {item}" for item in trimmed)
                    more = len(removed_list) - len(trimmed)
                    if more > 0:
                        extra_lines += f"\n- ... (+{more} more)"
                    extra = f"\nRemoved:\n{extra_lines}"
        self.completion_title.setText(title)
        self.completion_details.setText(details + extra)
        color = "#2e7d32" if ok else "#b71c1c"
        self.completion_title.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.completion_panel.setVisible(True)
        QtCore.QTimer.singleShot(7000, lambda: self.completion_panel.setVisible(False))

    def _start_module_job(self, action: str) -> None:
        if not (self.bus and self._is_explorer):
            QtWidgets.QMessageBox.information(self, "Module", "Runtime bus unavailable.")
            return
        if self._module_job_running:
            QtWidgets.QMessageBox.information(self, "Module", "Another module job is running.")
            return
        if not self.pending_module_id:
            QtWidgets.QMessageBox.information(self, "Module", "No module id available.")
            return
        if action == "install" and self._module_installed is True:
            QtWidgets.QMessageBox.information(self, "Module", "Module already installed.")
            return
        if action == "uninstall" and self._module_installed is False:
            QtWidgets.QMessageBox.information(self, "Module", "Module already uninstalled.")
            return
        topic = BUS_MODULE_INSTALL_REQUEST if action == "install" else BUS_MODULE_UNINSTALL_REQUEST
        self._set_module_job_state(job_id=None, action=action, running=True)
        self._show_module_panel(
            f"{action.title()} starting",
            f"{action.title()} {self.pending_module_id}: requesting job...",
            running=True,
        )
        try:
            response = self.bus.request(
                topic,
                {"module_id": self.pending_module_id},
                source="app_ui",
                timeout_ms=2000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._set_module_job_state(job_id=None, action=None, running=False)
            self._show_module_panel(
                "Module job failed",
                f"{action.title()} {self._format_module_job_label()}: {exc}",
                running=False,
                ok=False,
            )
            QtWidgets.QMessageBox.warning(self, "Module", f"Request failed: {exc}")
            return
        if not response.get("ok") or not response.get("job_id"):
            self._set_module_job_state(job_id=None, action=None, running=False)
            self._show_module_panel(
                "Module job failed",
                f"{action.title()} {self._format_module_job_label()}: {response.get('error') or 'unknown'}",
                running=False,
                ok=False,
            )
            QtWidgets.QMessageBox.warning(
                self,
                "Module",
                f"Request failed: {response.get('error') or 'unknown'}",
            )
            return
        job_id = str(response["job_id"])
        self._set_module_job_state(job_id=job_id, action=action, running=True)
        self._show_module_panel(
            "Module job queued",
            f"{action.title()} {self._format_module_job_label()}: awaiting progress",
            running=True,
        )
        self._start_module_poll_timer()

    def _show_module_panel(self, title: str, details: str, running: bool, ok: Optional[bool] = None) -> None:
        color = "#0d47a1"
        if ok is True:
            color = "#2e7d32"
        elif ok is False:
            color = "#b71c1c"
        self.module_title.setText(title)
        self.module_title.setStyleSheet(f"font-weight: bold; color: {color};")
        self.module_details.setText(details)
        self.module_panel.setVisible(True)

    def _set_module_job_state(self, *, job_id: Optional[str], action: Optional[str], running: bool) -> None:
        self.pending_module_job_id = job_id
        self.pending_module_action = action
        self._module_job_running = bool(running)
        if not running:
            self._stop_module_poll_timer()
        self._set_control_enabled(True)

    def _start_module_poll_timer(self) -> None:
        if not (self.bus and self.pending_module_job_id):
            return
        self._stop_module_poll_timer()
        timer = QtCore.QTimer(self)
        timer.setInterval(800)
        timer.timeout.connect(self._poll_module_job_status)
        self._module_poll_deadline = time.monotonic() + 30.0
        self._module_poll_timer = timer
        timer.start()

    def _stop_module_poll_timer(self) -> None:
        if self._module_poll_timer:
            self._module_poll_timer.stop()
            self._module_poll_timer.deleteLater()
            self._module_poll_timer = None
        self._module_poll_deadline = 0.0

    def _poll_module_job_status(self) -> None:
        if not (self.bus and self.pending_module_job_id):
            self._stop_module_poll_timer()
            return
        if self._module_poll_deadline and time.monotonic() > self._module_poll_deadline:
            self._stop_module_poll_timer()
            self._show_module_panel(
                "Module job timeout",
                f"{(self.pending_module_action or 'Module').title()} {self.pending_module_id}: timed out waiting for completion",
                running=False,
                ok=False,
            )
            self._set_module_job_state(job_id=None, action=None, running=False)
            return
        try:
            response = self.bus.request(
                BUS_JOBS_GET_REQUEST,
                {"job_id": self.pending_module_job_id},
                source="app_ui",
                timeout_ms=800,
            )
        except Exception:
            return
        if not response.get("ok"):
            return
        job = response.get("job") or {}
        status = str(job.get("status") or "").upper()
        ok_flag = job.get("ok")
        terminal = status in ("COMPLETED", "FAILED") or ok_flag is not None
        if not terminal:
            return
        self._stop_module_poll_timer()
        payload = {
            "job_id": self.pending_module_job_id,
            "module_id": job.get("module_id") or self.pending_module_id,
            "action": self.pending_module_action,
            "ok": bool(ok_flag),
            "error": job.get("error"),
        }
        self._handle_module_completed_ui(payload)

    def _is_active_module_payload(self, payload: Dict[str, Any]) -> bool:
        if not payload:
            return False
        if not self.pending_module_job_id:
            return False
        job_id = payload.get("job_id")
        if job_id and job_id != self.pending_module_job_id:
            return False
        module_id = payload.get("module_id")
        if module_id and module_id != self.pending_module_id:
            return False
        return True

    def _format_module_job_label(self) -> str:
        job_id = self.pending_module_job_id or ""
        if job_id:
            return f"{self.pending_module_id} (job {job_id[:8]})"
        return self.pending_module_id

    def _handle_module_progress_ui(self, payload: Dict[str, Any]) -> None:
        if not self._is_active_module_payload(payload):
            return
        stage = payload.get("stage") or "Working"
        percent = payload.get("percent")
        percent_text = f"{percent:.1f}%" if isinstance(percent, (int, float)) else ""
        action = (self.pending_module_action or "module").title()
        details = f"{action} {self._format_module_job_label()}: {percent_text} {stage}".strip()
        self._show_module_panel("Module Progress", details, running=True)

    def _handle_module_completed_ui(self, payload: Dict[str, Any]) -> None:
        if not self._is_active_module_payload(payload):
            return
        self._stop_module_poll_timer()
        ok = bool(payload.get("ok"))
        action = payload.get("action") or (self.pending_module_action or "module")
        error = payload.get("error")
        summary = "OK" if ok else error or "failed"
        job_label = self._format_module_job_label()
        self._set_module_job_state(job_id=None, action=None, running=False)
        self._show_module_panel(
            "Module Result",
            f"{action.title()} {job_label}: {summary}",
            running=False,
            ok=ok,
        )
        self._refresh_inventory()

    def _unsubscribe_all(self) -> None:
        if not self.bus:
            return
        for sub_id in self._bus_subscriptions:
            self.bus.unsubscribe(sub_id)
        self._bus_subscriptions.clear()
        self._bus_subscribed = False

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._unsubscribe_all()
        super().closeEvent(event)

    def _run_task(self, job: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        if self._task_thread:
            return
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


# endregion


# === [NAV-34] Screens: ModuleManagementScreen ===============================
# region NAV-34 ModuleManagementScreen
class ModuleManagementScreen(QtWidgets.QWidget):
    # --- [NAV-34A] ctor / dependencies
    def __init__(
        self,
        on_back,
        *,
        bus=None,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
        component_policy_provider: Optional[Callable[[], "WorkspaceComponentPolicy"]] = None,
    ):
        super().__init__()
        self.on_back = on_back
        self.bus = bus
        self._bus_dispatch_bridge = _BusDispatchBridge(self)
        self._bus_subscriptions: list[str] = []
        self.modules: list[Dict[str, Any]] = []
        self._module_index: Dict[str, Dict[str, Any]] = {}
        self.pending_job_id: Optional[str] = None
        self.pending_module_id: Optional[str] = None
        self.pending_action: Optional[str] = None
        self._job_poll_timer: Optional[QtCore.QTimer] = None
        self._job_poll_job_id: Optional[str] = None
        self._job_poll_started_ms: Optional[float] = None
        self._job_poll_timeout_ms: int = 30000
        self._job_poll_timeout_ms: int = 30000
        self.component_policy_provider = component_policy_provider

        layout = QtWidgets.QVBoxLayout(self)

        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title="Module Management",
            on_back=self.on_back,
            workspace_selector=selector,
        )
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_registry)
        header.add_action_widget(refresh_btn)
        layout.addWidget(header)

        self.status_label = QtWidgets.QLabel()
        layout.addWidget(self.status_label)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Module ID", "Repo?", "Store?", "Size", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self.table, stretch=1)

        self.progress_panel = QtWidgets.QFrame()
        self.progress_panel.setVisible(False)
        self.progress_panel.setStyleSheet("QFrame { border: 1px solid #ddd; border-radius: 4px; padding: 6px; }")
        pp_layout = QtWidgets.QHBoxLayout(self.progress_panel)
        pp_layout.setContentsMargins(8, 4, 8, 4)
        self.progress_title = QtWidgets.QLabel("")
        self.progress_details = QtWidgets.QLabel("")
        self.progress_details.setWordWrap(True)
        dismiss_btn = QtWidgets.QPushButton("Dismiss")
        dismiss_btn.setFixedWidth(80)
        dismiss_btn.clicked.connect(lambda: self.progress_panel.setVisible(False))
        text_box = QtWidgets.QVBoxLayout()
        text_box.addWidget(self.progress_title)
        text_box.addWidget(self.progress_details)
        pp_layout.addLayout(text_box)
        pp_layout.addStretch()
        pp_layout.addWidget(dismiss_btn)
        layout.addWidget(self.progress_panel)

        self._init_bus_subscriptions()
        self._refresh_registry()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._unsubscribe_all()
        super().closeEvent(event)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _init_bus_subscriptions(self) -> None:
        if not self.bus or self._bus_subscriptions:
            return
        self._subscribe_bus(BUS_MODULE_PROGRESS, self._on_module_progress_event)
        self._subscribe_bus(BUS_MODULE_COMPLETED, self._on_module_completed_event)
        self._subscribe_bus(BUS_JOB_PROGRESS, self._on_job_progress_event)
        self._subscribe_bus(BUS_JOB_COMPLETED, self._on_job_completed_event)

    def _subscribe_bus(self, topic: Optional[str], handler: Callable[[Any], None]) -> None:
        if not (self.bus and topic):
            return

        def _wrapped(envelope):
            self._bus_dispatch_bridge.envelope_dispatched.emit(handler, envelope)

        sub_id = self.bus.subscribe(topic, _wrapped, replay_last=False)
        self._bus_subscriptions.append(sub_id)

    def _unsubscribe_all(self) -> None:
        if not self.bus:
            return
        for sub_id in self._bus_subscriptions:
            self.bus.unsubscribe(sub_id)
        self._bus_subscriptions.clear()

    def _refresh_registry(self) -> None:
        records = None
        reason = ""
        if self.bus:
            self._set_status("Requesting registry via runtime bus...")
            records, reason = self._fetch_registry_via_bus()
        if records is None:
            records, reason = self._fetch_registry_direct()
        if records is None:
            self.modules = []
            self._populate_table()
            self._set_status(reason or "Registry unavailable.")
            return
        self.modules = self._build_module_rows(records)
        self._populate_table()
        self._set_status(reason or "Registry loaded.")

    def _fetch_registry_via_bus(self) -> tuple[Optional[list], str]:
        if not self.bus:
            return None, "Runtime bus unavailable."
        try:
            response = self.bus.request(
                BUS_REGISTRY_REQUEST,
                {},
                source="app_ui",
                timeout_ms=2000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            return None, f"Registry request failed: {exc}"
        if response.get("ok"):
            return response.get("registry") or [], "Registry refreshed via runtime bus."
        return None, f"Registry request failed: {response.get('error') or 'unknown'}"

    def _fetch_registry_direct(self) -> tuple[Optional[list], str]:
        if not CORE_CENTER_AVAILABLE:
            return None, "Core Center unavailable."
        try:
            ensure_data_roots()
            registry_path = Path("data/roaming/registry.json")
            existing = load_registry(registry_path)
            discovered = discover_components()
            merged = upsert_records(existing, discovered)
            save_registry(registry_path, merged)
            return merged, "Registry refreshed locally."
        except Exception as exc:  # pragma: no cover - defensive
            return None, f"Registry read failed: {exc}"

    def _build_module_rows(self, records: list) -> list[Dict[str, Any]]:
        modules: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            if str(rec.get("type")) != "module":
                continue
            module_id = str(rec.get("id") or "").strip()
            if not module_id:
                continue
            entry = modules.setdefault(
                module_id,
                {
                    "id": module_id,
                    "repo": False,
                    "store": False,
                    "repo_size": None,
                    "store_size": None,
                },
            )
            source = str(rec.get("source") or "")
            size = rec.get("disk_usage_bytes")
            if source == "repo":
                entry["repo"] = True
                entry["repo_size"] = size
            elif source == "store":
                entry["store"] = True
                entry["store_size"] = size
        result = []
        for module_id, entry in modules.items():
            size = entry.get("store_size") or entry.get("repo_size") or 0
            size_text = f"{size/1024/1024:.1f} MB" if size else ""
            result.append(
                {
                    "id": module_id,
                    "repo": bool(entry.get("repo")),
                    "store": bool(entry.get("store")),
                    "size": size,
                    "size_text": size_text,
                }
            )
        return sorted(result, key=lambda x: x["id"])

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self.modules))
        self._module_index = {m.get("id"): m for m in self.modules if m.get("id")}
        for row, mod in enumerate(self.modules):
            mod_id = mod.get("id") or ""
            repo = "Yes" if mod.get("repo") else "No"
            store = "Yes" if mod.get("store") else "No"
            size_text = mod.get("size_text") or ""

            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(mod_id))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(repo))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(store))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(size_text))

            actions_widget = QtWidgets.QWidget()
            actions_layout = QtWidgets.QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            install_btn = QtWidgets.QPushButton("Install")
            uninstall_btn = QtWidgets.QPushButton("Uninstall")
            install_btn.setEnabled(bool(mod.get("repo")) and not mod.get("store"))
            uninstall_btn.setEnabled(bool(mod.get("store")))
            install_btn.clicked.connect(lambda _=False, m=mod_id: self._start_job("install", m))
            uninstall_btn.clicked.connect(lambda _=False, m=mod_id: self._start_job("uninstall", m))
            actions_layout.addWidget(install_btn)
            actions_layout.addWidget(uninstall_btn)
            self.table.setCellWidget(row, 4, actions_widget)

        self.table.resizeRowsToContents()

    def _start_job(self, action: str, module_id: str) -> None:
        if not self.bus:
            QtWidgets.QMessageBox.information(self, "Module", "Runtime bus unavailable.")
            return
        if self.pending_job_id:
            QtWidgets.QMessageBox.information(self, "Module", "Another module job is running.")
            return
        entry = self._module_index.get(module_id, {})
        if action == "install" and entry.get("store"):
            QtWidgets.QMessageBox.information(self, "Module", "Module already installed.")
            return
        if action == "uninstall" and not entry.get("store"):
            QtWidgets.QMessageBox.information(self, "Module", "Module already uninstalled.")
            return
        topic = BUS_MODULE_INSTALL_REQUEST if action == "install" else BUS_MODULE_UNINSTALL_REQUEST
        self._set_job_state(job_id=None, module_id=module_id, action=action, running=True)
        self._show_progress_panel(
            f"{action.title()} requested",
            f"{action.title()} {module_id}: requesting job...",
            running=True,
        )
        try:
            response = self.bus.request(
                topic,
                {"module_id": module_id},
                source="app_ui",
                timeout_ms=2000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._set_job_state(job_id=None, module_id=None, action=None, running=False)
            self._show_progress_panel(
                "Module job failed",
                f"{action.title()} {module_id}: {exc}",
                running=False,
                ok=False,
            )
            QtWidgets.QMessageBox.warning(self, "Module", f"Request failed: {exc}")
            return
        if not response.get("ok") or not response.get("job_id"):
            self._set_job_state(job_id=None, module_id=None, action=None, running=False)
            self._show_progress_panel(
                "Module job failed",
                f"{action.title()} {module_id}: {response.get('error') or 'unknown'}",
                running=False,
                ok=False,
            )
            QtWidgets.QMessageBox.warning(
                self,
                "Module",
                f"Request failed: {response.get('error') or 'unknown'}",
            )
            return
        job_id = str(response["job_id"])
        self._set_job_state(job_id=job_id, module_id=module_id, action=action, running=True)
        self._show_progress_panel(
            "Module job queued",
            f"{action.title()} {module_id}: awaiting progress (job {job_id[:8]})",
            running=True,
        )
        self._start_job_poll_timer()

    def _is_active_payload(self, payload: Dict[str, Any]) -> bool:
        if not payload:
            return False
        job_id = payload.get("job_id")
        module_id = payload.get("module_id")
        if self.pending_job_id and job_id and job_id != self.pending_job_id:
            return False
        if self.pending_module_id and module_id and module_id != self.pending_module_id:
            return False
        if not (self.pending_job_id or self.pending_module_id):
            return False
        return True

    def _on_module_progress_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if not self._is_active_payload(payload):
            return
        self._handle_progress_payload(payload)

    def _on_job_progress_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if payload.get("job_type") not in (CORE_JOB_MODULE_INSTALL, CORE_JOB_MODULE_UNINSTALL):
            return
        if not self._is_active_payload(payload):
            return
        self._handle_progress_payload(payload)

    def _handle_progress_payload(self, payload: Dict[str, Any]) -> None:
        stage = payload.get("stage") or "Working"
        percent = payload.get("percent")
        percent_text = f"{percent:.1f}%" if isinstance(percent, (int, float)) else ""
        module_id = payload.get("module_id") or self.pending_module_id or "module"
        action = (self.pending_action or "module").title()
        details = f"{action} {module_id}: {percent_text} {stage}".strip()
        self._show_progress_panel("Module Progress", details, running=True)
        self._set_status(details)

    def _on_module_completed_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if not self._is_active_payload(payload):
            return
        self._stop_job_poll_timer()
        ok = bool(payload.get("ok"))
        error = payload.get("error")
        module_id = payload.get("module_id") or self.pending_module_id or "module"
        action = payload.get("action") or self.pending_action or "module"
        summary = "OK" if ok else error or "failed"
        self._show_progress_panel(
            "Module Result",
            f"{action.title()} {module_id}: {summary}",
            running=False,
            ok=ok,
        )
        self._set_status(f"{action.title()} {module_id}: {summary}")
        self._set_job_state(job_id=None, module_id=None, action=None, running=False)
        self._refresh_registry()

    def _on_job_completed_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if payload.get("job_type") not in (CORE_JOB_MODULE_INSTALL, CORE_JOB_MODULE_UNINSTALL):
            return
        if not self._is_active_payload(payload):
            return
        self._stop_job_poll_timer()
        ok = bool(payload.get("ok"))
        error = payload.get("error")
        module_id = self.pending_module_id or "module"
        action = self.pending_action or "module"
        summary = "OK" if ok else error or "failed"
        self._show_progress_panel(
            "Module Result",
            f"{action.title()} {module_id}: {summary}",
            running=False,
            ok=ok,
        )
        self._set_status(f"{action.title()} {module_id}: {summary}")
        self._set_job_state(job_id=None, module_id=None, action=None, running=False)
        self._refresh_registry()

    def _set_job_state(self, *, job_id: Optional[str], module_id: Optional[str], action: Optional[str], running: bool) -> None:
        self.pending_job_id = job_id
        self.pending_module_id = module_id
        self.pending_action = action if running else None
        if not running:
            self._stop_job_poll_timer()

    def _show_progress_panel(self, title: str, details: str, running: bool, ok: Optional[bool] = None) -> None:
        color = "#0d47a1"
        if ok is True:
            color = "#2e7d32"
        elif ok is False:
            color = "#b71c1c"
        self.progress_title.setText(title)
        self.progress_title.setStyleSheet(f"font-weight: bold; color: {color};")
        self.progress_details.setText(details)
        self.progress_panel.setVisible(True)

    def _start_job_poll_timer(self) -> None:
        job_id = self.pending_job_id
        if not (self.bus and job_id):
            return
        self._stop_job_poll_timer()
        self._job_poll_job_id = job_id
        self._job_poll_started_ms = time.monotonic() * 1000
        timer = QtCore.QTimer(self)
        timer.setInterval(800)
        timer.timeout.connect(self._poll_job_status)
        self._job_poll_timer = timer
        timer.start()

    def _stop_job_poll_timer(self) -> None:
        timer = getattr(self, "_job_poll_timer", None)
        if timer:
            timer.stop()
            timer.deleteLater()
        self._job_poll_timer = None
        self._job_poll_job_id = None
        self._job_poll_started_ms = None

    def _poll_job_status(self) -> None:
        job_id = self._job_poll_job_id or self.pending_job_id
        if not (self.bus and job_id):
            self._stop_job_poll_timer()
            return
        if self._job_poll_started_ms is not None and self._job_poll_timeout_ms:
            elapsed_ms = (time.monotonic() * 1000) - self._job_poll_started_ms
            if elapsed_ms > self._job_poll_timeout_ms:
                self._stop_job_poll_timer()
                self._show_progress_panel(
                    "Module job timeout",
                    f"{(self.pending_action or 'Module').title()} {self.pending_module_id or 'module'}: timed out waiting for completion",
                    running=False,
                    ok=False,
                )
                self._set_job_state(job_id=None, module_id=None, action=None, running=False)
                return
        try:
            response = self.bus.request(
                BUS_JOBS_GET_REQUEST,
                {"job_id": job_id},
                source="app_ui",
                timeout_ms=800,
            )
        except Exception:
            return
        if not response.get("ok"):
            return
        job = response.get("job") or {}
        status = str(job.get("status") or "").upper()
        ok_flag = job.get("ok")
        terminal = status in ("COMPLETED", "FAILED") or ok_flag is not None
        if not terminal:
            return
        self._stop_job_poll_timer()
        payload = {
            "job_id": job_id,
            "job_type": job.get("job_type"),
            "ok": ok_flag,
            "error": job.get("error"),
        }
        self._on_job_completed_event(SimpleNamespace(payload=payload))
# endregion


def _format_pack_label(pack: Dict[str, Any]) -> str:
    pack_id = pack.get("pack_id") or "unknown"
    name = pack.get("display_name") or pack_id
    version = pack.get("version") or "?"
    return f"{name} ({pack_id}) v{version}"


def _selected_pack_id(list_widget: QtWidgets.QListWidget) -> Optional[str]:
    item = list_widget.currentItem()
    if not item:
        return None
    value = item.data(QtCore.Qt.ItemDataRole.UserRole)
    return value if isinstance(value, str) else None


def _run_pack_job(action: str, pack_id: str) -> Dict[str, Any]:
    repo_root = Path("component_repo/component_v1/packs")
    store_root = Path("component_store/component_v1/packs")
    repo_pack = repo_root / pack_id
    store_pack = store_root / pack_id

    log_path = r"c:\Users\ahmed\Downloads\PhysicsLab\.cursor\debug.log"

    def _agent_log(message: str, data: Dict[str, Any], hypothesis_id: str) -> None:
        # region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as _fh:
                _fh.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "baseline",
                            "hypothesisId": hypothesis_id,
                            "location": "app_ui/main.py:_run_pack_job",
                            "message": message,
                            "data": data,
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        # endregion

    _agent_log(
        "pack_job_start",
        {
            "action": action,
            "pack_id": pack_id,
            "repo_pack": str(repo_pack),
            "store_pack": str(store_pack),
            "repo_exists": repo_pack.exists(),
            "store_exists": store_pack.exists(),
        },
        hypothesis_id="H1",
    )

    repo_root.mkdir(parents=True, exist_ok=True)
    store_root.mkdir(parents=True, exist_ok=True)

    try:
        if action == "install":
            if not repo_pack.exists():
                _agent_log(
                    "pack_job_missing_repo",
                    {"action": action, "pack_id": pack_id, "repo_pack": str(repo_pack)},
                    hypothesis_id="H1",
                )
                return {"ok": False, "message": f"Pack '{pack_id}' not found in repo."}
            if store_pack.exists():
                safe_rmtree(store_pack)
            safe_copytree(repo_pack, store_pack)
            result = {"ok": True, "message": f"Installed {pack_id}."}
            _agent_log(
                "pack_job_complete",
                {"action": action, "pack_id": pack_id, "ok": True, "store_pack": str(store_pack)},
                hypothesis_id="H1",
            )
            return result
        if action == "uninstall":
            if not store_pack.exists():
                _agent_log(
                    "pack_job_missing_store",
                    {"action": action, "pack_id": pack_id, "store_pack": str(store_pack)},
                    hypothesis_id="H1",
                )
                return {"ok": False, "message": f"Pack '{pack_id}' not installed."}
            safe_rmtree(store_pack)
            result = {"ok": True, "message": f"Uninstalled {pack_id}."}
            _agent_log(
                "pack_job_complete",
                {"action": action, "pack_id": pack_id, "ok": True, "store_pack": str(store_pack)},
                hypothesis_id="H1",
            )
            return result
        return {"ok": False, "message": "Unknown action."}
    except Exception as exc:
        result = {
            "ok": False,
            "message": (
                f"{action} failed: pack={pack_id} src={repo_pack} "
                f"dst={store_pack} err={exc!r}"
            ),
        }
        _agent_log(
            "pack_job_error",
            {"action": action, "pack_id": pack_id, "error": str(exc)},
            hypothesis_id="H1",
        )
        return result


# endregion


# === [NAV-35] Screens: ComponentManagementScreen ============================
# region NAV-35 ComponentManagementScreen
class ComponentManagementScreen(QtWidgets.QWidget):
    def __init__(
        self,
        on_back,
        bus=None,
        *,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
        on_packs_changed: Optional[Callable[[], None]] = None,
    ):
        super().__init__()
        self.on_back = on_back
        self.bus = bus
        self._job_thread: Optional[QtCore.QThread] = None
        self._bus_dispatch_bridge = _BusDispatchBridge(self)
        self._bus_subscriptions: list[str] = []
        self.pending_job_id: Optional[str] = None
        self.pending_pack_id: Optional[str] = None
        self.pending_action: Optional[str] = None
        self._job_poll_timer: Optional[QtCore.QTimer] = None
        self._job_poll_deadline: float = 0.0
        self._installed_pack_ids: set[str] = set()
        self.on_packs_changed = on_packs_changed
        self._bus_available = bool(self.bus)

        layout = QtWidgets.QVBoxLayout(self)
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title="Component Management",
            on_back=self.on_back,
            workspace_selector=selector,
        )
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        header.add_action_widget(refresh_btn)
        layout.addWidget(header)

        self.banner = QtWidgets.QLabel("")
        self.banner.setVisible(False)
        self.banner.setStyleSheet("color: #b71c1c; font-weight: bold;")
        layout.addWidget(self.banner)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(splitter, stretch=1)

        repo_panel = QtWidgets.QWidget()
        repo_layout = QtWidgets.QVBoxLayout(repo_panel)
        repo_layout.addWidget(QtWidgets.QLabel("Available (Repo)"))
        self.repo_list = QtWidgets.QListWidget()
        repo_layout.addWidget(self.repo_list, stretch=1)
        repo_btn_row = QtWidgets.QHBoxLayout()
        self.install_btn = QtWidgets.QPushButton("Install")
        self.install_btn.clicked.connect(self._install_selected)
        repo_btn_row.addWidget(self.install_btn)
        repo_layout.addLayout(repo_btn_row)
        splitter.addWidget(repo_panel)

        store_panel = QtWidgets.QWidget()
        store_layout = QtWidgets.QVBoxLayout(store_panel)
        store_layout.addWidget(QtWidgets.QLabel("Installed (Store)"))
        self.store_list = QtWidgets.QListWidget()
        store_layout.addWidget(self.store_list, stretch=1)
        store_btn_row = QtWidgets.QHBoxLayout()
        self.uninstall_btn = QtWidgets.QPushButton("Uninstall")
        self.uninstall_btn.clicked.connect(self._uninstall_selected)
        store_btn_row.addWidget(self.uninstall_btn)
        store_layout.addLayout(store_btn_row)
        splitter.addWidget(store_panel)

        self.progress_panel = QtWidgets.QFrame()
        self.progress_panel.setVisible(False)
        self.progress_panel.setStyleSheet("QFrame { border: 1px solid #ddd; border-radius: 4px; padding: 6px; }")
        pp_layout = QtWidgets.QHBoxLayout(self.progress_panel)
        text_box = QtWidgets.QVBoxLayout()
        self.progress_title = QtWidgets.QLabel("")
        self.progress_details = QtWidgets.QLabel("")
        self.progress_details.setWordWrap(True)
        dismiss_btn = QtWidgets.QPushButton("Dismiss")
        dismiss_btn.clicked.connect(lambda: self.progress_panel.setVisible(False))
        text_box.addWidget(self.progress_title)
        text_box.addWidget(self.progress_details)
        pp_layout.addLayout(text_box, stretch=1)
        pp_layout.addWidget(dismiss_btn)
        layout.addWidget(self.progress_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)

        self._init_bus_subscriptions()
        self.refresh()

    def refresh(self) -> None:
        self.repo_list.clear()
        self.store_list.clear()
        if not self.bus:
            self._bus_available = False
            self._set_banner("Management Core unavailable (runtime bus not connected).")
            self.install_btn.setEnabled(False)
            self.uninstall_btn.setEnabled(False)
            return
        self._bus_available = True
        self._set_banner("")
        repo_packs = component_packs.list_repo_packs()
        store_packs, inv_ok = self._load_installed_packs()
        if not inv_ok:
            self._set_banner("Management Core inventory unavailable; pack actions disabled.")
            self.install_btn.setEnabled(False)
            self.uninstall_btn.setEnabled(False)
        else:
            self._set_banner("")
        self._installed_pack_ids = {p.get("pack_id") or p.get("id") for p in store_packs if p.get("pack_id") or p.get("id")}
        for pack in repo_packs:
            label = _format_pack_label(pack)
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, pack.get("pack_id"))
            self.repo_list.addItem(item)
        for pack in store_packs:
            pack_id = pack.get("pack_id") or pack.get("id")
            label = _format_pack_label(
                {
                    "pack_id": pack_id,
                    "display_name": pack.get("display_name") or pack.get("name") or pack_id,
                    "version": pack.get("version"),
                }
            )
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, pack_id)
            self.store_list.addItem(item)
        if inv_ok and not self.pending_job_id:
            self.install_btn.setEnabled(True)
            self.uninstall_btn.setEnabled(True)

    def _install_selected(self) -> None:
        pack_id = _selected_pack_id(self.repo_list)
        if not pack_id:
            self._show_progress("Install", "Select a pack to install.", running=False, ok=False)
            return
        if pack_id in self._installed_pack_ids:
            self._show_progress("Install", f"{pack_id} already installed.", running=False, ok=False)
            return
        self._run_job("install", pack_id)

    def _uninstall_selected(self) -> None:
        pack_id = _selected_pack_id(self.store_list)
        if not pack_id:
            self._show_progress("Uninstall", "Select a pack to uninstall.", running=False, ok=False)
            return
        if pack_id not in self._installed_pack_ids:
            self._show_progress("Uninstall", f"{pack_id} not installed.", running=False, ok=False)
            return
        self._run_job("uninstall", pack_id)

    def _run_job(self, action: str, pack_id: str) -> None:
        if not self.bus:
            self._show_progress("Pack Job", "Runtime bus unavailable.", running=False, ok=False)
            return
        if self.pending_job_id:
            self._show_progress("Pack Job", "Another pack job is running.", running=False, ok=False)
            return
        topic = BUS_COMPONENT_PACK_INSTALL_REQUEST if action == "install" else BUS_COMPONENT_PACK_UNINSTALL_REQUEST
        self._set_job_state(job_id=None, pack_id=pack_id, action=action, running=True)
        self._show_progress(f"{action.title()} {pack_id}", "Starting job...", running=True)
        try:
            response = self.bus.request(
                topic,
                {"pack_id": pack_id},
                source="app_ui",
                timeout_ms=2000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._set_job_state(job_id=None, pack_id=None, action=None, running=False)
            self._show_progress("Pack Job", f"{action.title()} failed: {exc}", running=False, ok=False)
            return
        if not response.get("ok") or not response.get("job_id"):
            self._set_job_state(job_id=None, pack_id=None, action=None, running=False)
            self._show_progress(
                "Pack Job",
                f"{action.title()} failed: {response.get('error') or 'unknown'}",
                running=False,
                ok=False,
            )
            return
        job_id = str(response["job_id"])
        self._set_job_state(job_id=job_id, pack_id=pack_id, action=action, running=True)
        self._show_progress(
            "Pack Job",
            f"{action.title()} {pack_id}: awaiting completion (job {job_id[:8]})",
            running=True,
        )
        self._start_job_poll_timer()

    def _on_job_finished(self, result: Dict[str, Any]) -> None:
        self._job_thread = None
        self.install_btn.setEnabled(True)
        self.uninstall_btn.setEnabled(True)
        ok = bool(result.get("ok"))
        details = result.get("message") or ""
        self._show_progress("Pack Job", details, running=False, ok=ok)
        self._refresh_registry()
        self.refresh()

    def _on_job_error(self, error: str) -> None:
        self._job_thread = None
        self.install_btn.setEnabled(True)
        self.uninstall_btn.setEnabled(True)
        self._show_progress("Pack Job", error, running=False, ok=False)

    def _refresh_registry(self) -> None:
        if component_registry is None or component_packs is None:
            return
        try:
            component_packs.load_installed_packs()
        except Exception:
            pass

    def _show_progress(self, title: str, details: str, running: bool, ok: Optional[bool] = None) -> None:
        color = "#7a7a7a"
        if ok is True:
            color = "#2e7d32"
        elif ok is False:
            color = "#b71c1c"
        if running:
            details = f"{details} (running)"
        self.progress_title.setText(title)
        self.progress_title.setStyleSheet(f"font-weight: bold; color: {color};")
        self.progress_details.setText(details)
        self.progress_panel.setVisible(True)

    def _load_installed_packs(self) -> tuple[list[Dict[str, Any]], bool]:
        if self.bus:
            try:
                response = self.bus.request(
                    BUS_INVENTORY_REQUEST,
                    {},
                    source="app_ui",
                    timeout_ms=1500,
                )
                if response.get("ok"):
                    inventory = response.get("inventory") or {}
                    packs = inventory.get("component_packs") or []
                    return [
                        {
                            "pack_id": pack.get("id") or pack.get("pack_id"),
                            "version": pack.get("version"),
                            "display_name": pack.get("display_name") or pack.get("name"),
                        }
                        for pack in packs
                        if pack.get("id") or pack.get("pack_id")
                    ], True
            except Exception:
                return [], False
            return [], False
        if component_packs is None:
            return [], False
        return component_packs.list_installed_packs(), True

    def _init_bus_subscriptions(self) -> None:
        if not self.bus or self._bus_subscriptions:
            return
        self._subscribe_bus(BUS_JOB_PROGRESS, self._on_job_progress_event, replay_last=False)
        self._subscribe_bus(BUS_JOB_COMPLETED, self._on_job_completed_event, replay_last=True)

    def _subscribe_bus(self, topic: Optional[str], handler: Callable[[Any], None], replay_last: bool = False) -> None:
        if not (self.bus and topic):
            return

        def _wrapped(envelope):
            self._bus_dispatch_bridge.envelope_dispatched.emit(handler, envelope)

        sub_id = self.bus.subscribe(topic, _wrapped, replay_last=replay_last)
        self._bus_subscriptions.append(sub_id)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.bus:
            for sub_id in self._bus_subscriptions:
                self.bus.unsubscribe(sub_id)
            self._bus_subscriptions.clear()
        super().closeEvent(event)

    def _set_job_state(
        self,
        *,
        job_id: Optional[str],
        pack_id: Optional[str],
        action: Optional[str],
        running: bool,
    ) -> None:
        self.pending_job_id = job_id
        self.pending_pack_id = pack_id
        self.pending_action = action if running else None
        self.install_btn.setEnabled(not running)
        self.uninstall_btn.setEnabled(not running)
        if not running:
            self._stop_job_poll_timer()

    def _start_job_poll_timer(self) -> None:
        if not (self.bus and self.pending_job_id):
            return
        self._stop_job_poll_timer()
        timer = QtCore.QTimer(self)
        timer.setInterval(800)
        timer.timeout.connect(self._poll_job_status)
        self._job_poll_deadline = time.monotonic() + 45.0
        self._job_poll_timer = timer
        timer.start()

    def _stop_job_poll_timer(self) -> None:
        if self._job_poll_timer:
            self._job_poll_timer.stop()
            self._job_poll_timer.deleteLater()
            self._job_poll_timer = None
        self._job_poll_deadline = 0.0

    def _poll_job_status(self) -> None:
        if not (self.bus and self.pending_job_id):
            self._stop_job_poll_timer()
            return
        if self._job_poll_deadline and time.monotonic() > self._job_poll_deadline:
            self._stop_job_poll_timer()
            self._show_progress(
                "Pack Job Timeout",
                f"{(self.pending_action or 'Pack').title()} {self.pending_pack_id or 'pack'}: timed out",
                running=False,
                ok=False,
            )
            self._set_job_state(job_id=None, pack_id=None, action=None, running=False)
            return
        try:
            response = self.bus.request(
                BUS_JOBS_GET_REQUEST,
                {"job_id": self.pending_job_id},
                source="app_ui",
                timeout_ms=800,
            )
        except Exception as exc:
            self._stop_job_poll_timer()
            self._show_progress(
                "Pack Job",
                f"Job status failed: {exc}",
                running=False,
                ok=False,
            )
            self._set_job_state(job_id=None, pack_id=None, action=None, running=False)
            return
        if not response.get("ok"):
            self._stop_job_poll_timer()
            self._show_progress(
                "Pack Job",
                f"Job status failed: {response.get('error') or 'unknown'}",
                running=False,
                ok=False,
            )
            self._set_job_state(job_id=None, pack_id=None, action=None, running=False)
            return
        job = response.get("job") or {}
        status = str(job.get("status") or "").upper()
        ok_flag = job.get("ok")
        terminal = status in ("COMPLETED", "FAILED") or ok_flag is not None
        if not terminal:
            return
        payload = {
            "job_id": self.pending_job_id,
            "job_type": job.get("job_type"),
            "ok": ok_flag,
            "error": job.get("error"),
        }
        self._on_job_completed_event(SimpleNamespace(payload=payload))

    def _on_job_progress_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if payload.get("job_id") != self.pending_job_id:
            return
        percent = payload.get("percent")
        stage = payload.get("stage") or "Working"
        percent_text = f"{percent:.1f}%" if isinstance(percent, (int, float)) else ""
        label = self.pending_pack_id or "pack"
        self._show_progress(
            "Pack Progress",
            f"{(self.pending_action or 'pack').title()} {label}: {percent_text} {stage}".strip(),
            running=True,
        )

    def _on_job_completed_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if payload.get("job_id") != self.pending_job_id:
            return
        ok = bool(payload.get("ok"))
        error = payload.get("error") or "failed"
        label = self.pending_pack_id or "pack"
        action = self.pending_action or "pack"
        summary = "OK" if ok else error
        self._show_progress(
            "Pack Result",
            f"{action.title()} {label}: {summary}",
            running=False,
            ok=ok,
        )
        self._set_job_state(job_id=None, pack_id=None, action=None, running=False)
        self._refresh_registry()
        self.refresh()
        if self.on_packs_changed:
            try:
                self.on_packs_changed()
            except Exception:
                pass

    def _set_banner(self, text: str) -> None:
        if not text:
            self.banner.setVisible(False)
            self.banner.setText("")
        else:
            self.banner.setText(text)
            self.banner.setVisible(True)


# endregion


# === [NAV-33] Screens: WorkspaceManagementScreen ============================
# region NAV-33 WorkspaceManagementScreen
# (moved to app_ui/screens/workspace_management.py)
# endregion


# === [NAV-01] Small utilities ================================================
# region NAV-01 StatusPill
class StatusPill(QtWidgets.QLabel):
    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setVisible(False)

    def set_status(self, status: str) -> None:
        status = (status or "").upper()
        bg = "#eeeeee"
        fg = "#333333"
        if status == STATUS_READY:
            bg, fg = "#e8f5e9", "#2e7d32"
        elif status == STATUS_NOT_INSTALLED:
            bg, fg = "#fff8e1", "#f57c00"
        elif status == STATUS_UNAVAILABLE:
            bg, fg = "#ffebee", "#b71c1c"
        self.setText(status or "UNKNOWN")
        self.setStyleSheet(
            f"padding: 2px 8px; border-radius: 10px; background: {bg}; color: {fg};"
        )
        self.setVisible(True)


# endregion


# === [NAV-36] Screens: ContentManagementScreen ==============================
# region NAV-36 ContentManagementScreen
class ContentManagementScreen(QtWidgets.QWidget):
    # --- [NAV-36A] ctor / dependencies
    def __init__(
        self,
        adapter: "ContentSystemAdapter",
        on_back,
        on_open_part=None,
        *,
        bus=None,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
        component_policy_provider: Optional[Callable[[], "WorkspaceComponentPolicy"]] = None,
    ):
        super().__init__()
        self.adapter = adapter
        self.on_back = on_back
        self.on_open_part = on_open_part
        self.bus = bus
        self._bus_dispatch_bridge = _BusDispatchBridge(self)
        self._bus_subscriptions: list[str] = []
        self.current_selection: Optional[Dict[str, Any]] = None
        self.install_thread: Optional[QtCore.QThread] = None
        self.progress_dialog: Optional[QtWidgets.QProgressDialog] = None
        self.pending_job_id: Optional[str] = None
        self.pending_module_id: Optional[str] = None
        self.pending_action: Optional[str] = None
        self._selected_module_status: Optional[str] = None
        self._job_poll_timer: Optional[QtCore.QTimer] = None
        self._job_poll_job_id: Optional[str] = None
        self._job_poll_started_ms: Optional[float] = None
        self._job_poll_timeout_ms: int = 30000
        self.component_policy_provider = component_policy_provider

        layout = QtWidgets.QVBoxLayout(self)

        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title="Content Management",
            on_back=self.on_back,
            workspace_selector=selector,
        )
        layout.addWidget(header)

        toolbar = QtWidgets.QHBoxLayout()
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_tree)
        toolbar.addWidget(refresh_btn)
        toolbar.addSpacing(12)
        toolbar.addWidget(QtWidgets.QLabel("Show:"))
        self.filter_combo = QtWidgets.QComboBox()
        self.filter_combo.addItems(["All", "Installed only", "Not installed"])
        self.filter_combo.currentIndexChanged.connect(self._apply_filter)
        toolbar.addWidget(self.filter_combo)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.status_label = QtWidgets.QLabel()
        layout.addWidget(self.status_label)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, stretch=1)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Item", "Status"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnCount(2)
        header_view = self.tree.header()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        splitter.addWidget(self.tree)

        detail_widget = QtWidgets.QWidget()
        detail_layout = QtWidgets.QVBoxLayout(detail_widget)
        self.detail_title = QtWidgets.QLabel("Select an item to view details.")
        self.detail_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.detail_status_pill = StatusPill()
        self.detail_meta = QtWidgets.QLabel("")
        self.detail_meta.setStyleSheet("color: #555;")
        self.detail_action = QtWidgets.QLabel("")
        self.detail_action.setStyleSheet("color: #777;")
        self.detail_hint = QtWidgets.QLabel("")
        self.detail_hint.setStyleSheet("color: #777;")
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_status_pill)
        detail_layout.addWidget(self.detail_meta)
        detail_layout.addWidget(self.detail_action)
        detail_layout.addWidget(self.detail_hint)

        btn_row = QtWidgets.QHBoxLayout()
        self.install_part_btn = QtWidgets.QPushButton("Install part")
        self.install_part_btn.clicked.connect(self._install_part)
        self.install_part_btn.setVisible(False)
        self.install_module_btn = QtWidgets.QPushButton("Install module")
        self.install_module_btn.clicked.connect(lambda: self._start_module_job("install"))
        self.uninstall_module_btn = QtWidgets.QPushButton("Uninstall module")
        self.uninstall_module_btn.clicked.connect(lambda: self._start_module_job("uninstall"))
        btn_row.addWidget(self.install_part_btn)
        btn_row.addWidget(self.install_module_btn)
        btn_row.addWidget(self.uninstall_module_btn)
        btn_row.addStretch()
        detail_layout.addLayout(btn_row)

        self.progress_panel = QtWidgets.QFrame()
        self.progress_panel.setVisible(False)
        self.progress_panel.setStyleSheet("QFrame { border: 1px solid #ddd; border-radius: 4px; padding: 6px; }")
        cm_pp_layout = QtWidgets.QHBoxLayout(self.progress_panel)
        cm_pp_layout.setContentsMargins(8, 4, 8, 4)
        self.progress_title = QtWidgets.QLabel("")
        self.progress_details = QtWidgets.QLabel("")
        self.progress_details.setWordWrap(True)
        cm_dismiss = QtWidgets.QPushButton("Dismiss")
        cm_dismiss.setFixedWidth(80)
        cm_dismiss.clicked.connect(lambda: self.progress_panel.setVisible(False))
        cm_text = QtWidgets.QVBoxLayout()
        cm_text.addWidget(self.progress_title)
        cm_text.addWidget(self.progress_details)
        cm_pp_layout.addLayout(cm_text)
        cm_pp_layout.addStretch()
        cm_pp_layout.addWidget(cm_dismiss)
        detail_layout.addWidget(self.progress_panel)

        splitter.addWidget(detail_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        self._init_bus_subscriptions()
        self._tree_data: Optional[Dict[str, Any]] = None
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

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._unsubscribe_all()
        super().closeEvent(event)

    def _init_bus_subscriptions(self) -> None:
        if not self.bus or self._bus_subscriptions:
            return
        self._subscribe_bus(BUS_MODULE_PROGRESS, self._on_module_progress_event)
        self._subscribe_bus(BUS_MODULE_COMPLETED, self._on_module_completed_event)
        self._subscribe_bus(BUS_JOB_PROGRESS, self._on_job_progress_event)
        self._subscribe_bus(BUS_JOB_COMPLETED, self._on_job_completed_event)

    def _subscribe_bus(self, topic: Optional[str], handler: Callable[[Any], None]) -> None:
        if not (self.bus and topic):
            return

        def _wrapped(envelope):
            self._bus_dispatch_bridge.envelope_dispatched.emit(handler, envelope)

        sub_id = self.bus.subscribe(topic, _wrapped, replay_last=False)
        self._bus_subscriptions.append(sub_id)

    def _unsubscribe_all(self) -> None:
        if not self.bus:
            return
        for sub_id in self._bus_subscriptions:
            self.bus.unsubscribe(sub_id)
        self._bus_subscriptions.clear()

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def refresh_tree(self) -> None:
        data = self.adapter.list_tree()
        self._tree_data = data
        self._build_tree()
        self._set_status("Content tree refreshed.")

    def _build_tree(self) -> None:
        self.tree.clear()
        data = self._tree_data or {}
        module = data.get("module")
        if not module:
            self._set_status(data.get("reason") or "Module data unavailable.")
            self._clear_details()
            return

        filter_mode = self.filter_combo.currentText()
        disabled_parts: List[str] = []

        def part_allowed(status: str) -> bool:
            if filter_mode == "Installed only":
                return status == STATUS_READY
            if filter_mode == "Not installed":
                return status != STATUS_READY
            return True

        module_status = data.get("status", "")
        module_item = QtWidgets.QTreeWidgetItem(
            [self._display_name(module.get("title"), module.get("module_id"), "Module"), module_status]
        )
        module_item.setData(
            0,
            QtCore.Qt.ItemDataRole.UserRole,
            {"type": "module", "module_id": module.get("module_id"), "status": module_status},
        )
        added_any = False
        for section in module.get("sections", []):
            sec_item = QtWidgets.QTreeWidgetItem(
                [self._display_name(section.get("title"), section.get("section_id"), "Section"), section.get("status", "")]
            )
            sec_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, {"type": "section"})
            sec_has_child = False
            for package in section.get("packages", []):
                pkg_item = QtWidgets.QTreeWidgetItem(
                    [self._display_name(package.get("title"), package.get("package_id"), "Package"), package.get("status", "")]
                )
                pkg_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, {"type": "package"})
                pkg_has_child = False
                for part in package.get("parts", []):
                    status = part.get("status")
                    if not part_allowed(status):
                        continue
                    reason = part.get("reason")
                    component_id = part.get("component_id")
                    workspace_disabled = False
                    if component_id and not self._is_component_enabled(component_id):
                        status = STATUS_UNAVAILABLE
                        reason = WORKSPACE_DISABLED_REASON
                        workspace_disabled = True
                        disabled_parts.append(part.get("part_id") or component_id)
                    part_item = QtWidgets.QTreeWidgetItem(
                        [self._display_name(part.get("title"), part.get("part_id"), "Part"), status]
                    )
                    part_item.setData(
                        0,
                        QtCore.Qt.ItemDataRole.UserRole,
                        {
                            "type": "part",
                            "part_id": part.get("part_id"),
                            "module_id": module.get("module_id"),
                            "status": status,
                            "reason": reason,
                            "component_id": component_id,
                            "workspace_disabled": workspace_disabled,
                            "module_status": module_status,
                        },
                    )
                    pkg_item.addChild(part_item)
                    pkg_has_child = True
                if pkg_has_child:
                    sec_item.addChild(pkg_item)
                    sec_has_child = True
            if sec_has_child:
                module_item.addChild(sec_item)
                added_any = True

        if added_any or filter_mode == "All":
            self.tree.addTopLevelItem(module_item)
            self.tree.expandAll()
        else:
            self._set_status("No installed modules yet. Install from Module Management.")
        if disabled_parts:
            _agent_debug_log(
                "workspace",
                "H_WS_PART",
                "app_ui/main.py:ContentManagementScreen._build_tree",
                "parts_marked_disabled",
                {"count": len(disabled_parts), "sample": disabled_parts[:3]},
            )
        self._clear_details()

    def _apply_filter(self) -> None:
        self._build_tree()

    def _on_selection_changed(self) -> None:
        item = self.tree.currentItem()
        if not item:
            self._clear_details()
            return
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
        self.current_selection = data
        node_type = data.get("type")
        if node_type == "part":
            part_id = data.get("part_id")
            status = data.get("status") or ""
            reason = data.get("reason") or "Not installed."
            workspace_disabled = bool(data.get("workspace_disabled"))
            if workspace_disabled:
                status = STATUS_UNAVAILABLE
                reason = WORKSPACE_DISABLED_REASON
            self.detail_title.setText(f"Part {part_id}")
            self.detail_status_pill.set_status(status)
            self.detail_meta.setText(f"Module: {data.get('module_id') or 'physics'}")
            if workspace_disabled:
                self.detail_action.setText("Action: Enable pack in Workspace Management.")
            elif status == STATUS_READY:
                self.detail_action.setText("Action: Open in Content Browser or Uninstall Module.")
            else:
                self.detail_action.setText("Action: Install Module.")
            self.detail_hint.setText(f"Reason: {reason}")
            self.install_part_btn.setVisible(True)
            self.install_part_btn.setEnabled(not workspace_disabled and status != STATUS_READY)
            self.install_module_btn.setVisible(True)
            self.uninstall_module_btn.setVisible(True)
            self.pending_module_id = data.get("module_id")
            self._selected_module_status = data.get("module_status") or status
            self._set_module_action_enabled()
        elif node_type == "module":
            module_id = data.get("module_id") or "module"
            self.detail_title.setText(f"Module {module_id}")
            module_status = data.get("status") or item.text(1)
            self.detail_status_pill.set_status(module_status)
            self.detail_meta.setText(f"Module ID: {module_id}")
            if module_status == STATUS_READY:
                self.detail_action.setText("Action: Uninstall Module.")
            else:
                self.detail_action.setText("Action: Install Module.")
            self.detail_hint.setText("Manage the entire module.")
            self.install_part_btn.setVisible(False)
            self.install_module_btn.setVisible(True)
            self.uninstall_module_btn.setVisible(True)
            self.pending_module_id = module_id
            self._selected_module_status = module_status
            self._set_module_action_enabled()
        else:
            self._clear_details()

    def _clear_details(self) -> None:
        self.current_selection = None
        self.detail_title.setText("Select an item to view details.")
        self.detail_status_pill.setVisible(False)
        self.detail_meta.clear()
        self.detail_action.clear()
        self.detail_hint.clear()
        self.install_part_btn.setVisible(False)
        self.install_module_btn.setVisible(False)
        self.uninstall_module_btn.setVisible(False)
        self.pending_module_id = None
        self._selected_module_status = None

    def _on_item_double_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
        if data.get("type") != "part":
            return
        part_id = data.get("part_id")
        if part_id and self.on_open_part:
            if data.get("workspace_disabled"):
                QtWidgets.QMessageBox.information(self, "Workspace", WORKSPACE_DISABLED_REASON)
                return
            self.on_open_part(part_id)

    def _install_part(self) -> None:
        if not self.current_selection or self.current_selection.get("type") != "part":
            return
        if self.current_selection.get("workspace_disabled"):
            QtWidgets.QMessageBox.information(self, "Workspace", WORKSPACE_DISABLED_REASON)
            return
        if self.install_thread:
            return
        part_id = self.current_selection.get("part_id")
        self.progress_dialog = QtWidgets.QProgressDialog("Installing part...", "", 0, 0, self)
        self.progress_dialog.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        self.progress_dialog.setCancelButton(None)
        worker = InstallWorker(self.adapter, part_id)
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

    def _set_module_action_enabled(self) -> None:
        if not (hasattr(self, "install_module_btn") and hasattr(self, "uninstall_module_btn")):
            return
        if not self.bus:
            self.install_module_btn.setEnabled(False)
            self.uninstall_module_btn.setEnabled(False)
            return
        if self.pending_job_id:
            self.install_module_btn.setEnabled(False)
            self.uninstall_module_btn.setEnabled(False)
            return
        status = self._selected_module_status or ""
        if status == STATUS_READY:
            self.install_module_btn.setEnabled(False)
            self.uninstall_module_btn.setEnabled(True)
        elif status:
            self.install_module_btn.setEnabled(True)
            self.uninstall_module_btn.setEnabled(False)
        else:
            self.install_module_btn.setEnabled(True)
            self.uninstall_module_btn.setEnabled(True)

    def _start_module_job(self, action: str) -> None:
        module_id = self._selected_module_id()
        if not module_id:
            QtWidgets.QMessageBox.information(self, "Module", "Select the module first.")
            return
        if not self.bus:
            QtWidgets.QMessageBox.information(self, "Module", "Runtime bus unavailable.")
            return
        if self.pending_job_id:
            QtWidgets.QMessageBox.information(self, "Module", "Another module job is running.")
            return
        if action == "install" and self._selected_module_status == STATUS_READY:
            QtWidgets.QMessageBox.information(self, "Module", "Module already installed.")
            return
        if action == "uninstall" and self._selected_module_status != STATUS_READY:
            QtWidgets.QMessageBox.information(self, "Module", "Module already uninstalled.")
            return
        topic = BUS_MODULE_INSTALL_REQUEST if action == "install" else BUS_MODULE_UNINSTALL_REQUEST
        self._set_job_state(job_id=None, module_id=module_id, action=action, running=True)
        self._show_progress_panel(
            f"{action.title()} requested",
            f"{action.title()} {module_id}: requesting job...",
            running=True,
        )
        try:
            response = self.bus.request(
                topic,
                {"module_id": module_id},
                source="app_ui",
                timeout_ms=2000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._set_job_state(job_id=None, module_id=None, action=None, running=False)
            self._show_progress_panel(
                "Module job failed",
                f"{action.title()} {module_id}: {exc}",
                running=False,
                ok=False,
            )
            QtWidgets.QMessageBox.warning(self, "Module", f"Request failed: {exc}")
            return
        if not response.get("ok") or not response.get("job_id"):
            self._set_job_state(job_id=None, module_id=None, action=None, running=False)
            self._show_progress_panel(
                "Module job failed",
                f"{action.title()} {module_id}: {response.get('error') or 'unknown'}",
                running=False,
                ok=False,
            )
            QtWidgets.QMessageBox.warning(
                self,
                "Module",
                f"Request failed: {response.get('error') or 'unknown'}",
            )
            return
        job_id = str(response["job_id"])
        self._set_job_state(job_id=job_id, module_id=module_id, action=action, running=True)
        self._show_progress_panel(
            "Module job queued",
            f"{action.title()} {module_id}: awaiting progress (job {job_id[:8]})",
            running=True,
        )
        self._start_job_poll_timer()

    def _selected_module_id(self) -> Optional[str]:
        if self.current_selection and self.current_selection.get("type") == "module":
            return self.current_selection.get("module_id")
        if self.current_selection and self.current_selection.get("type") == "part":
            return self.current_selection.get("module_id")
        return None

    def _is_active_payload(self, payload: Dict[str, Any]) -> bool:
        if not payload:
            return False
        job_id = payload.get("job_id")
        module_id = payload.get("module_id")
        if self.pending_job_id and job_id and job_id != self.pending_job_id:
            return False
        if self.pending_module_id and module_id and module_id != self.pending_module_id:
            return False
        if not (self.pending_job_id or self.pending_module_id):
            return False
        return True

    def _on_module_progress_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if not self._is_active_payload(payload):
            return
        self._handle_progress_payload(payload)

    def _on_job_progress_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if payload.get("job_type") not in (CORE_JOB_MODULE_INSTALL, CORE_JOB_MODULE_UNINSTALL):
            return
        if not self._is_active_payload(payload):
            return
        self._handle_progress_payload(payload)

    def _handle_progress_payload(self, payload: Dict[str, Any]) -> None:
        stage = payload.get("stage") or "Working"
        percent = payload.get("percent")
        percent_text = f"{percent:.1f}%" if isinstance(percent, (int, float)) else ""
        module_id = payload.get("module_id") or self.pending_module_id or "module"
        action = (self.pending_action or "module").title()
        details = f"{action} {module_id}: {percent_text} {stage}".strip()
        self._show_progress_panel("Module Progress", details, running=True)
        self._set_status(details)

    def _on_module_completed_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if not self._is_active_payload(payload):
            return
        ok = bool(payload.get("ok"))
        error = payload.get("error")
        module_id = payload.get("module_id") or self.pending_module_id or "module"
        action = payload.get("action") or self.pending_action or "module"
        summary = "OK" if ok else error or "failed"
        self._show_progress_panel(
            "Module Result",
            f"{action.title()} {module_id}: {summary}",
            running=False,
            ok=ok,
        )
        self._set_status(f"{action.title()} {module_id}: {summary}")
        self._set_job_state(job_id=None, module_id=None, action=None, running=False)
        self._selected_module_status = STATUS_READY if ok and action == "install" else self._selected_module_status
        if ok and action == "uninstall":
            self._selected_module_status = STATUS_NOT_INSTALLED
        self._set_module_action_enabled()
        self.refresh_tree()

    def _on_job_completed_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if payload.get("job_type") not in (CORE_JOB_MODULE_INSTALL, CORE_JOB_MODULE_UNINSTALL):
            return
        if not self._is_active_payload(payload):
            return
        self._stop_job_poll_timer()
        ok = bool(payload.get("ok"))
        error = payload.get("error")
        module_id = self.pending_module_id or "module"
        action = self.pending_action or "module"
        summary = "OK" if ok else error or "failed"
        self._show_progress_panel(
            "Module Result",
            f"{action.title()} {module_id}: {summary}",
            running=False,
            ok=ok,
        )
        self._set_status(f"{action.title()} {module_id}: {summary}")
        self._set_job_state(job_id=None, module_id=None, action=None, running=False)
        self._selected_module_status = STATUS_READY if ok and action == "install" else self._selected_module_status
        if ok and action == "uninstall":
            self._selected_module_status = STATUS_NOT_INSTALLED
        self._set_module_action_enabled()
        self.refresh_tree()

    def _set_job_state(self, *, job_id: Optional[str], module_id: Optional[str], action: Optional[str], running: bool) -> None:
        self.pending_job_id = job_id
        self.pending_module_id = module_id
        self.pending_action = action if running else None
        if not running:
            self._stop_job_poll_timer()
        self._set_module_action_enabled()

    def _start_job_poll_timer(self) -> None:
        job_id = self.pending_job_id
        if not (self.bus and job_id):
            return
        self._stop_job_poll_timer()
        self._job_poll_job_id = job_id
        self._job_poll_started_ms = time.monotonic() * 1000
        timer = QtCore.QTimer(self)
        timer.setInterval(800)
        timer.timeout.connect(self._poll_job_status)
        self._job_poll_timer = timer
        timer.start()

    def _stop_job_poll_timer(self) -> None:
        timer = getattr(self, "_job_poll_timer", None)
        if timer:
            timer.stop()
            timer.deleteLater()
        self._job_poll_timer = None
        self._job_poll_job_id = None
        self._job_poll_started_ms = None

    def _poll_job_status(self) -> None:
        job_id = self._job_poll_job_id or self.pending_job_id
        if not (self.bus and job_id):
            self._stop_job_poll_timer()
            return
        if self._job_poll_started_ms is not None and self._job_poll_timeout_ms:
            elapsed_ms = (time.monotonic() * 1000) - self._job_poll_started_ms
            if elapsed_ms > self._job_poll_timeout_ms:
                self._stop_job_poll_timer()
                self._show_progress_panel(
                    "Module job timeout",
                    f"{(self.pending_action or 'Module').title()} {self.pending_module_id or 'module'}: timed out waiting for completion",
                    running=False,
                    ok=False,
                )
                self._set_job_state(job_id=None, module_id=None, action=None, running=False)
                return
        try:
            response = self.bus.request(
                BUS_JOBS_GET_REQUEST,
                {"job_id": job_id},
                source="app_ui",
                timeout_ms=800,
            )
        except Exception:
            return
        if not response.get("ok"):
            return
        job = response.get("job") or {}
        status = str(job.get("status") or "").upper()
        ok_flag = job.get("ok")
        terminal = status in ("COMPLETED", "FAILED") or ok_flag is not None
        if not terminal:
            return
        self._stop_job_poll_timer()
        payload = {
            "job_id": job_id,
            "job_type": job.get("job_type"),
            "ok": ok_flag,
            "error": job.get("error"),
        }
        self._on_job_completed_event(SimpleNamespace(payload=payload))

    def _show_progress_panel(self, title: str, details: str, running: bool, ok: Optional[bool] = None) -> None:
        color = "#0d47a1"
        if ok is True:
            color = "#2e7d32"
        elif ok is False:
            color = "#b71c1c"
        self.progress_title.setText(title)
        self.progress_title.setStyleSheet(f"font-weight: bold; color: {color};")
        self.progress_details.setText(details)
        self.progress_panel.setVisible(True)

    @staticmethod
    def _display_name(title: Optional[str], fallback: Optional[str], default: str) -> str:
        return str(title or fallback or default)


# endregion


# === [NAV-37] Screens: ComponentSandboxScreen ===============================
# region NAV-37 ComponentSandboxScreen
class ComponentSandboxScreen(QtWidgets.QWidget):
    def __init__(
        self,
        on_back,
        context_provider: Callable[[], "ComponentContext"],
        *,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
    ):
        super().__init__()
        self.on_back = on_back
        self.context_provider = context_provider
        self._host: Optional["ComponentHost"] = None

        layout = QtWidgets.QVBoxLayout(self)
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title="Component Sandbox",
            on_back=self.on_back,
            workspace_selector=selector,
        )
        layout.addWidget(header)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: #444;")
        layout.addWidget(self.status_label)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(splitter, stretch=1)

        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        component_label = QtWidgets.QLabel("Components")
        component_label.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(component_label)
        self.component_list = QtWidgets.QListWidget()
        self.component_list.itemDoubleClicked.connect(self._open_selected)
        left_layout.addWidget(self.component_list, stretch=1)

        button_row = QtWidgets.QHBoxLayout()
        self.open_btn = QtWidgets.QPushButton("Open")
        self.open_btn.clicked.connect(self._open_selected)
        button_row.addWidget(self.open_btn)
        self.close_btn = QtWidgets.QPushButton("Close")
        self.close_btn.clicked.connect(self._close_component)
        button_row.addWidget(self.close_btn)
        left_layout.addLayout(button_row)

        lab_label = QtWidgets.QLabel("Labs")
        lab_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
        left_layout.addWidget(lab_label)
        self.lab_list = QtWidgets.QListWidget()
        self.lab_list.itemDoubleClicked.connect(self._open_selected_lab_component)
        left_layout.addWidget(self.lab_list, stretch=1)

        lab_button_row = QtWidgets.QHBoxLayout()
        self.open_lab_btn = QtWidgets.QPushButton("Open selected lab as component")
        self.open_lab_btn.clicked.connect(self._open_selected_lab_component)
        lab_button_row.addWidget(self.open_lab_btn)
        left_layout.addLayout(lab_button_row)

        pack_label = QtWidgets.QLabel("Pack Components")
        pack_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
        left_layout.addWidget(pack_label)
        self.pack_list = QtWidgets.QListWidget()
        self.pack_list.itemDoubleClicked.connect(self._open_selected_pack_component)
        left_layout.addWidget(self.pack_list, stretch=1)

        pack_button_row = QtWidgets.QHBoxLayout()
        self.open_pack_btn = QtWidgets.QPushButton("Open selected pack component")
        self.open_pack_btn.clicked.connect(self._open_selected_pack_component)
        pack_button_row.addWidget(self.open_pack_btn)
        left_layout.addLayout(pack_button_row)

        splitter.addWidget(left_panel)

        self.host_container = QtWidgets.QWidget()
        host_layout = QtWidgets.QVBoxLayout(self.host_container)
        host_layout.setContentsMargins(0, 0, 0, 0)

        if ComponentHost is None or component_registry is None:
            msg = "Component runtime unavailable."
            if COMPONENT_RUNTIME_ERROR:
                msg = f"{msg} {COMPONENT_RUNTIME_ERROR}"
            error_label = QtWidgets.QLabel(msg)
            error_label.setStyleSheet("color: #b00;")
            host_layout.addWidget(error_label)
            self.open_btn.setEnabled(False)
            self.close_btn.setEnabled(False)
        else:
            self._host = ComponentHost()
            host_layout.addWidget(self._host, stretch=1)

        splitter.addWidget(self.host_container)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setChildrenCollapsible(False)

        self.refresh_components()

    def on_workspace_changed(self) -> None:
        if self._host is not None:
            try:
                self._host.unmount()
                self.status_label.setText("Workspace changed. Reopen a component to refresh context.")
            except Exception:
                pass
        self.refresh_components()

    def refresh_components(self) -> None:
        self.component_list.clear()
        self.lab_list.clear()
        self.pack_list.clear()
        if component_registry is None:
            return
        try:
            component_registry.register_lab_components(lab_registry)
        except Exception:
            pass
        policy = _get_global_component_policy()
        pack_manifests = []
        if component_packs is not None:
            try:
                pack_manifests = component_packs.load_installed_packs()
            except Exception:
                pack_manifests = []
        registry = component_registry.get_registry()
        for meta in registry.list_components():
            label = f"{meta.display_name} ({meta.component_id})"
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, meta.component_id)
            self.component_list.addItem(item)
        for lab_id, plugin in lab_registry.list_labs().items():
            title = getattr(plugin, "title", lab_id)
            item = QtWidgets.QListWidgetItem(f"{title} ({lab_id})")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, lab_id)
            self.lab_list.addItem(item)
        for pack in pack_manifests:
            manifest = pack.get("manifest") if isinstance(pack, dict) else None
            if not isinstance(manifest, dict):
                continue
            pack_id = manifest.get("pack_id") or "pack"
            if policy and not policy.is_pack_enabled(pack_id):
                continue
            components = manifest.get("components")
            if not isinstance(components, list):
                continue
            for component in components:
                if not isinstance(component, dict):
                    continue
                component_id = component.get("component_id")
                display_name = component.get("display_name") or component_id
                if not component_id:
                    continue
                label = f"{display_name} ({component_id}) [{pack_id}]"
                item = QtWidgets.QListWidgetItem(label)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, component_id)
                self.pack_list.addItem(item)

    def _open_selected(self) -> None:
        if component_registry is None or self._host is None:
            return
        item = self.component_list.currentItem()
        if not item:
            self.status_label.setText("Select a component to open.")
            return
        component_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        component = component_registry.get_registry().get_component(component_id)
        if not component:
            self.status_label.setText(f"Component '{component_id}' is not available.")
            return
        context = self.context_provider()
        self._host.mount(component, context)
        self.status_label.setText(f"Opened: {component_id}")

    def _close_component(self) -> None:
        if self._host is None:
            return
        self._host.unmount()
        self.status_label.setText("Component closed.")

    def _open_selected_lab_component(self) -> None:
        if component_registry is None or self._host is None:
            return
        item = self.lab_list.currentItem()
        if not item:
            self.status_label.setText("Select a lab to open as a component.")
            return
        lab_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        component_id = f"labhost:{lab_id}"
        component = component_registry.get_registry().get_component(component_id)
        if not component:
            self.status_label.setText(f"Lab component '{component_id}' is not registered.")
            return
        context = self.context_provider()
        self._host.mount(component, context)
        self.status_label.setText(f"Opened lab component: {lab_id}")

    def _open_selected_pack_component(self) -> None:
        if component_registry is None or self._host is None:
            return
        item = self.pack_list.currentItem()
        if not item:
            self.status_label.setText("Select a pack component to open.")
            return
        component_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        component = component_registry.get_registry().get_component(component_id)
        if not component:
            self.status_label.setText(f"Pack component '{component_id}' is not registered.")
            return
        context = self.context_provider()
        self._host.mount(component, context)
        self.status_label.setText(f"Opened pack component: {component_id}")


# endregion


# === [NAV-38] Screens: ComponentHostScreen ==================================
# region NAV-38 ComponentHostScreen
class ComponentHostScreen(QtWidgets.QWidget):
    def __init__(
        self,
        on_back,
        *,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
    ):
        super().__init__()
        self.on_back = on_back
        self._host: Optional["ComponentHost"] = None

        layout = QtWidgets.QVBoxLayout(self)
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title="Component Viewer",
            on_back=self.on_back,
            workspace_selector=selector,
        )
        self.close_btn = QtWidgets.QPushButton("Close")
        self.close_btn.clicked.connect(self._close_component)
        header.add_action_widget(self.close_btn)
        layout.addWidget(header)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: #444;")
        layout.addWidget(self.status_label)

        if ComponentHost is None or component_registry is None:
            msg = "Component runtime unavailable."
            if COMPONENT_RUNTIME_ERROR:
                msg = f"{msg} {COMPONENT_RUNTIME_ERROR}"
            error_label = QtWidgets.QLabel(msg)
            error_label.setStyleSheet("color: #b00;")
            layout.addWidget(error_label)
            self.close_btn.setEnabled(False)
        else:
            self._host = ComponentHost()
            layout.addWidget(self._host, stretch=1)

    def open_component(self, component_id: str, context: "ComponentContext") -> None:
        if component_registry is None or self._host is None:
            return
        component = component_registry.get_registry().get_component(component_id)
        if not component:
            self.status_label.setText(f"Component '{component_id}' is not registered.")
            return
        self._host.mount(component, context)
        self.status_label.setText(f"Opened component: {component_id}")

    def _close_component(self) -> None:
        if self._host is None:
            return
        self._host.unmount()
        self.status_label.setText("Component closed.")


# endregion


# === [NAV-39] Screens: LabHostScreen ========================================
# region NAV-39 LabHostScreen
class LabHostScreen(QtWidgets.QWidget):
    def __init__(
        self,
        on_back,
        lab_host: QtWidgets.QWidget,
        title: str,
        *,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back

        layout = QtWidgets.QVBoxLayout(self)
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title=title,
            on_back=self.on_back,
            workspace_selector=selector,
        )
        layout.addWidget(header)
        layout.addWidget(lab_host, stretch=1)

    def wants_global_esc_back(self) -> bool:
        return False


# endregion


# === [NAV-90] MainWindow =====================================================
# region NAV-90 MainWindow
class MainWindow(QtWidgets.QMainWindow):
    # --- [NAV-90A] ctor / wiring
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
        self.workspace_info: Dict[str, Any] = self._ensure_workspace_context()
        self.workspace_component_policy = WorkspaceComponentPolicy()
        _set_global_component_policy(self.workspace_component_policy)
        self.workspace_config: Dict[str, Any] = {}
        self._workspace_selectors: list[WorkspaceSelector] = []
        self._workspace_event_sub: Optional[str] = None
        self._workspace_event_bridge = _BusDispatchBridge(self)
        self._esc_shortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        self._esc_shortcut.activated.connect(self._handle_escape_back)

        self._load_active_workspace_config()
        self._reload_workspace_components()

        selector_factory = self._make_workspace_selector

        self.main_menu = MainMenuScreen(
            self._start_physics,
            self._open_content_browser,
            self._open_settings,
            self._open_module_management,
            self._open_content_management,
            self._open_diagnostics,
            self._open_workspace_management,
            self._open_component_management,
            self._open_component_sandbox,
            self._quit_app,
            self.current_profile,
            workspace_selector_factory=selector_factory,
        )
        self.module_management = ModuleManagementScreen(
            self._show_main_menu,
            bus=APP_BUS,
            workspace_selector_factory=selector_factory,
            component_policy_provider=self._get_component_policy,
        )
        self.content_browser = ContentBrowserScreen(
            self.adapter,
            self._show_main_menu,
            lambda: self.current_profile,
            self._open_lab,
            self._open_component_from_part,
            workspace_selector_factory=selector_factory,
            component_policy_provider=self._get_component_policy,
        )
        self.system_health = SystemHealthScreen(
            self._show_main_menu,
            cleanup_enabled=CORE_CENTER_AVAILABLE,
            bus=APP_BUS,
            workspace_selector_factory=selector_factory,
        )
        self.content_management = ContentManagementScreen(
            self.adapter,
            self._show_main_menu,
            self._open_content_browser_from_management,
            bus=APP_BUS,
            workspace_selector_factory=selector_factory,
            component_policy_provider=self._get_component_policy,
        )
        self.component_management = ComponentManagementScreen(
            self._show_main_menu,
            bus=APP_BUS,
            workspace_selector_factory=selector_factory,
            on_packs_changed=self._reload_workspace_components,
        )
        self.workspace_management = WorkspaceManagementScreen(
            self._show_main_menu,
            self._on_workspace_changed,
            bus=APP_BUS,
            workspace_selector_factory=selector_factory,
            log_handler=_agent_debug_log,
        )
        self.component_sandbox = ComponentSandboxScreen(
            self._show_main_menu,
            self._build_component_context,
            workspace_selector_factory=selector_factory,
        )
        self.component_host = ComponentHostScreen(
            self._show_content_browser, workspace_selector_factory=selector_factory
        )

        self.stacked.addWidget(self.main_menu)
        self.stacked.addWidget(self.content_browser)
        self.stacked.addWidget(self.system_health)
        self.stacked.addWidget(self.module_management)
        self.stacked.addWidget(self.content_management)
        self.stacked.addWidget(self.component_management)
        self.stacked.addWidget(self.workspace_management)
        self.stacked.addWidget(self.component_sandbox)
        self.stacked.addWidget(self.component_host)
        self._refresh_workspace_selectors()

        if APP_BUS and BUS_WORKSPACE_ACTIVE_CHANGED:
            try:
                def _workspace_bridge(envelope):
                    self._workspace_event_bridge.envelope_dispatched.emit(
                        self._handle_workspace_envelope, envelope
                    )

                self._workspace_event_sub = APP_BUS.subscribe(
                    BUS_WORKSPACE_ACTIVE_CHANGED,
                    _workspace_bridge,
                    replay_last=True,
                )
            except Exception:
                self._workspace_event_sub = None

        self._show_main_menu()

    def _open_workspace_management(self):
        self._dispose_lab_widget()
        if self.workspace_management:
            self.workspace_management.refresh()
            self.stacked.setCurrentWidget(self.workspace_management)

    def _handle_escape_back(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        modal = app.activeModalWidget() is not None
        focus = app.focusWidget()
        focus_class = type(focus).__name__ if focus else None
        editable_combo = isinstance(focus, QtWidgets.QComboBox) and focus.isEditable()
        current = self.stacked.currentWidget()
        current_class = type(current).__name__ if current else None
        wants_global = None
        try:
            if current and hasattr(current, "wants_global_esc_back"):
                wants_global = bool(current.wants_global_esc_back())
        except Exception:
            wants_global = "error"
        is_lab = current is self.lab_host_widget
        if modal:
            return
        if isinstance(focus, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
            return
        if isinstance(focus, QtWidgets.QComboBox) and focus.isEditable():
            return
        if wants_global is False:
            return
        if current is self.lab_host_widget:
            return
        if current is self.main_menu:
            return
        on_back = getattr(current, "on_back", None)
        if callable(on_back):
            on_back()
            return
        self._show_main_menu()

    def _make_workspace_selector(self) -> WorkspaceSelector:
        selector = WorkspaceSelector(
            list_workspaces=self._list_workspaces,
            activate_workspace=self._activate_workspace,
            get_active_workspace_id=lambda: (self.workspace_info or {}).get("id"),
        )
        self._workspace_selectors.append(selector)
        return selector

    def _refresh_workspace_selectors(self) -> None:
        active_id = (self.workspace_info or {}).get("id")
        for selector in list(self._workspace_selectors):
            try:
                selector.refresh(active_id)
            except Exception:
                continue

    def _handle_workspace_envelope(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        workspace = payload.get("workspace")
        if not isinstance(workspace, dict):
            return
        current_id = (self.workspace_info or {}).get("id")
        incoming_id = workspace.get("id")
        if incoming_id and current_id == incoming_id:
            self._refresh_workspace_selectors()
        self._on_workspace_changed(workspace, notify_bus=False)

    def _get_component_policy(self) -> WorkspaceComponentPolicy:
        return self.workspace_component_policy

    def _active_workspace_prefs_root(self) -> Path:
        paths = self.workspace_info.get("paths") if isinstance(self.workspace_info, dict) else None
        if isinstance(paths, dict) and paths:
            return _workspace_prefs_root_from_paths(paths)
        workspace_path = ""
        if isinstance(self.workspace_info, dict):
            workspace_path = self.workspace_info.get("path") or ""
        if workspace_path:
            return _workspace_prefs_root_from_dir(workspace_path)
        workspace_id = (self.workspace_info or {}).get("id") or "default"
        return Path("data") / "workspaces" / str(workspace_id) / "prefs"

    def _load_active_workspace_config(self) -> None:
        prefs_root = self._active_workspace_prefs_root()
        self.workspace_config = _load_workspace_config_from_root(prefs_root)

    def _resolve_enabled_pack_ids(self, available_pack_ids: set[str]) -> set[str]:
        config_value = (self.workspace_config or {}).get("enabled_component_packs")
        if isinstance(config_value, list):
            normalized = {str(pack_id) for pack_id in config_value if str(pack_id) in available_pack_ids}
            return normalized
        return set(available_pack_ids)

    def _reload_workspace_components(self) -> None:
        try:
            manifests = component_packs.load_installed_packs()
        except Exception:
            manifests = []
        pack_components: Dict[str, List[str]] = {}
        for entry in manifests:
            manifest = entry.get("manifest") if isinstance(entry, dict) else None
            if not isinstance(manifest, dict):
                continue
            pack_id = str(manifest.get("pack_id") or "").strip()
            if not pack_id:
                continue
            component_ids: List[str] = []
            for component in manifest.get("components") or []:
                if not isinstance(component, dict):
                    continue
                component_id = component.get("component_id")
                if component_id:
                    component_ids.append(str(component_id))
            pack_components[pack_id] = component_ids
        available_pack_ids = set(pack_components.keys())
        inventory_snapshot, inventory_error = _request_inventory_snapshot(APP_BUS)
        inventory_available = inventory_snapshot is not None and not inventory_error
        if inventory_snapshot:
            inv_ids = {
                str(item.get("id") or "").strip()
                for item in inventory_snapshot.get("component_packs") or []
                if item.get("id")
            }
            if inv_ids:
                available_pack_ids &= inv_ids
        enabled_pack_ids = self._resolve_enabled_pack_ids(available_pack_ids)
        filtered_manifests = [
            entry
            for entry in manifests
            if str((entry.get("manifest") or {}).get("pack_id") or "").strip() in enabled_pack_ids
        ]
        try:
            component_registry.register_lab_components(lab_registry)
        except Exception:
            pass
        component_registry.register_pack_components(filtered_manifests)
        disabled_components = {
            component_id
            for pack_id, components in pack_components.items()
            if pack_id not in enabled_pack_ids
            for component_id in components
        }
        self.workspace_component_policy.update(
            enabled_pack_ids=enabled_pack_ids,
            available_pack_ids=available_pack_ids,
            disabled_component_ids=disabled_components,
        )
        _agent_debug_log(
            "workspace",
            "H_WS_PACKS",
            "app_ui/main.py:MainWindow._reload_workspace_components",
            "policy_applied",
            {
                "workspace_id": (self.workspace_info or {}).get("id"),
                "available_count": len(available_pack_ids),
                "enabled_count": len(enabled_pack_ids),
                "disabled_components": len(disabled_components),
                "inventory_available": inventory_available,
            },
        )

    def _list_workspaces(self) -> List[Dict[str, object]]:
        if APP_BUS and BUS_WORKSPACE_LIST_REQUEST:
            try:
                response = APP_BUS.request(
                    BUS_WORKSPACE_LIST_REQUEST,
                    {},
                    source="app_ui",
                    timeout_ms=2000,
                )
                if response.get("ok"):
                    return response.get("workspaces") or []
            except Exception:
                pass
        ws = self.workspace_info if isinstance(self.workspace_info, dict) else None
        return [ws] if ws else []

    def _activate_workspace(self, workspace_id: str) -> bool:
        workspace_id = str(workspace_id or "").strip()
        if not workspace_id:
            return False
        if not (APP_BUS and BUS_WORKSPACE_SET_ACTIVE_REQUEST):
            QtWidgets.QMessageBox.warning(self, "Workspace", "Runtime bus unavailable.")
            return False
        try:
            response = APP_BUS.request(
                BUS_WORKSPACE_SET_ACTIVE_REQUEST,
                {"workspace_id": workspace_id},
                source="app_ui",
                timeout_ms=1500,
            )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Workspace", f"Set active failed: {exc}")
            return False
        if not response.get("ok"):
            QtWidgets.QMessageBox.warning(
                self, "Workspace", response.get("error") or "Set active failed."
            )
            return False
        workspace = response.get("workspace")
        if isinstance(workspace, dict):
            self._on_workspace_changed(workspace, notify_bus=False)
            self._publish_workspace_changed(workspace)
            return True
        return False

    def _publish_workspace_changed(self, workspace: Dict[str, Any]) -> None:
        if not isinstance(workspace, dict):
            return
        if not (APP_BUS and BUS_WORKSPACE_ACTIVE_CHANGED):
            return
        try:
            APP_BUS.publish(
                BUS_WORKSPACE_ACTIVE_CHANGED,
                {"workspace": workspace},
                source="app_ui",
                sticky=True,
            )
        except Exception:
            pass

    def _ensure_workspace_context(self) -> Dict[str, Any]:
        info = self._request_workspace_info()
        if info:
            return info
        return self._local_workspace_info("default")

    def _request_workspace_info(self) -> Optional[Dict[str, Any]]:
        if not (APP_BUS and BUS_WORKSPACE_GET_ACTIVE):
            return None
        try:
            response = APP_BUS.request(BUS_WORKSPACE_GET_ACTIVE, {}, source="app_ui", timeout_ms=1000)
        except Exception:
            response = {"ok": False}
        if response.get("ok"):
            workspace = response.get("workspace")
            if isinstance(workspace, dict):
                return workspace
            if "id" in response and "paths" in response:
                return {"id": response.get("id"), "paths": response.get("paths")}
        if APP_BUS and BUS_WORKSPACE_CREATE:
            try:
                response = APP_BUS.request(
                    BUS_WORKSPACE_CREATE,
                    {"workspace_id": "default"},
                    source="app_ui",
                    timeout_ms=1000,
                )
            except Exception:
                response = {"ok": False}
            if response.get("ok") and isinstance(response.get("workspace"), dict):
                return response.get("workspace")
        return None

    def _local_workspace_info(self, workspace_id: str) -> Dict[str, Any]:
        safe_id = self._sanitize_workspace_id(workspace_id)
        root = Path("data") / "workspaces" / safe_id
        paths = {
            "root": root,
            "runs": root / "runs",
            "runs_local": root / "runs_local",
            "cache": root / "cache",
            "store": root / "store",
            "prefs": root / "prefs",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return {"id": safe_id, "paths": {name: str(path.resolve()) for name, path in paths.items()}}

    def _sanitize_workspace_id(self, value: str) -> str:
        clean = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
        return clean or "default"

    def _show_module_management(self):
        self._dispose_lab_widget()
        if self.module_management:
            self.module_management._refresh_registry()
            self.stacked.setCurrentWidget(self.module_management)

    def _show_main_menu(self):
        self._dispose_lab_widget()
        self.stacked.setCurrentWidget(self.main_menu)

    def _on_workspace_changed(self, workspace: Dict[str, Any], *, notify_bus: bool = True) -> None:
        if isinstance(workspace, dict):
            self.workspace_info = workspace
        self._load_active_workspace_config()
        self._reload_workspace_components()
        self._refresh_workspace_selectors()
        if self.system_health:
            try:
                self.system_health._update_runs_workspace_label()
                self.system_health._refresh_runs_list()
            except Exception:
                pass
        if self.component_sandbox:
            try:
                self.component_sandbox.on_workspace_changed()
            except Exception:
                pass
        if self.content_browser:
            try:
                self.content_browser.refresh_tree()
            except Exception:
                pass
        if self.content_management:
            try:
                self.content_management.refresh_tree()
            except Exception:
                pass
        if self.component_management:
            try:
                self.component_management.refresh()
            except Exception:
                pass
        if notify_bus:
            self._publish_workspace_changed(self.workspace_info)

    def _start_physics(self):
        quick_part = self._find_quick_start_part()
        if quick_part:
            self.open_part_by_id(quick_part)
            return
        self._dispose_lab_widget()
        if self.content_management:
            self.content_management.refresh_tree()
            self.content_management._set_status("Install a module to begin.")
            self.stacked.setCurrentWidget(self.content_management)
            return
        self._show_module_management()

    def _find_quick_start_part(self) -> Optional[str]:
        data = self.adapter.list_tree()
        module = data.get("module") if isinstance(data, dict) else None
        if not isinstance(module, dict):
            return None
        for section in module.get("sections", []):
            for package in section.get("packages", []):
                for part in package.get("parts", []):
                    if part.get("status") != STATUS_READY:
                        continue
                    part_id = part.get("part_id")
                    if not part_id:
                        continue
                    lab = part.get("lab")
                    lab_id = lab.get("lab_id") if isinstance(lab, dict) else None
                    if lab_id or str(part_id).endswith("_demo"):
                        return part_id
        return None

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

    def _open_content_browser_from_management(self, part_id: str) -> None:
        self._open_content_browser(focus_part=part_id)

    def open_part_by_id(self, part_id: str) -> None:
        detail = self.adapter.get_part(part_id)
        manifest = detail.get("manifest") or {}
        behavior = manifest.get("behavior") or {}
        component_id = detail.get("component_id") or manifest.get("component_id")
        lab_id = None
        detail_lab = detail.get("lab") if isinstance(detail, dict) else None
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
        if not lab_id and part_id == "gravity_demo":
            lab_id = "gravity"
        if not lab_id and behavior.get("preset") == "projectile-demo":
            lab_id = "projectile"
        if not lab_id and part_id == "projectile_demo":
            lab_id = "projectile"
        if component_id and detail.get("status") == STATUS_READY:
            self._open_component_from_part(component_id, part_id, manifest, detail)
            return
        if lab_id and detail.get("status") == STATUS_READY:
            self._open_lab(lab_id, part_id, manifest, detail)
            return
        self._open_content_browser(focus_part=part_id)

    def _open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()
        self.current_profile = ui_config.load_experience_profile()
        if self.main_menu:
            self.main_menu.set_profile(self.current_profile)
        if self.content_browser:
            self.content_browser.set_profile(self.current_profile)

    def _open_module_management(self):
        self._show_module_management()

    def _open_content_management(self):
        self._dispose_lab_widget()
        if self.content_management:
            self.content_management.refresh_tree()
            self.stacked.setCurrentWidget(self.content_management)

    def _open_diagnostics(self):
        self._dispose_lab_widget()
        if self.system_health:
            self.system_health.prepare()
            self.stacked.setCurrentWidget(self.system_health)

    def _open_component_management(self):
        self._dispose_lab_widget()
        if self.component_management:
            self.component_management.refresh()
            self.stacked.setCurrentWidget(self.component_management)

    def _open_component_sandbox(self):
        self._dispose_lab_widget()
        if not COMPONENT_RUNTIME_AVAILABLE:
            QtWidgets.QMessageBox.warning(self, "Components", "Component runtime unavailable.")
            return
        if self.component_sandbox:
            self.component_sandbox.refresh_components()
            self.stacked.setCurrentWidget(self.component_sandbox)

    def _open_component_from_part(
        self,
        component_id: str,
        part_id: Optional[str],
        manifest: Dict[str, Any],
        detail: Dict[str, Any],
    ) -> None:
        self._dispose_lab_widget()
        if not COMPONENT_RUNTIME_AVAILABLE or self.component_host is None:
            QtWidgets.QMessageBox.warning(self, "Components", "Component runtime unavailable.")
            return
        context = self._build_component_context(part_id=part_id, detail=detail)
        if not self.workspace_component_policy.is_component_enabled(component_id):
            QtWidgets.QMessageBox.information(self, "Component", WORKSPACE_DISABLED_REASON)
            return
        self.component_host.open_component(component_id, context)
        self.stacked.setCurrentWidget(self.component_host)

    def _quit_app(self):
        app = QtWidgets.QApplication.instance()
        if app:
            app.quit()

    def _build_component_context(
        self,
        *,
        part_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> "ComponentContext":
        policy = dict(LAB_DEFAULT_POLICY)
        policy_topic = getattr(BUS_TOPICS, "CORE_POLICY_GET_REQUEST", "core.policy.get.request") if BUS_TOPICS else "core.policy.get.request"
        if APP_BUS and policy_topic:
            try:
                response = APP_BUS.request(policy_topic, {}, source="app_ui", timeout_ms=1000)
            except Exception:
                response = {"ok": False}
            if response.get("ok") and isinstance(response.get("policy"), dict):
                policy.update(response["policy"])
        paths = self.workspace_info.get("paths") if isinstance(self.workspace_info, dict) else {}
        runs_root = Path(paths.get("runs") or Path("data") / "workspaces" / "default" / "runs")
        runs_local_root = Path(paths.get("runs_local") or Path("data") / "workspaces" / "default" / "runs_local")
        store_root = Path(paths.get("store") or Path("data") / "store")
        storage = StorageRoots(
            roaming=Path("data/roaming"),
            store=store_root,
            runs=runs_root,
            runs_local=runs_local_root,
        )
        asset_root = None
        if isinstance(detail, dict):
            paths = detail.get("paths")
            if isinstance(paths, dict):
                store_manifest = paths.get("store_manifest")
                if isinstance(store_manifest, str):
                    asset_root = Path(store_manifest).resolve().parent
        return ComponentContext(
            bus=APP_BUS,
            policy=policy,
            storage=storage,
            profile=self.current_profile,
            reduced_motion=ui_config.get_reduced_motion(),
            content_adapter=self.adapter,
            part_id=part_id,
            detail=detail,
            asset_root=asset_root,
            workspace_id=self.workspace_info.get("id"),
            workspace_root=Path(paths.get("root")) if isinstance(paths, dict) and paths.get("root") else None,
        )

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
            host = LabHost(
                lab_id,
                widget,
                guide_text,
                reduced_motion,
                bus=APP_BUS,
                profile=self.current_profile,
                plugin=plugin,
            )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Lab", f"Failed to open lab: {exc}")
            return
        self.lab_widget = widget
        title = plugin.title if getattr(plugin, "title", None) else f"Lab: {lab_id}"
        screen = LabHostScreen(
            self._show_content_browser,
            host,
            title,
            workspace_selector_factory=self._make_workspace_selector,
        )
        self.lab_host_widget = screen
        self.stacked.addWidget(screen)
        self.stacked.setCurrentWidget(screen)

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
# endregion


# === [NAV-99] main() entrypoint =============================================
# region NAV-99 main()
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
# endregion
