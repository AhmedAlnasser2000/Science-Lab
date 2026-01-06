import sys
import time
from datetime import datetime
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app_ui import config as ui_config
from app_ui.widgets.app_header import AppHeader
from app_ui.widgets.workspace_selector import WorkspaceSelector
from app_ui.ui_helpers import terms
from tools.pillars_report import find_latest_report, load_report
from tools.pillars_harness import run_pillars
from app_ui.diagnostics.providers import (
    DiagnosticsContext,
    DiagnosticsProvider,
    list_providers,
    register_provider,
)

try:
    from runtime_bus import topics as BUS_TOPICS
except Exception:  # pragma: no cover - defensive
    BUS_TOPICS = None

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

try:
    from content_system.validation import clear_validation_cache, get_validation_report
except Exception:  # pragma: no cover - defensive
    get_validation_report = None
    clear_validation_cache = None

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
BUS_INVENTORY_REQUEST = (
    BUS_TOPICS.CORE_INVENTORY_GET_REQUEST if BUS_TOPICS else "core.inventory.get.request"
)
BUS_JOBS_LIST_REQUEST = (
    BUS_TOPICS.CORE_JOBS_LIST_REQUEST if BUS_TOPICS else "core.jobs.list.request"
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
BUS_MODULE_PROGRESS = (
    BUS_TOPICS.CONTENT_INSTALL_PROGRESS if BUS_TOPICS else "content.install.progress"
)
BUS_MODULE_COMPLETED = (
    BUS_TOPICS.CONTENT_INSTALL_COMPLETED if BUS_TOPICS else "content.install.completed"
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
BUS_WORKSPACE_GET_ACTIVE_REQUEST = (
    BUS_TOPICS.CORE_WORKSPACE_GET_ACTIVE_REQUEST
    if BUS_TOPICS
    else "core.workspace.get_active.request"
)

CORE_JOB_REPORT = "core.report.generate"


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
        self._pillars_thread: Optional[QtCore.QThread] = None
        self._pillars_worker: Optional[TaskWorker] = None
        self._pillars_report_path: Optional[Path] = None
        self._pillars_report: Optional[Dict[str, Any]] = None
        self._pillars_fail_only = False
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
        self._segment_pillars_btn = _make_segment("Pillars", 1)
        self._segment_runs_btn = _make_segment("Runs", 2)
        self._segment_maintenance_btn = _make_segment("Maintenance", 3)
        self._segment_modules_btn = _make_segment(f"{terms.TOPIC}s", 4)
        self._segment_content_btn = _make_segment("Content", 5)
        self._segment_jobs_btn = _make_segment("Jobs", 6)
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

        self.pillars_summary_card = QtWidgets.QFrame()
        self.pillars_summary_card.setStyleSheet(
            "QFrame { border: 1px solid #ddd; border-radius: 4px; padding: 6px; }"
        )
        pillars_card_layout = QtWidgets.QHBoxLayout(self.pillars_summary_card)
        pillars_title = QtWidgets.QLabel("Pillars Status")
        pillars_title.setStyleSheet("font-weight: bold;")
        pillars_card_layout.addWidget(pillars_title)
        self.pillars_summary_label = QtWidgets.QLabel("No report found yet.")
        pillars_card_layout.addWidget(self.pillars_summary_label)
        pillars_card_layout.addStretch()
        self.pillars_open_btn = QtWidgets.QPushButton("Open Pillars")
        self.pillars_open_btn.clicked.connect(lambda: self._set_segment(1))
        pillars_card_layout.addWidget(self.pillars_open_btn)
        page_overview_layout.addWidget(self.pillars_summary_card)

        providers_panel = QtWidgets.QFrame()
        providers_panel.setStyleSheet(
            "QFrame { border: 1px solid #ddd; border-radius: 4px; padding: 6px; }"
        )
        providers_layout = QtWidgets.QVBoxLayout(providers_panel)
        providers_layout.setContentsMargins(8, 4, 8, 6)
        header_row = QtWidgets.QHBoxLayout()
        providers_title = QtWidgets.QLabel("Diagnostics Providers")
        providers_title.setStyleSheet("font-weight: bold;")
        header_row.addWidget(providers_title)
        header_row.addStretch()
        providers_layout.addLayout(header_row)
        self._providers_list_layout = QtWidgets.QVBoxLayout()
        providers_layout.addLayout(self._providers_list_layout)
        page_overview_layout.addWidget(providers_panel)

        self.report_view = QtWidgets.QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setPlaceholderText("Storage report will appear here.")
        page_overview_layout.addWidget(self.report_view, stretch=1)
        self._stack.addWidget(page_overview)

        page_pillars = QtWidgets.QWidget()
        page_pillars_layout = QtWidgets.QVBoxLayout(page_pillars)
        page_pillars_layout.setContentsMargins(0, 0, 0, 0)

        pillars_header = QtWidgets.QLabel("Pillars Status")
        pillars_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        page_pillars_layout.addWidget(pillars_header)

        self.pillars_last_updated = QtWidgets.QLabel("Last updated: —")
        self.pillars_report_path = QtWidgets.QLabel("Last report: —")
        self.pillars_report_path.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.pillars_summary_line = QtWidgets.QLabel("PASS: 0  FAIL: 0  SKIP: 0")
        page_pillars_layout.addWidget(self.pillars_last_updated)
        page_pillars_layout.addWidget(self.pillars_report_path)
        page_pillars_layout.addWidget(self.pillars_summary_line)

        pillars_toolbar = QtWidgets.QHBoxLayout()
        self.pillars_filter_group = QtWidgets.QButtonGroup(self)
        self.pillars_filter_all_btn = QtWidgets.QPushButton("All")
        self.pillars_filter_all_btn.setCheckable(True)
        self.pillars_filter_fail_btn = QtWidgets.QPushButton("Fail only")
        self.pillars_filter_fail_btn.setCheckable(True)
        self.pillars_filter_group.setExclusive(True)
        self.pillars_filter_group.addButton(self.pillars_filter_all_btn)
        self.pillars_filter_group.addButton(self.pillars_filter_fail_btn)
        self.pillars_filter_all_btn.setChecked(True)
        self.pillars_filter_all_btn.clicked.connect(lambda: self._set_pillars_filter(False))
        self.pillars_filter_fail_btn.clicked.connect(lambda: self._set_pillars_filter(True))
        pillars_toolbar.addWidget(self.pillars_filter_all_btn)
        pillars_toolbar.addWidget(self.pillars_filter_fail_btn)
        pillars_toolbar.addSpacing(12)
        self.pillars_open_folder_btn = QtWidgets.QPushButton("Open report folder")
        self.pillars_open_folder_btn.clicked.connect(self._open_pillars_folder)
        pillars_toolbar.addWidget(self.pillars_open_folder_btn)
        self.pillars_copy_path_btn = QtWidgets.QPushButton("Copy report path")
        self.pillars_copy_path_btn.clicked.connect(self._copy_pillars_path)
        pillars_toolbar.addWidget(self.pillars_copy_path_btn)
        self.pillars_copy_summary_btn = QtWidgets.QPushButton("Copy summary")
        self.pillars_copy_summary_btn.clicked.connect(self._copy_pillars_summary)
        pillars_toolbar.addWidget(self.pillars_copy_summary_btn)
        self.pillars_run_btn = QtWidgets.QPushButton("Run pillars checks")
        self.pillars_run_btn.clicked.connect(self._run_pillars_checks)
        pillars_toolbar.addWidget(self.pillars_run_btn)
        pillars_toolbar.addStretch()
        page_pillars_layout.addLayout(pillars_toolbar)

        self.pillars_empty_state = QtWidgets.QFrame()
        empty_layout = QtWidgets.QVBoxLayout(self.pillars_empty_state)
        empty_label = QtWidgets.QLabel(
            "No pillars report found yet. Run the checks to generate one."
        )
        empty_label.setStyleSheet("color: #666;")
        empty_layout.addWidget(empty_label)
        self.pillars_empty_run_btn = QtWidgets.QPushButton("Run pillars checks")
        self.pillars_empty_run_btn.clicked.connect(self._run_pillars_checks)
        empty_layout.addWidget(self.pillars_empty_run_btn)
        empty_layout.addStretch()
        page_pillars_layout.addWidget(self.pillars_empty_state)

        self.pillars_table = QtWidgets.QTableWidget(0, 4)
        self.pillars_table.setHorizontalHeaderLabels(["ID", "Title", "Status", "Reason"])
        self.pillars_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.pillars_table.horizontalHeader().setSectionResizeMode(
            3, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.pillars_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pillars_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        page_pillars_layout.addWidget(self.pillars_table, stretch=1)

        self.pillars_log = QtWidgets.QPlainTextEdit()
        self.pillars_log.setReadOnly(True)
        self.pillars_log.setPlaceholderText("Pillars run output will appear here.")
        self.pillars_log.setMaximumHeight(120)
        page_pillars_layout.addWidget(self.pillars_log)

        self._stack.addWidget(page_pillars)

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
        self.runs_delete_all_workspace_btn = QtWidgets.QPushButton("Delete All (Project)")
        self.runs_delete_all_workspace_btn.clicked.connect(self._delete_all_runs_for_workspace)
        runs_toolbar.addWidget(self.runs_delete_all_workspace_btn)
        self.runs_workspace_label = QtWidgets.QLabel(f"{terms.PROJECT}: ?")
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
        self.install_btn = QtWidgets.QPushButton(f"Install {terms.TOPIC.lower()} (local)")
        self.install_btn.clicked.connect(lambda: self._start_module_job("install"))
        self.uninstall_btn = QtWidgets.QPushButton(f"Uninstall {terms.TOPIC.lower()} (local)")
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
        self.module_title = QtWidgets.QLabel(f"{terms.TOPIC} Status")
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

        page_content = QtWidgets.QWidget()
        page_content_layout = QtWidgets.QVBoxLayout(page_content)
        page_content_layout.setContentsMargins(0, 0, 0, 0)
        content_toolbar = QtWidgets.QHBoxLayout()
        self.content_diag_refresh_btn = QtWidgets.QPushButton("Refresh validation")
        self.content_diag_refresh_btn.clicked.connect(lambda: self._refresh_content_diagnostics(force=True))
        content_toolbar.addWidget(self.content_diag_refresh_btn)
        self.content_diag_copy_btn = QtWidgets.QPushButton("Copy details")
        self.content_diag_copy_btn.clicked.connect(self._copy_content_diagnostics)
        content_toolbar.addWidget(self.content_diag_copy_btn)
        content_toolbar.addStretch()
        page_content_layout.addLayout(content_toolbar)
        self.content_diag_status = QtWidgets.QLabel("Content diagnostics unavailable.")
        self.content_diag_status.setStyleSheet("color: #555;")
        page_content_layout.addWidget(self.content_diag_status)
        self.content_diag_tree = QtWidgets.QTreeWidget()
        self.content_diag_tree.setColumnCount(2)
        self.content_diag_tree.setHeaderLabels(["Item", "Detail"])
        header_view = self.content_diag_tree.header()
        header_view.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        page_content_layout.addWidget(self.content_diag_tree, stretch=1)
        self._content_diag_report: Optional[Dict[str, Any]] = None
        self._stack.addWidget(page_content)
        self._content_page_index = self._stack.count() - 1

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
        self._ensure_default_providers()
        self._render_providers()
        self._refresh_pillars_view()

    def prepare(self) -> None:
        if self.refresh_capability and self._pending_initial_refresh:
            self._refresh_report()
        self._update_comm_controls()
        if self.bus and not self._inventory_checked:
            self._refresh_inventory()
        self._refresh_content_diagnostics()
        self._refresh_pillars_view()

    def _set_segment(self, index: int) -> None:
        if index < 0 or index >= self._stack.count():
            return
        self._stack.setCurrentIndex(index)
        for idx, btn in enumerate(self._segment_buttons):
            btn.setChecked(idx == index)
        if index == getattr(self, "_content_page_index", -1):
            self._refresh_content_diagnostics()
        if index == 1:
            self._refresh_pillars_view()

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
        if hasattr(self, "content_diag_refresh_btn"):
            self.content_diag_refresh_btn.setEnabled(bool(enabled))
        if hasattr(self, "content_diag_copy_btn"):
            self.content_diag_copy_btn.setEnabled(bool(enabled))
        self._update_pillars_controls()
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
        module_id = self.pending_module_id or terms.TOPIC.lower()
        if hasattr(self, "install_btn"):
            self.install_btn.setText(f"Install {module_id} topic (local)")
        if hasattr(self, "uninstall_btn"):
            self.uninstall_btn.setText(f"Uninstall {module_id} topic (local)")

    def _refresh_inventory(self) -> None:
        self._inventory_checked = True
        if not self.bus:
            self._module_installed = None
            self._update_module_button_labels()
            self._set_control_enabled(True)
            return

    def _ensure_default_providers(self) -> None:
        if getattr(SystemHealthScreen, "_providers_registered", False):
            return
        provider = DiagnosticsProvider(
            id="pillars_status",
            title="Pillars Status",
            is_available=lambda ctx: True,
            create_widget=SystemHealthScreen._build_pillars_status_widget,
        )
        register_provider(provider)
        SystemHealthScreen._providers_registered = True

    def _render_providers(self) -> None:
        if not hasattr(self, "_providers_list_layout"):
            return
        ctx = DiagnosticsContext(workspace_id="default", data_root=str(Path("data")))
        layout = self._providers_list_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for provider in list_providers(ctx):
            card = QtWidgets.QFrame()
            card.setStyleSheet(
                "QFrame { border: 1px solid #e1e1e1; border-radius: 4px; padding: 6px; }"
            )
            card_layout = QtWidgets.QVBoxLayout(card)
            title_row = QtWidgets.QHBoxLayout()
            title_lbl = QtWidgets.QLabel(provider.title)
            title_lbl.setStyleSheet("font-weight: bold;")
            title_row.addWidget(title_lbl)
            title_row.addStretch()
            card_layout.addLayout(title_row)
            widget = provider.create_widget(ctx) if provider.create_widget else None
            if widget is not None:
                card_layout.addWidget(widget)
            else:
                card_layout.addWidget(QtWidgets.QLabel("Provider unavailable."))
            layout.addWidget(card)
        layout.addStretch()

    @staticmethod
    def _find_latest_pillars_report() -> Optional[Path]:
        candidates = []
        base = Path("data/roaming")
        candidates.append(base / "pillars_report.json")
        candidates.append(base / "pillars_report_latest.json")
        if base.exists():
            candidates.extend(sorted(base.glob("pillars_report*.json"), key=lambda p: p.stat().st_mtime, reverse=True))
        for path in candidates:
            if path.exists():
                return path
        return None

    @staticmethod
    def _build_pillars_status_widget(ctx: DiagnosticsContext) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        info_label = QtWidgets.QLabel()
        info_label.setWordWrap(True)
        report_path = SystemHealthScreen._find_latest_pillars_report()
        if report_path:
            info_label.setText(f"Latest pillars_report.json: {report_path}")
            target_folder = report_path.parent
        else:
            info_label.setText("No pillars report found yet. Run the pillars harness to generate one.")
            target_folder = Path(ctx.data_root) if ctx and ctx.data_root else Path("data/roaming")
        layout.addWidget(info_label)
        open_btn = QtWidgets.QPushButton("Open report folder")
        open_btn.setEnabled(target_folder.exists())
        open_btn.clicked.connect(
            lambda: QtGui.QDesktopServices.openUrl(
                QtCore.QUrl.fromLocalFile(str(target_folder.resolve()))
            )
        )
        layout.addWidget(open_btn)
        layout.addStretch()
        return widget
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

    def _update_pillars_controls(self) -> None:
        profile = ui_config.load_experience_profile()
        allow_run = profile in {"Explorer", "Educator"}
        if hasattr(self, "pillars_run_btn"):
            self.pillars_run_btn.setEnabled(bool(allow_run))
            if not allow_run:
                self.pillars_run_btn.setToolTip("Available for Explorer and Educator profiles.")
            else:
                self.pillars_run_btn.setToolTip("")
        if hasattr(self, "pillars_empty_run_btn"):
            self.pillars_empty_run_btn.setEnabled(bool(allow_run))

    def _refresh_pillars_view(self) -> None:
        report_dir = Path("data/roaming/pillars_reports")
        report_path = find_latest_report(report_dir)
        self._pillars_report_path = report_path
        self._pillars_report = None

        if report_path and report_path.exists():
            try:
                self._pillars_report = load_report(report_path)
            except Exception:
                self._pillars_report = None

        self._render_pillars_summary()
        self._render_pillars_table()

    def _set_pillars_filter(self, fail_only: bool) -> None:
        self._pillars_fail_only = bool(fail_only)
        self._render_pillars_table()

    def _render_pillars_summary(self) -> None:
        report = self._pillars_report
        if report and self._pillars_report_path:
            mtime = self._pillars_report_path.stat().st_mtime
            timestamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        else:
            timestamp = "—"
        if hasattr(self, "pillars_last_updated"):
            self.pillars_last_updated.setText(f"Last updated: {timestamp}")
        if hasattr(self, "pillars_report_path"):
            if self._pillars_report_path:
                self.pillars_report_path.setText(f"Last report: {self._pillars_report_path}")
            else:
                self.pillars_report_path.setText("Last report: —")

        summary = {"PASS": 0, "FAIL": 0, "SKIP": 0}
        if report:
            for entry in report.get("results") or []:
                status = (entry.get("status") or "").upper()
                if status in summary:
                    summary[status] += 1
        summary_text = f"PASS: {summary['PASS']}  FAIL: {summary['FAIL']}  SKIP: {summary['SKIP']}"
        if hasattr(self, "pillars_summary_line"):
            self.pillars_summary_line.setText(summary_text)
        if hasattr(self, "pillars_summary_label"):
            self.pillars_summary_label.setText(summary_text)

        has_report = bool(report)
        if hasattr(self, "pillars_empty_state"):
            self.pillars_empty_state.setVisible(not has_report)
        if hasattr(self, "pillars_table"):
            self.pillars_table.setVisible(has_report)
        if hasattr(self, "pillars_open_folder_btn"):
            self.pillars_open_folder_btn.setEnabled(bool(self._pillars_report_path))
        if hasattr(self, "pillars_copy_path_btn"):
            self.pillars_copy_path_btn.setEnabled(bool(self._pillars_report_path))
        if hasattr(self, "pillars_copy_summary_btn"):
            self.pillars_copy_summary_btn.setEnabled(bool(self._pillars_report_path))

    def _render_pillars_table(self) -> None:
        report = self._pillars_report
        table = getattr(self, "pillars_table", None)
        if table is None:
            return
        table.setRowCount(0)
        if not report:
            return
        results = report.get("results") or []
        if self._pillars_fail_only:
            results = [r for r in results if (r.get("status") or "").upper() == "FAIL"]
        table.setRowCount(len(results))
        for row, entry in enumerate(results):
            pillar_id = entry.get("id") or entry.get("pillar_id") or ""
            title = entry.get("title") or entry.get("name") or ""
            status = entry.get("status") or ""
            reason = entry.get("reason") or entry.get("details") or ""
            id_item = QtWidgets.QTableWidgetItem(str(pillar_id))
            title_item = QtWidgets.QTableWidgetItem(str(title))
            status_item = QtWidgets.QTableWidgetItem(str(status))
            reason_item = QtWidgets.QTableWidgetItem(str(reason))
            if reason:
                reason_item.setToolTip(str(reason))
            status_upper = str(status).upper()
            if status_upper == "PASS":
                status_item.setBackground(QtGui.QColor("#d7f2d7"))
            elif status_upper == "FAIL":
                status_item.setBackground(QtGui.QColor("#f6d4d4"))
            elif status_upper == "SKIP":
                status_item.setBackground(QtGui.QColor("#e8e8e8"))
            table.setItem(row, 0, id_item)
            table.setItem(row, 1, title_item)
            table.setItem(row, 2, status_item)
            table.setItem(row, 3, reason_item)

    def _open_pillars_folder(self) -> None:
        if not self._pillars_report_path:
            return
        folder = self._pillars_report_path.parent
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(folder.resolve())))

    def _copy_pillars_path(self) -> None:
        if not self._pillars_report_path:
            return
        QtWidgets.QApplication.clipboard().setText(str(self._pillars_report_path))

    def _copy_pillars_summary(self) -> None:
        report = self._pillars_report
        if not report:
            return
        summary = {"PASS": 0, "FAIL": 0, "SKIP": 0}
        for entry in report.get("results") or []:
            status = (entry.get("status") or "").upper()
            if status in summary:
                summary[status] += 1
        text = f"PASS: {summary['PASS']}  FAIL: {summary['FAIL']}  SKIP: {summary['SKIP']}"
        QtWidgets.QApplication.clipboard().setText(text)

    def _run_pillars_checks(self) -> None:
        if self._pillars_thread is not None:
            return

        def _run() -> Dict[str, Any]:
            log_path = Path("data/roaming/pillars_run_latest.log")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            out_dir = Path("data/roaming/pillars_reports")
            cmd = f"{sys.executable} tools/pillars_harness.py --out {out_dir}"
            started = datetime.now().isoformat()
            success = False
            report_path: Optional[Path] = None
            error = ""
            traceback_text = ""
            try:
                report_path = run_pillars(out_dir)
                success = True
            except SystemExit as exc:
                error = f"SystemExit: {exc}"
            except Exception as exc:
                error = f"{exc}"
                traceback_text = traceback.format_exc()
            log_lines = [
                f"started_at: {started}",
                f"command: {cmd}",
                f"success: {success}",
                f"report_path: {report_path or ''}",
            ]
            if error:
                log_lines.append(f"error: {error}")
            if traceback_text:
                log_lines.append("traceback:")
                log_lines.append(traceback_text)
            log_path.write_text("\n".join(log_lines))
            return {
                "success": success,
                "report_path": str(report_path) if report_path else "",
                "error": error,
                "log_path": str(log_path),
            }

        self.pillars_log.setPlainText("Running pillars checks...\n")
        if hasattr(self, "pillars_run_btn"):
            self.pillars_run_btn.setEnabled(False)
        if hasattr(self, "pillars_empty_run_btn"):
            self.pillars_empty_run_btn.setEnabled(False)
        worker = TaskWorker(_run)
        thread = QtCore.QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_pillars_run_finished)
        worker.error.connect(self._on_pillars_run_error)
        worker.error.connect(thread.quit)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_pillars_thread_finished)
        self._pillars_worker = worker
        self._pillars_thread = thread
        thread.start()

    def _on_pillars_run_finished(self, payload: Dict[str, Any]) -> None:
        success = payload.get("success", False)
        error = payload.get("error") or ""
        log_path = payload.get("log_path") or ""
        report_path = payload.get("report_path") or ""
        if success:
            text = f"Pillars run completed.\nReport: {report_path}".strip()
        else:
            text = f"Pillars run failed.\nError: {error}\nLog: {log_path}".strip()
        self.pillars_log.setPlainText(text)
        self._update_pillars_controls()
        if success:
            self._refresh_pillars_view()

    def _on_pillars_run_error(self, message: str) -> None:
        log_path = Path("data/roaming/pillars_run_latest.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(f"started_at: {datetime.now().isoformat()}\nerror: {message}\n")
        self.pillars_log.setPlainText(
            f"Pillars run failed: {message}\nLog: {log_path}"
        )
        self._update_pillars_controls()

    def _on_pillars_thread_finished(self) -> None:
        if self._pillars_thread:
            self._pillars_thread.deleteLater()
        if self._pillars_worker:
            self._pillars_worker.deleteLater()
        self._pillars_thread = None
        self._pillars_worker = None
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
        self.runs_workspace_label.setText(f"{terms.PROJECT}: {workspace_id}")

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
            self.runs_status.setText("No runs in this project.")
            return
        total_bytes = sum(item.get("size_bytes") or 0 for item in items)
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete all runs",
            f"Delete all runs in this project ({len(items)} runs, ~{total_bytes/1024/1024:.2f} MB)?",
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
            QtWidgets.QMessageBox.information(self, "Topic", "Runtime bus unavailable.")
            return
        if self._module_job_running:
            QtWidgets.QMessageBox.information(self, "Topic", "Another topic job is running.")
            return
        if not self.pending_module_id:
            QtWidgets.QMessageBox.information(self, "Topic", "No topic id available.")
            return
        if action == "install" and self._module_installed is True:
            QtWidgets.QMessageBox.information(self, "Topic", "Topic already installed.")
            return
        if action == "uninstall" and self._module_installed is False:
            QtWidgets.QMessageBox.information(self, "Topic", "Topic already uninstalled.")
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
                "Topic job failed",
                f"{action.title()} {self._format_module_job_label()}: {exc}",
                running=False,
                ok=False,
            )
            QtWidgets.QMessageBox.warning(self, "Topic", f"Request failed: {exc}")
            return
        if not response.get("ok") or not response.get("job_id"):
            self._set_module_job_state(job_id=None, action=None, running=False)
            self._show_module_panel(
                "Topic job failed",
                f"{action.title()} {self._format_module_job_label()}: {response.get('error') or 'unknown'}",
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
        self._set_module_job_state(job_id=job_id, action=action, running=True)
        self._show_module_panel(
            "Topic job queued",
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
                "Topic job timeout",
                f"{(self.pending_module_action or terms.TOPIC).title()} {self.pending_module_id}: timed out waiting for completion",
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
        action = (self.pending_module_action or terms.TOPIC.lower()).title()
        details = f"{action} {self._format_module_job_label()}: {percent_text} {stage}".strip()
        self._show_module_panel("Topic Progress", details, running=True)

    def _handle_module_completed_ui(self, payload: Dict[str, Any]) -> None:
        if not self._is_active_module_payload(payload):
            return
        self._stop_module_poll_timer()
        ok = bool(payload.get("ok"))
        action = payload.get("action") or (self.pending_module_action or terms.TOPIC.lower())
        error = payload.get("error")
        summary = "OK" if ok else error or "failed"
        job_label = self._format_module_job_label()
        self._set_module_job_state(job_id=None, action=None, running=False)
        self._show_module_panel(
            "Topic Result",
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
        if self._pillars_thread and self._pillars_thread.isRunning():
            self._pillars_thread.quit()
            self._pillars_thread.wait(2000)
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

    def _refresh_content_diagnostics(self, *, force: bool = False) -> None:
        if not callable(get_validation_report):
            self.content_diag_status.setText("Content diagnostics unavailable.")
            if hasattr(self, "content_diag_tree"):
                self.content_diag_tree.clear()
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
        if force and callable(clear_validation_cache):
            clear_validation_cache()
            try:
                import content_system

                content_system.list_tree()
            except Exception:
                pass
        span_id = None
        if callable(publish_span_start_global) and SpanStart:
            span_id = f"content.validation.{workspace_id}.{int(time.time() * 1000)}"
            publish_span_start_global(
                SpanStart(
                    span_id=span_id,
                    label="Content validation",
                    node_id="system:content_system",
                    source_id="system:content_system",
                    severity=None,
                    ts=time.time(),
                )
            )
        report = get_validation_report(limit=100)
        self._content_diag_report = report
        ok_count = report.get("ok_count", 0)
        warn_count = report.get("warn_count", 0)
        fail_count = report.get("fail_count", 0)
        self.content_diag_status.setText(
            f"Validation summary: OK={ok_count} WARN={warn_count} FAIL={fail_count}"
        )
        if span_id and callable(publish_span_update_global) and SpanUpdate:
            publish_span_update_global(
                SpanUpdate(
                    span_id=span_id,
                    progress=1.0,
                    message=f"OK={ok_count} WARN={warn_count} FAIL={fail_count}",
                    ts=time.time(),
                )
            )
        if span_id and callable(publish_span_end_global) and SpanEnd:
            status = "completed" if fail_count == 0 else "failed"
            publish_span_end_global(
                SpanEnd(
                    span_id=span_id,
                    status=status,
                    ts=time.time(),
                    message=f"Validation {status}: OK={ok_count} WARN={warn_count} FAIL={fail_count}",
                )
            )
        if callable(build_check) and callable(publish_expect_check_global):
            expected = {"failures": 0, "warnings": 0}
            actual = {"failures": fail_count, "warnings": warn_count}
            message = (
                "Validation clean."
                if fail_count == 0 and warn_count == 0
                else f"Validation issues: FAIL={fail_count}, WARN={warn_count}."
            )
            check = build_check(
                check_id="content.validation.summary",
                node_id="system:content_system",
                expected=expected,
                actual=actual,
                mode="exact",
                message=message,
                context={
                    "action": "validate",
                    "workspace_id": workspace_id,
                    "ok_count": ok_count,
                    "fail_count": fail_count,
                    "warn_count": warn_count,
                },
            )
            publish_expect_check_global(check)
        failures = report.get("failures") or []
        warnings = report.get("warnings") or []
        tree = self.content_diag_tree
        tree.clear()
        if not failures and not warnings:
            tree.addTopLevelItem(
                QtWidgets.QTreeWidgetItem(["No validation issues recorded.", ""])
            )
            return

        def _add_group(label: str, items: list[dict]) -> None:
            group = QtWidgets.QTreeWidgetItem([label, f"{len(items)} item(s)"])
            tree.addTopLevelItem(group)
            grouped: Dict[str, list[dict]] = {}
            for entry in items:
                manifest_type = entry.get("manifest_type") or "unknown"
                grouped.setdefault(manifest_type, []).append(entry)
            for manifest_type, entries in grouped.items():
                m_node = QtWidgets.QTreeWidgetItem(
                    [manifest_type, f"{len(entries)} item(s)"]
                )
                group.addChild(m_node)
                for entry in entries:
                    summary = entry.get("error_summary") or "issue"
                    node = QtWidgets.QTreeWidgetItem([summary, entry.get("json_path") or ""])
                    m_node.addChild(node)
                    node.addChild(QtWidgets.QTreeWidgetItem(["Path", entry.get("path") or ""]))
                    node.addChild(
                        QtWidgets.QTreeWidgetItem(["Schema", entry.get("schema_id") or ""])
                    )
                    node.addChild(
                        QtWidgets.QTreeWidgetItem(
                            ["JSON path", entry.get("json_path") or "$"]
                        )
                    )
            group.setExpanded(True)

        if failures:
            _add_group("Failures", failures)
        if warnings:
            _add_group("Warnings", warnings)
        tree.expandToDepth(1)

    def _copy_content_diagnostics(self) -> None:
        report = self._content_diag_report or {}
        lines: list[str] = []
        lines.append("Content validation report")
        lines.append(
            f"OK={report.get('ok_count', 0)} "
            f"WARN={report.get('warn_count', 0)} "
            f"FAIL={report.get('fail_count', 0)}"
        )
        failures = report.get("failures") or []
        warnings = report.get("warnings") or []
        if warnings:
            lines.append("")
            lines.append("Warnings:")
            for item in warnings:
                lines.append(
                    f"- {item.get('manifest_type')} {item.get('path')} "
                    f"{item.get('error_summary')} ({item.get('json_path') or '$'}) "
                    f"[{item.get('schema_id') or 'no schema'}]"
                )
        if failures:
            lines.append("")
            lines.append("Failures:")
            for item in failures:
                lines.append(
                    f"- {item.get('manifest_type')} {item.get('path')} "
                    f"{item.get('error_summary')} ({item.get('json_path') or '$'}) "
                    f"[{item.get('schema_id') or 'no schema'}]"
                )
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))
