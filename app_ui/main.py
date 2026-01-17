# =============================================================================
# NAV INDEX (search these tags)
# [NAV-00] Imports / constants
# [NAV-01] Small utilities (font safety, path helpers, etc.)
# [NAV-10] Navigation controller / routing helpers
# [NAV-20] AppHeader + workspace selector wiring
# [NAV-30] Screens: MainMenuScreen
# [NAV-31] Screens: ContentBrowserScreen (app_ui/screens/content_browser.py)
# [NAV-32] Screens: SystemHealthScreen (app_ui/screens/system_health.py)
# [NAV-33] Screens: WorkspaceManagementScreen (app_ui/screens/workspace_management.py)
# [NAV-34] Screens: ModuleManagementScreen
# [NAV-35] Screens: ComponentManagementScreen (app_ui/screens/component_management.py)
# [NAV-36] Screens: ContentManagementScreen
# [NAV-37] Screens: ComponentSandboxScreen
# [NAV-37A] Screens: BlockHostScreen (app_ui/screens/block_host.py)
# [NAV-37B] Screens: BlockCatalogScreen (app_ui/screens/block_catalog.py)
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
from app_ui.codesee.runtime.events import CodeSeeEvent, EVENT_APP_ACTIVITY, EVENT_JOB_UPDATE
from app_ui.codesee.runtime.bus_bridge import BusBridge
from app_ui.codesee.runtime.hooks import install_exception_hooks
from app_ui.codesee.runtime.hub import CodeSeeRuntimeHub, get_global_hub, set_global_hub
from app_ui.codesee.screen import CodeSeeScreen
from app_ui.codesee.window import CodeSeeWindow
from app_ui import ui_scale
from app_ui import versioning
from app_ui.window_state import restore_geometry as restore_window_geometry
from app_ui.window_state import save_geometry as save_window_geometry
from app_ui.screens.component_management import ComponentManagementScreen
from app_ui.screens.block_catalog import BlockCatalogScreen
from app_ui.screens.block_host import BlockHostScreen
from app_ui.screens.content_browser import ContentBrowserScreen
from app_ui.screens.system_health import SystemHealthScreen
from app_ui.screens.workspace_management import (
    WorkspaceManagementScreen,
    _load_workspace_config_from_root,
    _request_inventory_snapshot,
    _save_workspace_config_to_root,
    _workspace_prefs_root_from_dir,
    _workspace_prefs_root_from_paths,
)
from app_ui.ui_helpers.assets import read_asset_text
from app_ui.ui_helpers.component_policy import (
    WorkspaceComponentPolicy,
    _get_global_component_policy,
    _set_global_component_policy,
)
from app_ui.ui_helpers import terms
from app_ui.ui_helpers.install_worker import InstallWorker
from app_ui.ui_helpers.statuses import (
    STATUS_READY,
    STATUS_NOT_INSTALLED,
    STATUS_UNAVAILABLE,
    WORKSPACE_DISABLED_REASON,
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
# (moved to app_ui/ui_helpers/component_policy.py)
# endregion


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


_qt_msg_handler_installed = False
_prev_qt_msg_handler = None


def _install_qt_message_filter() -> None:
    global _qt_msg_handler_installed, _prev_qt_msg_handler
    if _qt_msg_handler_installed:
        return
    if os.environ.get("PHYSICSLAB_SUPPRESS_QFONT_WARN", "1") in ("0", "false", "False"):
        _qt_msg_handler_installed = True
        return

    def _handler(mode, context, message):  # type: ignore[no-untyped-def]
        try:
            if mode == QtCore.QtMsgType.QtWarningMsg and message.startswith("QFont::setPointSize:"):
                return
        except Exception:
            pass
        if _prev_qt_msg_handler:
            _prev_qt_msg_handler(mode, context, message)
        else:
            try:
                sys.stderr.write(f"{message}\n")
            except Exception:
                pass

    _prev_qt_msg_handler = QtCore.qInstallMessageHandler(_handler)
    _qt_msg_handler_installed = True

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
        on_open_block_catalog,
        on_open_code_see,
        on_open_code_see_window,
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
        self.on_open_block_catalog = on_open_block_catalog
        self.on_open_code_see = on_open_code_see
        self.on_open_code_see_window = on_open_code_see_window
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
        if self.on_open_block_catalog:
            self._add_button(f"{terms.BLOCK} Catalog", self.on_open_block_catalog)

        if self.profile in ("Educator", "Explorer"):
            self._add_button(f"{terms.TOPIC} Management", self.on_open_module_mgmt)
            self._add_button("Content Management", self.on_open_content_mgmt)

        if self.profile in ("Educator", "Explorer"):
            self._add_button("System Health / Storage", self.on_open_diagnostics)

        if self.profile == "Explorer" and self.on_open_workspace_mgmt:
            self._add_button(f"{terms.PROJECT} Management", self.on_open_workspace_mgmt)

        if self.profile == "Explorer" and self.on_open_component_mgmt:
            self._add_button(f"{terms.PACK} Management", self.on_open_component_mgmt)

        if self.profile == "Explorer" and self.on_open_component_sandbox and COMPONENT_RUNTIME_AVAILABLE:
            self._add_button(f"{terms.BLOCK} Sandbox", self.on_open_component_sandbox)

        if self.profile == "Explorer" and self.on_open_code_see:
            self._add_button("Code See", self.on_open_code_see)
        if self.profile == "Explorer" and self.on_open_code_see_window:
            self._add_button("Code See (Window)", self.on_open_code_see_window)

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

        header = QtWidgets.QLabel(f"{terms.TOPIC} Manager")
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

        self.part_title = QtWidgets.QLabel("Select an activity to view details.")
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
            self.error_label.setText(reason or "Topic information unavailable.")
            return

        self.error_label.clear()
        module_status = data.get("status", STATUS_READY)
        module_item = QtWidgets.QTreeWidgetItem([
            f"{terms.TOPIC} {module.get('module_id')}: {module.get('title')}",
            module_status,
        ])
        self.tree.addTopLevelItem(module_item)

        for section in module.get("sections", []):
            sec_status = section.get("status", STATUS_READY)
            section_text = f"{terms.UNIT} {section.get('section_id')}: {section.get('title')}"
            section_item = QtWidgets.QTreeWidgetItem([section_text, sec_status])
            if section.get("reason"):
                section_item.setToolTip(0, section.get("reason"))
            module_item.addChild(section_item)

            for package in section.get("packages", []):
                pkg_status = package.get("status", STATUS_READY)
                package_text = f"{terms.LESSON} {package.get('package_id')}: {package.get('title')}"
                package_item = QtWidgets.QTreeWidgetItem([package_text, pkg_status])
                if package.get("reason"):
                    package_item.setToolTip(0, package.get("reason"))
                section_item.addChild(package_item)

                for part in package.get("parts", []):
                    part_text = f"{terms.ACTIVITY} {part.get('part_id')}: {part.get('title')}"
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
        self.part_title.setText("Select an activity to view details.")
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
            return "Preview available only for text-based activities."

        content = manifest.get("content") or {}
        asset = content.get("asset_path")
        if not asset:
            return "Activity manifest missing asset path."

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
                f"Unable to download activity: {result.get('reason', 'Unknown error')}",
            )
        else:
            QtWidgets.QMessageBox.information(
                self,
                "Download Complete",
                f"Activity status: {result.get('status')} ({result.get('reason') or 'ok'})",
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
            QtWidgets.QMessageBox.warning(self, "Run Failed", "Activity manifest unavailable.")
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

        layout.addWidget(QtWidgets.QLabel("UI Scale"))
        self.scale_combo = QtWidgets.QComboBox()
        self.scale_combo.addItems(["80%", "90%", "100%", "110%", "125%", "150%"])
        layout.addWidget(self.scale_combo)

        layout.addWidget(QtWidgets.QLabel("Density"))
        self.density_combo = QtWidgets.QComboBox()
        self.density_combo.addItems(["Comfortable", "Compact"])
        layout.addWidget(self.density_combo)

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
        scale_cfg = ui_scale.load_config()
        self.scale_combo.setCurrentText(f"{scale_cfg.scale_percent}%")
        density_label = "Compact" if scale_cfg.density == "compact" else "Comfortable"
        self.density_combo.setCurrentText(density_label)
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

            scale_percent = int(self.scale_combo.currentText().replace("%", ""))
            density = "compact" if self.density_combo.currentText().lower().startswith("compact") else "comfortable"
            scale_cfg = ui_scale.UiScaleConfig(scale_percent=scale_percent, density=density)
            ui_scale.save_config(scale_cfg)

            app = QtWidgets.QApplication.instance()
            applied = True
            if app:
                applied = apply_ui_config_styles(app)
                ui_scale.apply_to_app(app, scale_cfg)

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
# (moved to app_ui/screens/content_browser.py)
# endregion

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
# (moved to app_ui/screens/system_health.py)
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
            title=f"{terms.TOPIC} Management",
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
        self.table.setHorizontalHeaderLabels(
            [f"{terms.TOPIC} ID", "Repo?", "Store?", "Size", "Actions"]
        )
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
            install_btn = QtWidgets.QPushButton(f"Install {terms.TOPIC}")
            uninstall_btn = QtWidgets.QPushButton(f"Uninstall {terms.TOPIC}")
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
            QtWidgets.QMessageBox.information(self, "Topic", "Runtime bus unavailable.")
            return
        if self.pending_job_id:
            QtWidgets.QMessageBox.information(self, "Topic", "Another topic job is running.")
            return
        entry = self._module_index.get(module_id, {})
        if action == "install" and entry.get("store"):
            QtWidgets.QMessageBox.information(self, "Topic", "Topic already installed.")
            return
        if action == "uninstall" and not entry.get("store"):
            QtWidgets.QMessageBox.information(self, "Topic", "Topic already uninstalled.")
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
                "Topic job failed",
                f"{action.title()} {module_id}: {exc}",
                running=False,
                ok=False,
            )
            QtWidgets.QMessageBox.warning(self, "Topic", f"Request failed: {exc}")
            return
        if not response.get("ok") or not response.get("job_id"):
            self._set_job_state(job_id=None, module_id=None, action=None, running=False)
            self._show_progress_panel(
                "Topic job failed",
                f"{action.title()} {module_id}: {response.get('error') or 'unknown'}",
                running=False,
                ok=False,
            )
            QtWidgets.QMessageBox.warning(
                self,
                "Topic",
                f"Request failed: {response.get('error') or 'unknown'}",
            )
            return
        job_id = str(response["job_id"])
        self._set_job_state(job_id=job_id, module_id=module_id, action=action, running=True)
        self._show_progress_panel(
            "Topic job queued",
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
        module_id = payload.get("module_id") or self.pending_module_id or terms.TOPIC.lower()
        action = (self.pending_action or terms.TOPIC.lower()).title()
        details = f"{action} {module_id}: {percent_text} {stage}".strip()
        self._show_progress_panel("Topic Progress", details, running=True)
        self._set_status(details)

    def _on_module_completed_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if not self._is_active_payload(payload):
            return
        self._stop_job_poll_timer()
        ok = bool(payload.get("ok"))
        error = payload.get("error")
        module_id = payload.get("module_id") or self.pending_module_id or terms.TOPIC.lower()
        action = payload.get("action") or self.pending_action or terms.TOPIC.lower()
        summary = "OK" if ok else error or "failed"
        self._show_progress_panel(
            "Topic Result",
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
        module_id = self.pending_module_id or terms.TOPIC.lower()
        action = self.pending_action or terms.TOPIC.lower()
        summary = "OK" if ok else error or "failed"
        hub = get_global_hub()
        if hub:
            event = CodeSeeEvent(
                ts=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                kind=EVENT_JOB_UPDATE,
                severity="info" if ok else "error",
                message=f"{action.title()} {module_id}: {summary}",
                node_ids=["system:core_center"],
                source="app_ui",
            )
            hub.publish(event)
        self._show_progress_panel(
            "Topic Result",
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
                    "Topic job timeout",
                    f"{(self.pending_action or terms.TOPIC).title()} {self.pending_module_id or terms.TOPIC.lower()}: timed out waiting for completion",
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


# === [NAV-35] Screens: ComponentManagementScreen ============================
# region NAV-35 ComponentManagementScreen
# (moved to app_ui/screens/component_management.py)
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
        self.install_part_btn = QtWidgets.QPushButton(f"Install {terms.ACTIVITY.lower()}")
        self.install_part_btn.clicked.connect(self._install_part)
        self.install_part_btn.setVisible(False)
        self.install_module_btn = QtWidgets.QPushButton(f"Install {terms.TOPIC.lower()}")
        self.install_module_btn.clicked.connect(lambda: self._start_module_job("install"))
        self.uninstall_module_btn = QtWidgets.QPushButton(f"Uninstall {terms.TOPIC.lower()}")
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
            self._set_status(data.get("reason") or "Topic data unavailable.")
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
            [
                self._display_name(
                    module.get("title"),
                    module.get("module_id"),
                    terms.TOPIC,
                ),
                module_status,
            ]
        )
        module_item.setData(
            0,
            QtCore.Qt.ItemDataRole.UserRole,
            {
                "type": "module",
                "module_id": module.get("module_id"),
                "status": module_status,
                "reason": data.get("reason"),
            },
        )
        added_any = False
        for section in module.get("sections", []):
            sec_item = QtWidgets.QTreeWidgetItem(
                [
                    self._display_name(
                        section.get("title"),
                        section.get("section_id"),
                        terms.UNIT,
                    ),
                    section.get("status", ""),
                ]
            )
            sec_item.setData(
                0,
                QtCore.Qt.ItemDataRole.UserRole,
                {
                    "type": "section",
                    "status": section.get("status"),
                    "reason": section.get("reason"),
                },
            )
            sec_has_child = False
            for package in section.get("packages", []):
                pkg_item = QtWidgets.QTreeWidgetItem(
                    [
                        self._display_name(
                            package.get("title"),
                            package.get("package_id"),
                            terms.LESSON,
                        ),
                        package.get("status", ""),
                    ]
                )
                pkg_item.setData(
                    0,
                    QtCore.Qt.ItemDataRole.UserRole,
                    {
                        "type": "package",
                        "status": package.get("status"),
                        "reason": package.get("reason"),
                    },
                )
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
                        [
                            self._display_name(
                                part.get("title"),
                                part.get("part_id"),
                                terms.ACTIVITY,
                            ),
                            status,
                        ]
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
            self._set_status(f"No installed {terms.TOPIC.lower()}s yet. Install from {terms.TOPIC} Management.")
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
            reason = data.get("reason")
            workspace_disabled = bool(data.get("workspace_disabled"))
            if workspace_disabled:
                status = STATUS_UNAVAILABLE
                reason = WORKSPACE_DISABLED_REASON
            self.detail_title.setText(f"{terms.ACTIVITY} {part_id}")
            self.detail_status_pill.set_status(status)
            self.detail_status_pill.setVisible(True)
            self.detail_meta.setText(f"{terms.TOPIC}: {data.get('module_id') or 'physics'}")
            if workspace_disabled:
                self.detail_action.setText("Action: Enable pack in Project Management.")
            elif status == STATUS_READY:
                self.detail_action.setText("Action: Open in Content Browser.")
            else:
                self.detail_action.setText(f"Action: Install {terms.ACTIVITY.lower()}.")
            self.detail_hint.setText(self._format_reason(status, reason, workspace_disabled))
            self.install_part_btn.setVisible(status == STATUS_NOT_INSTALLED and not workspace_disabled)
            self.install_part_btn.setEnabled(status == STATUS_NOT_INSTALLED and not workspace_disabled)
            self.install_module_btn.setVisible(False)
            self.uninstall_module_btn.setVisible(False)
            self.pending_module_id = None
            self._selected_module_status = None
        elif node_type == "module":
            module_id = data.get("module_id") or terms.TOPIC.lower()
            self.detail_title.setText(f"{terms.TOPIC} {module_id}")
            module_status = data.get("status") or item.text(1) or STATUS_READY
            self.detail_status_pill.set_status(module_status)
            self.detail_status_pill.setVisible(True)
            self.detail_meta.setText(f"{terms.TOPIC} ID: {module_id}")
            if module_status == STATUS_READY:
                self.detail_action.setText(f"Action: Uninstall {terms.TOPIC}.")
            else:
                self.detail_action.setText(f"Action: Install {terms.TOPIC}.")
            self.detail_hint.setText(self._format_reason(module_status, data.get("reason"), False))
            self.install_part_btn.setVisible(False)
            self.install_module_btn.setVisible(module_status != STATUS_READY)
            self.uninstall_module_btn.setVisible(module_status == STATUS_READY)
            self.pending_module_id = module_id
            self._selected_module_status = module_status
            self._set_module_action_enabled()
        elif node_type == "section":
            section_id = item.text(0)
            self.detail_title.setText(f"{terms.UNIT} {section_id}")
            section_status = data.get("status") or item.text(1) or STATUS_READY
            self.detail_status_pill.set_status(section_status)
            self.detail_status_pill.setVisible(True)
            self.detail_meta.setText("")
            self.detail_action.setText(f"Select a {terms.LESSON.lower()} to manage {terms.ACTIVITY.lower()}s.")
            self.detail_hint.setText(self._format_reason(section_status, data.get("reason"), False))
            self.install_part_btn.setVisible(False)
            self.install_module_btn.setVisible(False)
            self.uninstall_module_btn.setVisible(False)
            self.pending_module_id = None
            self._selected_module_status = None
        elif node_type == "package":
            package_id = item.text(0)
            self.detail_title.setText(f"{terms.LESSON} {package_id}")
            package_status = data.get("status") or item.text(1) or STATUS_READY
            self.detail_status_pill.set_status(package_status)
            self.detail_status_pill.setVisible(True)
            self.detail_meta.setText("")
            self.detail_action.setText(f"Select an {terms.ACTIVITY.lower()} to manage content.")
            self.detail_hint.setText(self._format_reason(package_status, data.get("reason"), False))
            self.install_part_btn.setVisible(False)
            self.install_module_btn.setVisible(False)
            self.uninstall_module_btn.setVisible(False)
            self.pending_module_id = None
            self._selected_module_status = None
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

    def _format_reason(
        self,
        status: Optional[str],
        reason: Optional[str],
        workspace_disabled: bool,
    ) -> str:
        if status == STATUS_READY:
            return ""
        if not status and reason:
            return f"Reason: {reason}"
        if not status:
            return ""
        if workspace_disabled:
            return "Reason: Disabled by project (enable pack in Project Management)"
        if status == STATUS_NOT_INSTALLED:
            return "Reason: Not installed (install to content_store)"
        if reason:
            return f"Reason: {reason}"
        if status:
            return f"Reason: {status}"
        return "Reason: Unavailable"

    def _on_item_double_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole) or {}
        if data.get("type") != "part":
            return
        part_id = data.get("part_id")
        if part_id and self.on_open_part:
            if data.get("workspace_disabled"):
                QtWidgets.QMessageBox.information(self, "Project", WORKSPACE_DISABLED_REASON)
                return
            self.on_open_part(part_id)

    def _install_part(self) -> None:
        if not self.current_selection or self.current_selection.get("type") != "part":
            return
        if self.current_selection.get("workspace_disabled"):
            QtWidgets.QMessageBox.information(self, "Project", WORKSPACE_DISABLED_REASON)
            return
        if self.install_thread:
            return
        part_id = self.current_selection.get("part_id")
        self.progress_dialog = QtWidgets.QProgressDialog(
            f"Installing {terms.ACTIVITY.lower()}...", "", 0, 0, self
        )
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
            QtWidgets.QMessageBox.information(self, "Topic", "Select the topic first.")
            return
        if not self.bus:
            QtWidgets.QMessageBox.information(self, "Topic", "Runtime bus unavailable.")
            return
        if self.pending_job_id:
            QtWidgets.QMessageBox.information(self, "Topic", "Another topic job is running.")
            return
        if action == "install" and self._selected_module_status == STATUS_READY:
            QtWidgets.QMessageBox.information(self, "Topic", "Topic already installed.")
            return
        if action == "uninstall" and self._selected_module_status != STATUS_READY:
            QtWidgets.QMessageBox.information(self, "Topic", "Topic already uninstalled.")
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
                "Topic job failed",
                f"{action.title()} {module_id}: {exc}",
                running=False,
                ok=False,
            )
            QtWidgets.QMessageBox.warning(self, "Topic", f"Request failed: {exc}")
            return
        if not response.get("ok") or not response.get("job_id"):
            self._set_job_state(job_id=None, module_id=None, action=None, running=False)
            self._show_progress_panel(
                "Topic job failed",
                f"{action.title()} {module_id}: {response.get('error') or 'unknown'}",
                running=False,
                ok=False,
            )
            QtWidgets.QMessageBox.warning(
                self,
                "Topic",
                f"Request failed: {response.get('error') or 'unknown'}",
            )
            return
        job_id = str(response["job_id"])
        self._set_job_state(job_id=job_id, module_id=module_id, action=action, running=True)
        self._show_progress_panel(
            "Topic job queued",
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
        module_id = payload.get("module_id") or self.pending_module_id or terms.TOPIC.lower()
        action = (self.pending_action or terms.TOPIC.lower()).title()
        details = f"{action} {module_id}: {percent_text} {stage}".strip()
        self._show_progress_panel("Topic Progress", details, running=True)
        self._set_status(details)

    def _on_module_completed_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if not self._is_active_payload(payload):
            return
        ok = bool(payload.get("ok"))
        error = payload.get("error")
        module_id = payload.get("module_id") or self.pending_module_id or terms.TOPIC.lower()
        action = payload.get("action") or self.pending_action or terms.TOPIC.lower()
        summary = "OK" if ok else error or "failed"
        self._show_progress_panel(
            "Topic Result",
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
        module_id = self.pending_module_id or terms.TOPIC.lower()
        action = self.pending_action or terms.TOPIC.lower()
        summary = "OK" if ok else error or "failed"
        hub = get_global_hub()
        if hub:
            event = CodeSeeEvent(
                ts=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                kind=EVENT_JOB_UPDATE,
                severity="info" if ok else "error",
                message=f"{action.title()} {module_id}: {summary}",
                node_ids=["system:core_center"],
                source="app_ui",
            )
            hub.publish(event)
        self._show_progress_panel(
            "Topic Result",
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
                    "Topic job timeout",
                    f"{(self.pending_action or terms.TOPIC).title()} {self.pending_module_id or terms.TOPIC.lower()}: timed out waiting for completion",
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
        on_open_block: Optional[Callable[[str], None]],
        on_open_empty: Optional[Callable[[], None]],
        on_start_template: Optional[Callable[[Dict[str, Any]], None]] = None,
        *,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
    ):
        super().__init__()
        self.on_back = on_back
        self.context_provider = context_provider
        self.on_open_block = on_open_block
        self.on_open_empty = on_open_empty
        self.on_start_template = on_start_template
        self._templates: List[Dict[str, Any]] = []
        self._template_by_id: Dict[str, Dict[str, Any]] = {}
        self._component_pack_map: Dict[str, str] = {}
        self._installed_pack_ids: set[str] = set()
        self._available_pack_ids: set[str] = set()
        self._current_template_id: Optional[str] = None

        layout = QtWidgets.QVBoxLayout(self)
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title=f"{terms.BLOCK} Sandbox",
            on_back=self.on_back,
            workspace_selector=selector,
        )
        layout.addWidget(header)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: #444;")
        layout.addWidget(self.status_label)

        start_box = QtWidgets.QGroupBox("Start")
        start_layout = QtWidgets.QVBoxLayout(start_box)
        start_actions = QtWidgets.QHBoxLayout()
        self.start_empty_btn = QtWidgets.QPushButton("Start Empty")
        self.start_empty_btn.clicked.connect(self._start_empty)
        start_actions.addWidget(self.start_empty_btn)
        start_actions.addSpacing(12)
        start_actions.addWidget(QtWidgets.QLabel("Template:"))
        self.template_combo = QtWidgets.QComboBox()
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)
        start_actions.addWidget(self.template_combo, stretch=1)
        self.start_template_btn = QtWidgets.QPushButton("Start from Template")
        self.start_template_btn.clicked.connect(self._start_from_template)
        start_actions.addWidget(self.start_template_btn)
        start_layout.addLayout(start_actions)

        self.template_desc = QtWidgets.QLabel("Choose a template to see its recommended blocks.")
        self.template_desc.setStyleSheet("color: #555;")
        start_layout.addWidget(self.template_desc)
        self.template_list = QtWidgets.QListWidget()
        start_layout.addWidget(self.template_list)
        layout.addWidget(start_box)

        advanced_box = QtWidgets.QGroupBox("Advanced")
        advanced_box.setCheckable(True)
        advanced_box.setChecked(False)
        advanced_layout = QtWidgets.QHBoxLayout(advanced_box)

        component_panel = QtWidgets.QWidget()
        component_layout = QtWidgets.QVBoxLayout(component_panel)
        component_layout.setContentsMargins(0, 0, 0, 0)
        component_label = QtWidgets.QLabel(f"{terms.BLOCK}s")
        component_label.setStyleSheet("font-weight: bold;")
        component_layout.addWidget(component_label)
        self.component_list = QtWidgets.QListWidget()
        self.component_list.itemDoubleClicked.connect(self._open_selected)
        component_layout.addWidget(self.component_list, stretch=1)
        button_row = QtWidgets.QHBoxLayout()
        self.open_btn = QtWidgets.QPushButton("Open")
        self.open_btn.clicked.connect(self._open_selected)
        button_row.addWidget(self.open_btn)
        button_row.addStretch()
        component_layout.addLayout(button_row)

        lab_panel = QtWidgets.QWidget()
        lab_layout = QtWidgets.QVBoxLayout(lab_panel)
        lab_layout.setContentsMargins(0, 0, 0, 0)
        lab_label = QtWidgets.QLabel("Labs")
        lab_label.setStyleSheet("font-weight: bold;")
        lab_layout.addWidget(lab_label)
        self.lab_list = QtWidgets.QListWidget()
        self.lab_list.itemDoubleClicked.connect(self._open_selected_lab_component)
        lab_layout.addWidget(self.lab_list, stretch=1)
        lab_button_row = QtWidgets.QHBoxLayout()
        self.open_lab_btn = QtWidgets.QPushButton(
            f"Open selected lab as {terms.BLOCK.lower()}"
        )
        self.open_lab_btn.clicked.connect(self._open_selected_lab_component)
        lab_button_row.addWidget(self.open_lab_btn)
        lab_button_row.addStretch()
        lab_layout.addLayout(lab_button_row)

        pack_panel = QtWidgets.QWidget()
        pack_layout = QtWidgets.QVBoxLayout(pack_panel)
        pack_layout.setContentsMargins(0, 0, 0, 0)
        pack_label = QtWidgets.QLabel(f"{terms.PACK} {terms.BLOCK}s")
        pack_label.setStyleSheet("font-weight: bold;")
        pack_layout.addWidget(pack_label)
        self.pack_list = QtWidgets.QListWidget()
        self.pack_list.itemDoubleClicked.connect(self._open_selected_pack_component)
        pack_layout.addWidget(self.pack_list, stretch=1)
        pack_button_row = QtWidgets.QHBoxLayout()
        self.open_pack_btn = QtWidgets.QPushButton(
            f"Open selected {terms.PACK.lower()} {terms.BLOCK.lower()}"
        )
        self.open_pack_btn.clicked.connect(self._open_selected_pack_component)
        pack_button_row.addWidget(self.open_pack_btn)
        pack_button_row.addStretch()
        pack_layout.addLayout(pack_button_row)

        advanced_layout.addWidget(component_panel, stretch=1)
        advanced_layout.addWidget(lab_panel, stretch=1)
        advanced_layout.addWidget(pack_panel, stretch=1)
        layout.addWidget(advanced_box, stretch=1)

        self.refresh_components()
        self._load_templates()
        self._refresh_template_summary()

    def on_workspace_changed(self) -> None:
        self.status_label.setText("Project changed. Refreshing available blocks.")
        self.refresh_components()
        self._refresh_template_summary()

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
        self._component_pack_map = {}
        self._installed_pack_ids = set()
        self._available_pack_ids = set()
        if component_packs is not None:
            try:
                pack_manifests = component_packs.list_repo_packs()
            except Exception:
                pack_manifests = []
            try:
                installed = component_packs.list_installed_packs()
            except Exception:
                installed = []
            self._installed_pack_ids = {
                str(pack.get("pack_id") or "").strip()
                for pack in installed
                if pack.get("pack_id")
            }
        registry = component_registry.get_registry()
        for meta in registry.list_components():
            openable, status, _reason = self._component_status(str(meta.component_id))
            label = f"{meta.display_name} ({meta.component_id}) - {status}"
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, meta.component_id)
            if not openable:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.component_list.addItem(item)
        for lab_id, plugin in lab_registry.list_labs().items():
            title = getattr(plugin, "title", lab_id)
            item = QtWidgets.QListWidgetItem(f"{title} ({lab_id})")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, lab_id)
            component_id = f"labhost:{lab_id}"
            openable, status, _reason = self._component_status(component_id)
            if status != "Enabled":
                item.setText(f"{title} ({lab_id}) - {status}")
            if not openable:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.lab_list.addItem(item)
        for pack in pack_manifests:
            manifest = pack.get("manifest") if isinstance(pack, dict) else None
            if not isinstance(manifest, dict):
                continue
            pack_id = manifest.get("pack_id") or "pack"
            self._available_pack_ids.add(str(pack_id))
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
                self._component_pack_map[str(component_id)] = str(pack_id)
                openable, status, _reason = self._component_status(str(component_id))
                label = f"{display_name} ({component_id}) [{pack_id}] - {status}"
                item = QtWidgets.QListWidgetItem(label)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, component_id)
                if not openable:
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
                self.pack_list.addItem(item)

    def _component_status(self, component_id: str) -> tuple[bool, str, str]:
        if component_registry is None:
            return False, "Unavailable", "Block runtime unavailable."
        policy = _get_global_component_policy()
        pack_id = self._component_pack_map.get(component_id)
        if pack_id and pack_id not in self._installed_pack_ids:
            return False, "Not installed", f"Install the {terms.PACK.lower()} to use this block."
        if policy and pack_id and not policy.is_pack_enabled(pack_id):
            return False, "Disabled by project", "Enable this Pack in Project Settings."
        if policy and not policy.is_component_enabled(component_id):
            return False, "Disabled by project", "Enable this Pack in Project Settings."
        component = component_registry.get_registry().get_component(component_id)
        if not component:
            return False, "Unavailable", "Block not registered."
        return True, "Enabled", "Enabled in this project."

    def _start_empty(self) -> None:
        if self.on_open_empty:
            self.on_open_empty()
        self.status_label.setText("Opened an empty block host.")

    def _on_template_changed(self) -> None:
        idx = self.template_combo.currentIndex()
        template_id = self.template_combo.itemData(idx)
        self._current_template_id = template_id if isinstance(template_id, str) else None
        self._refresh_template_summary()

    def _refresh_template_summary(self) -> None:
        template = self._template_by_id.get(self._current_template_id) if self._current_template_id else None
        if not template:
            self.template_desc.setText("Choose a template to see its recommended blocks.")
            self.template_list.clear()
            return
        title = template.get("title") or template.get("id") or "Template"
        desc = template.get("description") or "No description provided."
        self.template_desc.setText(f"{title}: {desc}")
        self.template_list.clear()
        for component_id in template.get("recommended_blocks") or []:
            if not isinstance(component_id, str):
                continue
            openable, status, reason = self._component_status(component_id)
            label = f"{component_id} - {status}"
            item = QtWidgets.QListWidgetItem(label)
            item.setToolTip(reason)
            if not openable:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.template_list.addItem(item)

    def _start_from_template(self) -> None:
        template = self._template_by_id.get(self._current_template_id) if self._current_template_id else None
        if not template:
            self.status_label.setText("Select a template to start.")
            return
        if self.on_start_template:
            self.on_start_template(template)
            title = template.get("title") or template.get("id") or "Template"
            self.status_label.setText(f"Started template: {title}")
            return
        if self.on_open_empty:
            self.on_open_empty()
        open_first = template.get("open_first")
        candidates = [open_first] if isinstance(open_first, str) else []
        for component_id in template.get("recommended_blocks") or []:
            if isinstance(component_id, str) and component_id not in candidates:
                candidates.append(component_id)
        for component_id in candidates:
            openable, _status, reason = self._component_status(component_id)
            if openable and self.on_open_block:
                self.on_open_block(component_id)
                self.status_label.setText(f"Opened template block: {component_id}")
                return
            if not openable:
                self.status_label.setText(reason)
        self.status_label.setText("No available blocks for this template.")

    def _load_templates(self) -> None:
        self._templates = []
        self._template_by_id = {}
        template_root = Path("app_ui/templates/block_sandbox")
        try:
            template_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            return
        for path in sorted(template_root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            template_id = data.get("id")
            if not isinstance(template_id, str) or not template_id:
                continue
            self._templates.append(data)
            self._template_by_id[template_id] = data
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        self.template_combo.addItem("Select a template...", None)
        for template in self._templates:
            title = template.get("title") or template.get("id")
            self.template_combo.addItem(str(title), template.get("id"))
        self.template_combo.blockSignals(False)

    def _open_selected(self) -> None:
        if component_registry is None or not self.on_open_block:
            return
        item = self.component_list.currentItem()
        if not item:
            self.status_label.setText("Select a block to open.")
            return
        component_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        openable, _status, reason = self._component_status(str(component_id))
        if not openable:
            self.status_label.setText(reason)
            return
        self.on_open_block(str(component_id))
        self.status_label.setText(f"Opened block: {component_id}")

    def _open_selected_lab_component(self) -> None:
        if component_registry is None or not self.on_open_block:
            return
        item = self.lab_list.currentItem()
        if not item:
            self.status_label.setText("Select a lab to open as a block.")
            return
        lab_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        component_id = f"labhost:{lab_id}"
        openable, _status, reason = self._component_status(component_id)
        if not openable:
            self.status_label.setText(reason)
            return
        self.on_open_block(component_id)
        self.status_label.setText(f"Opened lab block: {lab_id}")

    def _open_selected_pack_component(self) -> None:
        if component_registry is None or not self.on_open_block:
            return
        item = self.pack_list.currentItem()
        if not item:
            self.status_label.setText("Select a pack block to open.")
            return
        component_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        openable, _status, reason = self._component_status(str(component_id))
        if not openable:
            self.status_label.setText(reason)
            return
        self.on_open_block(str(component_id))
        self.status_label.setText(f"Opened pack block: {component_id}")


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
            title=f"{terms.BLOCK} Viewer",
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
            msg = "Block runtime unavailable."
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
            self.status_label.setText(f"Block '{component_id}' is not registered.")
            return
        self._host.mount(component, context)
        self.status_label.setText(f"Opened block: {component_id}")

    def show_empty_state(self, message: str = "No blocks added yet.") -> None:
        if self._host is None:
            return
        self._host.unmount()
        self.status_label.setText(message)

    def _close_component(self) -> None:
        if self._host is None:
            return
        self._host.unmount()
        self.status_label.setText("Block closed.")


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
        build = versioning.get_build_info()
        self.setWindowTitle(
            f"PhysicsLab V1 - {build.get('app_version', 'unknown')} ({build.get('build_id', 'unknown')})"
        )
        self.resize(900, 600)
        self.adapter = ContentSystemAdapter()
        self.current_profile = initial_profile
        self.codesee_hub = CodeSeeRuntimeHub()
        set_global_hub(self.codesee_hub)
        install_exception_hooks(self.codesee_hub)
        self.codesee_window: Optional[CodeSeeWindow] = None
        self._codesee_context: str = "Main Menu"
        self.codesee_bus_bridge: Optional[BusBridge] = None

        self.stacked = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stacked)
        self.lab_widget: Optional[QtWidgets.QWidget] = None
        self.lab_host_widget: Optional[QtWidgets.QWidget] = None
        self.workspace_info: Dict[str, Any] = self._ensure_workspace_context()
        if self.codesee_hub:
            self.codesee_hub.set_workspace_id((self.workspace_info or {}).get("id") or "default")
        if APP_BUS and self.codesee_hub:
            self.codesee_bus_bridge = BusBridge(
                APP_BUS,
                self.codesee_hub,
                workspace_id_provider=lambda: (self.workspace_info or {}).get("id") or "default",
            )
            self.codesee_bus_bridge.start()
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
            self._open_block_catalog,
            self._open_code_see,
            self._open_code_see_window,
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
            log_handler=_agent_debug_log,
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
            on_open_component_management=self._open_component_management,
            on_open_block_catalog=self._open_block_catalog,
            on_open_module_management=self._show_module_management,
            on_open_content_management=self._open_content_management,
            log_handler=_agent_debug_log,
        )
        self.component_sandbox = ComponentSandboxScreen(
            self._show_main_menu,
            self._build_component_context,
            self._add_block_to_host,
            self._open_block_host_empty,
            self._start_block_template,
            workspace_selector_factory=selector_factory,
        )
        self.block_host = BlockHostScreen(
            on_back=self._show_main_menu,
            context_provider=self._build_component_context,
            prefs_root_provider=self._active_workspace_prefs_root,
            workspace_selector_factory=selector_factory,
            component_policy_provider=self._get_component_policy,
            open_picker=self._open_block_picker,
        )
        self.block_catalog = BlockCatalogScreen(
            on_back=self._show_main_menu,
            on_open_block=self._add_block_to_host,
            workspace_selector_factory=selector_factory,
            component_policy_provider=self._get_component_policy,
            bus=APP_BUS,
        )
        self.codesee = CodeSeeScreen(
            on_back=self._show_main_menu,
            workspace_info_provider=self._get_workspace_info,
            bus=APP_BUS,
            content_adapter=self.adapter,
            workspace_selector_factory=selector_factory,
            runtime_hub=self.codesee_hub,
            on_open_window=self._open_code_see_window,
        )
        try:
            self.codesee.set_screen_context(self._codesee_context)
        except Exception:
            pass
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
        self.stacked.addWidget(self.block_host)
        self.stacked.addWidget(self.block_catalog)
        self.stacked.addWidget(self.codesee)
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
        restore_window_geometry(self, "main")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[name-defined]
        if self.codesee_bus_bridge:
            try:
                self.codesee_bus_bridge.stop()
            except Exception:
                pass
        save_window_geometry(self, "main")
        super().closeEvent(event)

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

    def _get_workspace_info(self) -> Dict[str, Any]:
        return self.workspace_info if isinstance(self.workspace_info, dict) else {}

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
            QtWidgets.QMessageBox.warning(self, "Project", "Runtime bus unavailable.")
            return False
        try:
            response = APP_BUS.request(
                BUS_WORKSPACE_SET_ACTIVE_REQUEST,
                {"workspace_id": workspace_id},
                source="app_ui",
                timeout_ms=1500,
            )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Project", f"Set active failed: {exc}")
            return False
        if not response.get("ok"):
            QtWidgets.QMessageBox.warning(
                self, "Project", response.get("error") or "Set active failed."
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
        if self.codesee and self.stacked.currentWidget() == self.codesee:
            try:
                self.codesee.save_layout()
            except Exception:
                pass
        self.stacked.setCurrentWidget(self.main_menu)
        self._publish_codesee_event("Main Menu", node_ids=["system:app_ui"])

    def _publish_codesee_event(self, message: str, *, node_ids: Optional[List[str]] = None) -> None:
        if not self.codesee_hub:
            return
        self._codesee_context = message
        if hasattr(self, "codesee") and self.codesee:
            try:
                self.codesee.set_screen_context(message)
            except Exception:
                pass
        if self.codesee_window:
            try:
                self.codesee_window.screen.set_screen_context(message)
            except Exception:
                pass
        event = CodeSeeEvent(
            ts=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            kind=EVENT_APP_ACTIVITY,
            severity="info",
            message=message,
            node_ids=node_ids or ["system:app_ui"],
            source="app_ui",
        )
        self.codesee_hub.publish(event)

    def _on_workspace_changed(self, workspace: Dict[str, Any], *, notify_bus: bool = True) -> None:
        if self.codesee:
            try:
                self.codesee.save_layout()
            except Exception:
                pass
        if self.codesee_window:
            try:
                self.codesee_window.screen.save_layout()
            except Exception:
                pass
        if isinstance(workspace, dict):
            self.workspace_info = workspace
        if self.codesee_hub:
            self.codesee_hub.set_workspace_id((self.workspace_info or {}).get("id") or "default")
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
        if self.block_host:
            try:
                self.block_host.on_workspace_changed()
            except Exception:
                pass
        if self.block_catalog:
            try:
                self.block_catalog.on_workspace_changed()
            except Exception:
                pass
        if self.codesee:
            try:
                self.codesee.on_workspace_changed()
            except Exception:
                pass
        if self.codesee_window:
            try:
                self.codesee_window.screen.on_workspace_changed()
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
            self.content_management._set_status(f"Install a {terms.TOPIC.lower()} to begin.")
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
        self._publish_codesee_event("Content Browser", node_ids=["system:app_ui"])
        return selected

    def _show_content_browser(self):
        self._dispose_lab_widget()
        self.stacked.setCurrentWidget(self.content_browser)
        self._publish_codesee_event("Content Browser", node_ids=["system:app_ui"])

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
            self._publish_codesee_event("Content Management", node_ids=["system:app_ui"])

    def _open_diagnostics(self):
        self._dispose_lab_widget()
        if self.system_health:
            self.system_health.prepare()
            self.stacked.setCurrentWidget(self.system_health)
            self._publish_codesee_event("Diagnostics", node_ids=["system:app_ui"])

    def _open_component_management(self):
        self._dispose_lab_widget()
        if self.component_management:
            self.component_management.refresh()
            self.stacked.setCurrentWidget(self.component_management)
            self._publish_codesee_event("Pack Management", node_ids=["system:app_ui"])

    def _open_component_sandbox(self):
        self._dispose_lab_widget()
        if not COMPONENT_RUNTIME_AVAILABLE:
            QtWidgets.QMessageBox.warning(self, "Blocks", "Block runtime unavailable.")
            return
        if self.component_sandbox:
            self.component_sandbox.refresh_components()
            self.stacked.setCurrentWidget(self.component_sandbox)
            self._publish_codesee_event("Block Sandbox", node_ids=["system:app_ui"])

    def _open_block_catalog(self):
        self._dispose_lab_widget()
        if not COMPONENT_RUNTIME_AVAILABLE:
            QtWidgets.QMessageBox.warning(self, "Blocks", "Block runtime unavailable.")
            return
        if self.block_catalog:
            self.block_catalog.refresh_catalog()
            self.stacked.setCurrentWidget(self.block_catalog)
            self._publish_codesee_event("Block Catalog", node_ids=["system:app_ui"])

    def _open_code_see(self) -> None:
        self._dispose_lab_widget()
        if self.current_profile != "Explorer":
            return
        if self.codesee:
            self.codesee.open_root()
            self.stacked.setCurrentWidget(self.codesee)
            self._publish_codesee_event("Code See", node_ids=["system:app_ui"])

    def _open_code_see_window(self) -> None:
        if self.current_profile != "Explorer":
            return
        if self.codesee_window is not None:
            self.codesee_window.raise_()
            self.codesee_window.activateWindow()
            return
        self.codesee_window = CodeSeeWindow(
            workspace_info_provider=self._get_workspace_info,
            bus=APP_BUS,
            content_adapter=self.adapter,
            runtime_hub=self.codesee_hub,
            workspace_selector_factory=self._make_workspace_selector,
            on_close=self._on_codesee_window_closed,
        )
        self.codesee_window.show()
        try:
            self.codesee_window.screen.set_screen_context(self._codesee_context)
        except Exception:
            pass
        self._publish_codesee_event("Code See (Window)", node_ids=["system:app_ui"])

    def _on_codesee_window_closed(self) -> None:
        self.codesee_window = None

    def _open_component_by_id(self, component_id: str) -> None:
        self._dispose_lab_widget()
        if not COMPONENT_RUNTIME_AVAILABLE or self.component_host is None:
            QtWidgets.QMessageBox.warning(self, "Blocks", "Block runtime unavailable.")
            return
        context = self._build_component_context()
        if not self.workspace_component_policy.is_component_enabled(component_id):
            QtWidgets.QMessageBox.information(
                self,
                "Block",
                "Disabled by project. Enable this Pack in Project Settings.",
            )
            return
        self.component_host.open_component(component_id, context)
        self.stacked.setCurrentWidget(self.component_host)

    def _open_block_host_empty(self) -> None:
        self._dispose_lab_widget()
        if not COMPONENT_RUNTIME_AVAILABLE or self.block_host is None:
            QtWidgets.QMessageBox.warning(self, "Blocks", "Block runtime unavailable.")
            return
        self.block_host.open_empty()
        self.stacked.setCurrentWidget(self.block_host)

    def _add_block_to_host(self, component_id: str) -> None:
        self._dispose_lab_widget()
        if not COMPONENT_RUNTIME_AVAILABLE or self.block_host is None:
            QtWidgets.QMessageBox.warning(self, "Blocks", "Block runtime unavailable.")
            return
        if not self.workspace_component_policy.is_component_enabled(component_id):
            QtWidgets.QMessageBox.information(
                self,
                "Block",
                "Disabled by project. Enable this Pack in Project Settings.",
            )
            return
        self.block_host.add_block(component_id, activate=True)
        self.stacked.setCurrentWidget(self.block_host)

    def _start_block_template(self, template: Dict[str, Any]) -> None:
        self._dispose_lab_widget()
        if not COMPONENT_RUNTIME_AVAILABLE or self.block_host is None:
            QtWidgets.QMessageBox.warning(self, "Blocks", "Block runtime unavailable.")
            return
        self.block_host.start_template(template)
        self.stacked.setCurrentWidget(self.block_host)

    def _open_block_picker(self, on_pick: Callable[[str], None]) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"{terms.BLOCK} Catalog")
        dialog.resize(900, 600)
        layout = QtWidgets.QVBoxLayout(dialog)

        def _handle_pick(component_id: str) -> None:
            on_pick(component_id)
            dialog.accept()

        picker = BlockCatalogScreen(
            on_back=dialog.reject,
            on_open_block=None,
            on_pick=_handle_pick,
            workspace_selector_factory=self._make_workspace_selector,
            component_policy_provider=self._get_component_policy,
            bus=APP_BUS,
        )
        layout.addWidget(picker)
        dialog.exec()

    def _open_component_from_part(
        self,
        component_id: str,
        part_id: Optional[str],
        manifest: Dict[str, Any],
        detail: Dict[str, Any],
    ) -> None:
        self._dispose_lab_widget()
        if not COMPONENT_RUNTIME_AVAILABLE or self.component_host is None:
            QtWidgets.QMessageBox.warning(self, "Blocks", "Block runtime unavailable.")
            return
        context = self._build_component_context(part_id=part_id, detail=detail)
        if not self.workspace_component_policy.is_component_enabled(component_id):
            QtWidgets.QMessageBox.information(self, "Block", WORKSPACE_DISABLED_REASON)
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
        self._publish_codesee_event(f"Lab Opened: {title}", node_ids=["system:app_ui"])

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
def _run_app(argv: List[str], *, safe_viewer: bool) -> int:
    app = QtWidgets.QApplication(argv)
    _install_qt_message_filter()
    apply_ui_config_styles(app)
    scale_cfg = ui_scale.load_config()
    ui_scale.apply_to_app(app, scale_cfg)
    if safe_viewer:
        from app_ui.safe_viewer import SafeViewerWindow

        window = SafeViewerWindow()
    else:
        profile = ui_config.load_experience_profile()
        print(f"Experience profile: {profile}")
        window = MainWindow(profile)
    window.show()
    return app.exec()


def main():
    safe_viewer = "--safe-viewer" in sys.argv
    argv = [arg for arg in sys.argv if arg != "--safe-viewer"]
    if safe_viewer:
        sys.exit(_run_app(argv, safe_viewer=True))
    try:
        sys.exit(_run_app(argv, safe_viewer=False))
    except Exception as exc:
        print("Startup failed during normal boot.")
        try:
            import platform
            import traceback
            from app_ui.codesee import crash_io

            workspace_id = crash_io.best_effort_workspace_id()
            build_info = versioning.get_build_info()
            record = {
                "format_version": 1,
                "ts": time.time(),
                "workspace_id": workspace_id,
                "where": "startup",
                "exception_type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
                "build": build_info,
                "app": {
                    "python": sys.version,
                    "platform": platform.platform(),
                    "pid": os.getpid(),
                },
            }
            path = crash_io.write_latest_crash(workspace_id, record)
            crash_io.write_history_crash(workspace_id, record)
            print(f"Crash record written: {path}")
        except Exception as write_exc:
            print(f"Crash record write failed: {write_exc}")
        print("Tip: python -m app_ui.main --safe-viewer")
        raise


if __name__ == "__main__":
    main()
# endregion
