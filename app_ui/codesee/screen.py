# =============================================================================
# NAV INDEX (search these tags)
# [NAV-00] Imports / constants
# [NAV-05] Stable re-exports for tests (lens palette + helpers)
# [NAV-20] CodeSeeScreen
# [NAV-30] CodeSeeScreen: graph navigation + layout persistence
# [NAV-40] CodeSeeScreen: lens palette integration (dock/float/pin/persist)
# [NAV-60] CodeSeeScreen: overlays + rendering helpers
# [NAV-70] CodeSeeScreen: UI density + status tick + runtime events
# [NAV-80] CodeSeeScreen: snapshots/diff/crash/presets (dialogs + actions)
# [NAV-90] Module helpers (toggle/buttons/labels/filters/spans/badges)
# [NAV-99] Smoke test entrypoints
# =============================================================================

# === [NAV-00] Imports / constants ============================================
# region NAV-00 Imports / constants
from __future__ import annotations

import base64
from dataclasses import dataclass
import functools
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app_ui import config as ui_config
from app_ui.widgets.app_header import AppHeader
from app_ui.widgets.workspace_selector import WorkspaceSelector

from . import (
    crash_io,
    diagnostics,
    harness,
    icon_pack,
    view_config,
)
from .badges import Badge, badge_from_key, sort_by_priority
from .canvas.items import NodeItem, clear_icon_cache
from .canvas.scene import GraphScene
from .canvas.view import GraphView
from .collectors.atlas_builder import build_atlas_graph
from .collectors.base import CollectorContext
from .demos.demo_graphs import build_demo_root_graph, build_demo_subgraphs
from .dialogs import diagnostics_dialog
from .diff import DiffResult, NodeChange, diff_snapshots
from .expectations import EVACheck, check_from_dict
from .graph_model import ArchitectureGraph, Edge, Node
from .lenses import LENS_ATLAS, LENS_BUS, LENS_CONTENT, LENS_PLATFORM, LensSpec, get_lens, get_lenses
from .item_ref import ItemRef, itemref_display_name, itemref_from_node
from .peek import (
    MAX_PEEK_ADD_PER_EXPAND,
    MAX_PEEK_VISIBLE_TOTAL,
    PeekContext,
    apply_expand_budget,
    breadcrumb_chain_ids,
    build_containment_index,
    collapse_subtree_ids,
    has_unloaded_subgraph,
    item_ref_for_node_id,
)
from .relations import RelationIndex, build_relation_index, query_relation_page
from .runtime.events import (
    CodeSeeEvent,
    EVENT_APP_ACTIVITY,
    EVENT_APP_CRASH,
    EVENT_APP_ERROR,
    EVENT_BUS_REPLY,
    EVENT_BUS_REQUEST,
    EVENT_EXPECT_CHECK,
    EVENT_JOB_UPDATE,
    EVENT_SPAN_END,
    EVENT_SPAN_START,
    EVENT_SPAN_UPDATE,
    EVENT_TEST_PULSE,
    SpanRecord,
)
# --- [NAV-05] Stable re-exports for tests (lens palette + helpers)
from .runtime.hub import CodeSeeRuntimeHub
from .runtime.monitor_state import MonitorState
from .storage import layout_store, snapshot_index, snapshot_io
from .dialogs.inspector import _span_is_stuck
from .dialogs.facet_settings import open_facet_settings
from .dialogs.pulse_settings import open_pulse_settings
from .dialogs.removed import CodeSeeRemovedDialog
from .ui.lens_palette import (
    LensPaletteWidget,
    _filter_lens_tiles,
    _lens_palette_lens_ids,
    lens_palette_dock_orientation,
)
from .ui.inspector_panel import CodeSeeInspectorPanel
from .util import log_buffer
from app_ui import ui_scale
from app_ui import versioning

DEFAULT_LENS = LENS_ATLAS
LENS_EXT = "extensibility"
SOURCE_DEMO = "System Map"
SOURCE_ATLAS = "Atlas"
SOURCE_SNAPSHOT = "Snapshot (Latest)"
ICON_STYLE_LABELS = {
    icon_pack.ICON_STYLE_AUTO: "Auto",
    icon_pack.ICON_STYLE_COLOR: "Color",
    icon_pack.ICON_STYLE_MONO: "Mono",
}
MONITOR_TRACE_COLOR = QtGui.QColor("#4c6ef5")

FACET_NODE_TYPE = "Facet"
FACET_EDGE_KIND = "facet"
FACET_EDGE_RELATION = "facet_of"
FACET_META_KEY = "codesee_facet"
FACET_KEYS_ACTIVITY = {"logs", "activity", "spans", "runs", "errors", "signals"}
FACET_KEYS_RELATIONS = {"deps", "packs", "entry_points"}
FACET_TO_RELATION_CATEGORY = {
    "deps": "depends_on",
    "packs": "contains",
    "entry_points": "exports",
}
FACET_LABELS = {
    "deps": "Dependencies",
    "packs": "Packs",
    "entry_points": "Entry points",
    "logs": "Logs",
    "activity": "Activity",
    "spans": "Spans",
    "runs": "Runs",
    "errors": "Errors",
    "signals": "Signals",
}
FACET_SOURCE_HINT = "Facet nodes are curated for System Map (Demo) right now. Switch Source -> Demo."
# endregion NAV-00 Imports / constants


@dataclass(frozen=True)
class FacetSelection:
    facet_id: str
    base_node_id: str
    facet_key: str
    facet_label: str

# === [NAV-20] CodeSeeScreen ===================================================
# region NAV-20 CodeSeeScreen
class CodeSeeScreen(QtWidgets.QWidget):
    def __init__(
        self,
        on_back: Callable[[], None],
        workspace_info_provider: Callable[[], Dict[str, Any]],
        *,
        bus=None,
        content_adapter=None,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
        runtime_hub: Optional[CodeSeeRuntimeHub] = None,
        on_open_window: Optional[Callable[[], None]] = None,
        allow_detach: bool = True,
        safe_mode: bool = False,
        crash_view: bool = False,
        dock_host: Optional[QtWidgets.QMainWindow] = None,
    ) -> None:
        super().__init__()
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.on_back = on_back
        self._workspace_info_provider = workspace_info_provider
        self._bus = bus
        self._content_adapter = content_adapter
        self._runtime_hub = runtime_hub
        self._on_open_window = on_open_window
        self._allow_detach = allow_detach
        self._safe_mode = bool(safe_mode)
        self._crash_view = bool(crash_view)
        self._crash_record: Optional[dict] = None
        self._crash_node_id: Optional[str] = None
        self._lens = view_config.load_last_lens_id(self._workspace_id()) or DEFAULT_LENS
        self._reduced_motion = ui_config.get_reduced_motion()
        self._view_config = view_config.load_view_config(self._workspace_id(), self._lens)
        self._icon_style = self._view_config.icon_style
        self._node_theme = self._view_config.node_theme
        self._pulse_settings = self._view_config.pulse_settings
        self._facet_settings = self._view_config.facet_settings
        self._build_info = versioning.get_build_info()
        palette_state = view_config.load_lens_palette_state(self._workspace_id())
        self._lens_palette_pinned = bool(palette_state.get("pinned", False))
        self._lens_palette_recent = list(palette_state.get("recent", []))
        self._lens_palette: Optional[LensPaletteWidget] = None
        self._diagnostics_dialog: Optional[diagnostics_dialog.CodeSeeDiagnosticsDialog] = None
        self._lens_palette_visible = bool(palette_state.get("palette_visible", False))
        self._lens_palette_event_filter_installed = False
        self.selected_item: Optional[ItemRef] = None
        self.inspected_item: Optional[ItemRef] = None
        self.inspector_locked = False
        self.inspected_history: list[ItemRef] = []
        self.inspected_history_index = -1
        self._peek = PeekContext()
        self._peek_warning: str = ""
        self._peek_node_map: Dict[str, Node] = {}
        self._peek_children_by_id: Dict[str, list[str]] = {}
        self._render_node_map: Dict[str, Node] = {}
        self._facet_selection_by_id: Dict[str, FacetSelection] = {}
        self._active_facet_selection: Optional[FacetSelection] = None
        self._facet_scope_multi_hint_key: Optional[str] = None
        self._relation_index_normal: Optional[RelationIndex] = None
        self._relation_index_normal_key: Optional[tuple] = None
        self._relation_index_compare: Optional[RelationIndex] = None
        self._relation_index_compare_key: Optional[tuple] = None
        self._inspector_relations_state_key: Optional[tuple] = None
        self._inspector_panel: Optional[CodeSeeInspectorPanel] = None
        self._inspector_dock: Optional[QtWidgets.QDockWidget] = None
        if self._runtime_hub:
            self._runtime_hub.set_workspace_id(self._workspace_id())

        self._demo_root = build_demo_root_graph()
        self._demo_subgraphs = build_demo_subgraphs()
        self._atlas_root: Optional[ArchitectureGraph] = None
        self._atlas_subgraphs: Dict[str, ArchitectureGraph] = {}
        self._snapshot_graph: Optional[ArchitectureGraph] = None

        self._active_root: Optional[ArchitectureGraph] = self._demo_root
        self._active_subgraphs: Dict[str, ArchitectureGraph] = self._demo_subgraphs
        self._source = self._normalize_source_value(SOURCE_SNAPSHOT if self._safe_mode else SOURCE_DEMO)
        self._graph_stack: list[str] = [self._demo_root.graph_id]
        self._current_graph_id: Optional[str] = None
        self._current_graph: Optional[ArchitectureGraph] = None
        self._render_graph_id: Optional[str] = None
        self._snapshot_entries: list[dict] = []
        self._diff_mode = False
        self._diff_result: Optional[DiffResult] = None
        self._diff_baseline_graph: Optional[ArchitectureGraph] = None
        self._diff_compare_graph: Optional[ArchitectureGraph] = None
        self._diff_filters: Dict[str, bool] = {
            "only_added": False,
            "only_removed": False,
            "only_changed": False,
        }
        self._live_enabled = bool(self._view_config.live_enabled)
        self._monitor_enabled = bool(self._view_config.monitor_enabled)
        self._monitor_follow_last_trace = bool(self._view_config.monitor_follow_last_trace)
        self._monitor_show_edge_path = bool(self._view_config.monitor_show_edge_path)
        self._monitor = MonitorState(
            span_stuck_seconds=int(self._view_config.span_stuck_seconds),
            follow_last_trace=self._monitor_follow_last_trace,
        )
        self._monitor_active_trace_id: Optional[str] = None
        self._monitor_trace_pinned = False
        self._events_by_node: Dict[str, list[CodeSeeEvent]] = {}
        self._overlay_badges: Dict[str, list[Badge]] = {}
        self._overlay_limit = 8
        self._runtime_connected = False
        self._screen_context: Optional[str] = None
        self._overlay_checks: Dict[str, list[EVACheck]] = {}
        self._status_timer = QtCore.QTimer(self)
        self._status_timer.setInterval(1000)
        self._status_timer.timeout.connect(self._on_status_tick)
        self._last_span_pulse = 0.0

        self._dock_host_external = dock_host is not None
        if dock_host is not None:
            self._dock_host = dock_host
        else:
            self._dock_host = QtWidgets.QMainWindow(self)
            self._dock_host.setObjectName("codeseeDockHost")
            self._dock_host.setDockNestingEnabled(False)
            self._dock_host.setWindowFlags(QtCore.Qt.WindowType.Widget)
            self._dock_host.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
        self._dock_host.setDockOptions(
            QtWidgets.QMainWindow.DockOption.AnimatedDocks
            | QtWidgets.QMainWindow.DockOption.AllowNestedDocks
            | QtWidgets.QMainWindow.DockOption.AllowTabbedDocks
            | QtWidgets.QMainWindow.DockOption.GroupedDragging
        )
        self._dock_container = QtWidgets.QWidget()
        self._dock_container.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        layout = QtWidgets.QVBoxLayout(self._dock_container)
        self._root_layout = layout
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(title="Code See", on_back=self._handle_back, workspace_selector=selector)
        layout.addWidget(header)

        breadcrumb_row = QtWidgets.QHBoxLayout()
        self._breadcrumb_row = breadcrumb_row
        self.back_btn = QtWidgets.QPushButton("Back")
        self.back_btn.clicked.connect(self._back_to_parent)
        breadcrumb_row.addWidget(self.back_btn)
        self.breadcrumb_container = QtWidgets.QWidget()
        self.breadcrumb_layout = QtWidgets.QHBoxLayout(self.breadcrumb_container)
        self.breadcrumb_layout.setContentsMargins(0, 0, 0, 0)
        breadcrumb_row.addWidget(self.breadcrumb_container, stretch=1)
        self.lens_label = QtWidgets.QLabel("")
        self.lens_label.setStyleSheet("color: #555;")
        breadcrumb_row.addWidget(self.lens_label)
        layout.addLayout(breadcrumb_row)

        self.peek_row = QtWidgets.QWidget()
        self.peek_row_layout = QtWidgets.QHBoxLayout(self.peek_row)
        self.peek_row_layout.setContentsMargins(0, 0, 0, 0)
        self.peek_row_layout.setSpacing(8)
        self.peek_breadcrumb_label = QtWidgets.QLabel("Peek: (inactive)")
        self.peek_breadcrumb_label.setStyleSheet("color: #355070; font-weight: 600;")
        self.peek_row_layout.addWidget(self.peek_breadcrumb_label, stretch=1)
        self.peek_exit_btn = QtWidgets.QToolButton()
        self.peek_exit_btn.setText("Exit Peek")
        self.peek_exit_btn.clicked.connect(self._exit_peek)
        self.peek_row_layout.addWidget(self.peek_exit_btn)
        self.peek_collapse_all_btn = QtWidgets.QToolButton()
        self.peek_collapse_all_btn.setText("Collapse all")
        self.peek_collapse_all_btn.clicked.connect(self._collapse_all_peek)
        self.peek_row_layout.addWidget(self.peek_collapse_all_btn)
        self.peek_reset_btn = QtWidgets.QToolButton()
        self.peek_reset_btn.setText("Reset view")
        self.peek_reset_btn.clicked.connect(self._reset_peek_view)
        self.peek_row_layout.addWidget(self.peek_reset_btn)
        self.peek_external_toggle = QtWidgets.QToolButton()
        self.peek_external_toggle.setText("Include 1-hop external context")
        self.peek_external_toggle.setCheckable(True)
        self.peek_external_toggle.setEnabled(False)
        self.peek_external_toggle.setToolTip("Coming later in V5.5d5.")
        self.peek_row_layout.addWidget(self.peek_external_toggle)
        self.peek_row.setVisible(False)
        layout.addWidget(self.peek_row)

        source_row = QtWidgets.QHBoxLayout()
        self._source_row = source_row
        source_row.addWidget(QtWidgets.QLabel("Lens:"))
        self.lens_palette_btn = QtWidgets.QToolButton()
        self.lens_palette_btn.setText("Lenses")
        self.lens_palette_btn.setToolTip("Open lens palette (L)")
        self.lens_palette_btn.setCheckable(True)
        self.lens_palette_btn.clicked.connect(self._on_lens_palette_button_clicked)
        self.lens_palette_btn.setStyleSheet(
            "QToolButton { background: #1e88e5; color: #fff; border-radius: 4px; padding: 3px 8px; }"
            "QToolButton:checked { background: #1565c0; }"
        )
        source_row.addWidget(self.lens_palette_btn)
        self.lens_combo = QtWidgets.QComboBox()
        self._lens_map = get_lenses()
        self._lens_map[LENS_EXT] = LensSpec(LENS_EXT, "Extensibility/Dependencies", _ext_nodes, _ext_edges)
        for lens_id in _lens_palette_lens_ids():
            lens = self._lens_map.get(lens_id)
            if lens:
                self.lens_combo.addItem(lens.title, lens_id)
        self.lens_combo.currentIndexChanged.connect(self._on_lens_changed)
        source_row.addWidget(self.lens_combo)
        source_row.addWidget(QtWidgets.QLabel("Source:"))
        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.addItems([SOURCE_DEMO, SOURCE_ATLAS, SOURCE_SNAPSHOT])
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        self.source_combo.blockSignals(True)
        self.source_combo.setCurrentText(self._normalize_source_value(self._source))
        self.source_combo.blockSignals(False)
        source_row.addWidget(self.source_combo)
        self.snapshot_button = QtWidgets.QToolButton()
        self.snapshot_button.setText("Snapshots")
        self.snapshot_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.snapshot_menu = QtWidgets.QMenu(self.snapshot_button)
        self.snapshot_button.setMenu(self.snapshot_menu)
        source_row.addWidget(self.snapshot_button)
        self.capture_btn = QtGui.QAction("Capture Snapshot", self.snapshot_menu)
        self.capture_btn.triggered.connect(self._capture_snapshot)
        self.load_btn = QtGui.QAction("Load Latest Snapshot", self.snapshot_menu)
        self.load_btn.triggered.connect(self._load_latest_snapshot_action)
        self.baseline_combo = QtWidgets.QComboBox()
        self.baseline_combo.currentIndexChanged.connect(self._on_baseline_changed)
        self.compare_combo = QtWidgets.QComboBox()
        self.compare_combo.currentIndexChanged.connect(self._on_compare_changed)
        self.live_toggle = QtWidgets.QToolButton()
        self.live_toggle.setText("Live")
        self.live_toggle.setCheckable(True)
        self.live_toggle.toggled.connect(self._on_live_toggled)
        source_row.addWidget(self.live_toggle)
        self.monitor_toggle = QtWidgets.QToolButton()
        self.monitor_toggle.setText("Monitor")
        self.monitor_toggle.setCheckable(True)
        self.monitor_toggle.setToolTip("Monitoring Mode: stateful activity + trace path (no time-window semantics)")
        self.monitor_toggle.toggled.connect(self._on_monitor_toggled)
        source_row.addWidget(self.monitor_toggle)
        toggle_style = _toggle_style()
        _apply_toggle_style([self.live_toggle, self.monitor_toggle], toggle_style)
        self.icon_style_combo = QtWidgets.QComboBox()
        for style, label in ICON_STYLE_LABELS.items():
            self.icon_style_combo.addItem(label, style)
        self.icon_style_combo.currentIndexChanged.connect(self._on_icon_style_changed)
        source_row.addWidget(QtWidgets.QLabel("Icon:"))
        source_row.addWidget(self.icon_style_combo)
        self.refresh_btn = QtWidgets.QToolButton()
        self.refresh_btn.setText("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_current_graph)
        source_row.addWidget(self.refresh_btn)
        self.open_window_button = QtWidgets.QToolButton()
        self.open_window_button.setText("Open in Window")
        self.open_window_button.clicked.connect(self._open_in_window)
        source_row.addWidget(self.open_window_button)
        self.open_window_btn = QtGui.QAction("Open in Window", self)
        self.open_window_btn.triggered.connect(self._open_in_window)
        self.view_menu = QtWidgets.QMenu(self)
        self.filters_menu = QtWidgets.QMenu(self)
        self.live_menu = QtWidgets.QMenu(self)
        self.presets_menu = QtWidgets.QMenu(self)
        self.more_button = QtWidgets.QToolButton()
        self.more_button.setText("More")
        self.more_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_menu = QtWidgets.QMenu(self.more_button)
        self.more_button.setMenu(self.more_menu)
        source_row.addWidget(self.more_button)
        source_row.addStretch()
        layout.addLayout(source_row)

        self._lens_palette_dock: Optional[QtWidgets.QDockWidget] = None
        self._dock_state_restored = False
        self._dock_syncing = False
        self._dock_size_syncing = False
        self._dock_save_timer = QtCore.QTimer(self)
        self._dock_save_timer.setSingleShot(True)
        self._dock_save_timer.timeout.connect(self._persist_lens_palette_dock_state)
        self._dock_last_floating: Optional[bool] = None

        self._build_view_menu()
        self._build_filter_menu()
        self._build_layer_menu()
        self._build_badge_menu()
        self._build_snapshot_menu()
        self._build_live_menu()
        self._build_presets_menu()
        self._build_more_menu()

        self.mode_status_row = QtWidgets.QWidget()
        mode_layout = QtWidgets.QHBoxLayout(self.mode_status_row)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(8)
        self._mode_status_layout = mode_layout
        self.mode_status_label = QtWidgets.QLabel("")
        self.mode_status_label.setStyleSheet("color: #555;")
        mode_layout.addWidget(self.mode_status_label, stretch=1)
        self.crash_open_btn = QtWidgets.QToolButton()
        self.crash_open_btn.setText("Open Crash Folder")
        self.crash_open_btn.clicked.connect(self._open_crash_folder)
        mode_layout.addWidget(self.crash_open_btn)
        self.crash_clear_btn = QtWidgets.QToolButton()
        self.crash_clear_btn.setText("Clear Crash")
        self.crash_clear_btn.clicked.connect(self._clear_crash_record)
        mode_layout.addWidget(self.crash_clear_btn)
        layout.addWidget(self.mode_status_row)

        self.filter_status_row = QtWidgets.QWidget()
        status_layout = QtWidgets.QHBoxLayout(self.filter_status_row)
        self._filter_status_layout = status_layout
        status_layout.setContentsMargins(0, 0, 0, 0)
        self.filter_status_label = QtWidgets.QLabel("")
        self.filter_status_label.setStyleSheet("color: #555;")
        status_layout.addWidget(self.filter_status_label)
        self.filter_chips_container = QtWidgets.QWidget()
        self.filter_chips_layout = QtWidgets.QHBoxLayout(self.filter_chips_container)
        self.filter_chips_layout.setContentsMargins(0, 0, 0, 0)
        self.filter_chips_layout.setSpacing(6)
        status_layout.addWidget(self.filter_chips_container, stretch=1)
        self.clear_filters_btn = QtWidgets.QPushButton("Clear all")
        self.clear_filters_btn.clicked.connect(self._clear_all_filters)
        status_layout.addWidget(self.clear_filters_btn)
        self.filter_status_row.setVisible(False)
        layout.addWidget(self.filter_status_row)

        self._lens_palette_shortcut = QtGui.QShortcut(QtGui.QKeySequence("L"), self)
        self._lens_palette_shortcut.activated.connect(self._toggle_lens_palette)
        self._lens_palette_escape = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        self._lens_palette_escape.activated.connect(self._on_lens_palette_escape)

        self.debug_status_row = QtWidgets.QWidget()
        debug_layout = QtWidgets.QHBoxLayout(self.debug_status_row)
        self._debug_status_layout = debug_layout
        debug_layout.setContentsMargins(0, 0, 0, 0)
        self.debug_status_label = QtWidgets.QLabel("")
        self.debug_status_label.setStyleSheet("color: #666;")
        debug_layout.addWidget(self.debug_status_label, stretch=1)
        self.debug_status_row.setVisible(False)
        layout.addWidget(self.debug_status_row)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: #555;")
        layout.addWidget(self.status_label)

        self.scene = GraphScene(
            on_open_subgraph=self._enter_subgraph,
            on_layout_changed=self._save_layout,
            on_inspect=self._inspect_node,
            on_peek=self._on_node_peek_requested,
            on_toggle_peek=self._on_node_double_click_in_peek,
            peek_menu_state=self._peek_menu_state,
            on_status_badges=self._show_status_menu,
            icon_style=self._resolved_icon_style(),
            node_theme=self._node_theme,
        )
        self.scene.set_reduced_motion(self._reduced_motion)
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        self.view = GraphView(
            self.scene,
            on_set_facet_density=self._on_set_facet_density,
            on_set_facet_scope=self._on_set_facet_scope,
            on_open_facet_settings=self._on_open_facet_settings,
        )
        self.view.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self.view, stretch=1)

        if not self._dock_host_external:
            self._dock_host.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
            self._dock_host.setCentralWidget(self._dock_container)
            outer_layout = QtWidgets.QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)
            outer_layout.setSpacing(0)
            outer_layout.addWidget(self._dock_host, stretch=1)

        ui_scale.register_listener(self._on_ui_scale_changed)
        self._apply_density(ui_scale.get_config())
        self._refresh_snapshot_history()
        self._sync_view_controls()
        self._update_peek_controls()
        self._ensure_inspector_panel()
        self._update_action_state()
        self._set_active_graphs(self._demo_root, self._demo_subgraphs)
        if self._runtime_hub and not self._runtime_connected:
            self._runtime_hub.event_emitted.connect(self._on_runtime_event)
            self._runtime_connected = True
        if self._safe_mode:
            self.live_toggle.setChecked(False)
            self.live_toggle.setEnabled(False)
            self.live_toggle.setVisible(False)
            if hasattr(self, "test_pulse_action"):
                self.test_pulse_action.setVisible(False)
            self._update_action_state()
            if self._crash_view:
                self._load_crash_record()
            self._load_latest_snapshot(show_status=True)
        elif self._crash_view:
            self._load_crash_record()
        self._update_mode_status(0, 0)
        self._update_debug_status()
        if harness.is_enabled() and self.status_label:
            self.status_label.setText("Harness enabled (PHYSICSLAB_CODESEE_HARNESS=1).")
        if self._lens_palette_pinned or self._lens_palette_visible:
            self._show_lens_palette()

    def open_root(self) -> None:
        if not self._active_root:
            return
        self._graph_stack = [self._active_root.graph_id]
        self._set_graph(self._active_root.graph_id)

    def dock_container(self) -> QtWidgets.QWidget:
        return self._dock_container

    def on_workspace_changed(self) -> None:
        self._lens = view_config.load_last_lens_id(self._workspace_id()) or DEFAULT_LENS
        self._view_config = view_config.load_view_config(self._workspace_id(), self._lens)
        self._icon_style = self._view_config.icon_style
        self._node_theme = self._view_config.node_theme
        self._pulse_settings = self._view_config.pulse_settings
        self._facet_settings = self._view_config.facet_settings
        self._monitor_enabled = bool(self._view_config.monitor_enabled)
        self._monitor_follow_last_trace = bool(self._view_config.monitor_follow_last_trace)
        self._monitor_show_edge_path = bool(self._view_config.monitor_show_edge_path)
        self._monitor.clear()
        self._monitor_active_trace_id = None
        self._monitor_trace_pinned = False
        self._monitor.set_follow_last_trace(self._monitor_follow_last_trace)
        self._monitor.set_span_stuck_seconds(int(self._view_config.span_stuck_seconds))
        self._diff_mode = False
        self._diff_result = None
        self._diff_baseline_graph = None
        self._diff_compare_graph = None
        self._diff_filters = {key: False for key in self._diff_filters}
        self._live_enabled = bool(self._view_config.live_enabled)
        self._events_by_node.clear()
        self._overlay_badges.clear()
        self._overlay_checks.clear()
        self._facet_selection_by_id.clear()
        self._active_facet_selection = None
        if self._crash_view:
            self._load_crash_record()
        self._sync_view_controls()
        self.scene.set_icon_style(self._resolved_icon_style())
        self.scene.set_node_theme(self._node_theme)
        self.scene.set_badge_layers(self._view_config.show_badge_layers)
        self._refresh_snapshot_history()
        self._render_current_graph()
        if hasattr(self, "diff_action"):
            self.diff_action.blockSignals(True)
            self.diff_action.setChecked(False)
            self.diff_action.blockSignals(False)

    def set_screen_context(self, context: str, detail: Optional[dict] = None) -> None:
        context = (context or "").strip()
        if not context:
            return
        if context == self._screen_context and not detail:
            return
        self._screen_context = context
        if self.scene:
            self.scene.set_context_nodes(self._context_nodes_for(context), label=context)
        self._update_mode_status(0, 0)

    def _context_nodes_for(self, context: str) -> set[str]:
        key = context.lower()
        if "system health" in key or "diagnostics" in key or "pack management" in key:
            return {"system:core_center"}
        if "content browser" in key or "content management" in key:
            return {"system:content_system"}
        if "block sandbox" in key or "block catalog" in key:
            return {"system:component_runtime"}
        if "lab" in key:
            return {"system:component_runtime"}
        return {"system:app_ui"}
        self.live_toggle.blockSignals(True)
        self.live_toggle.setChecked(self._live_enabled)
        self.live_toggle.blockSignals(False)
        self._update_action_state()
        if self._runtime_hub:
            self._runtime_hub.set_workspace_id(self._workspace_id())
        if self._source == SOURCE_ATLAS:
            self._build_atlas()
            return
        if self._source == SOURCE_SNAPSHOT:
            self._load_latest_snapshot(show_status=False)
            return
        if not self._current_graph_id:
            return
        self._current_graph_id = None
        self._set_graph(self._graph_stack[-1])

    def save_layout(self) -> None:
        self._save_layout()

    def cleanup(self) -> None:
        if self._status_timer and self._status_timer.isActive():
            self._status_timer.stop()
        if self._runtime_hub and self._runtime_connected:
            try:
                self._runtime_hub.event_emitted.disconnect(self._on_runtime_event)
            except Exception:
                pass
            self._runtime_connected = False
        if self.scene:
            self.scene.clear_pulses()

    def set_reduced_motion(self, value: bool) -> None:
        self._reduced_motion = bool(value)
        self.scene.set_icon_style(self._resolved_icon_style())
        self.scene.set_reduced_motion(self._reduced_motion)

    def _handle_back(self) -> None:
        self._save_layout()
        self.on_back()

    # --- [NAV-30A] graph stack / set graph / enter-subgraph
    def _workspace_id(self) -> str:
        info = self._workspace_info_provider() or {}
        if isinstance(info, dict):
            workspace_id = info.get("id") or info.get("workspace_id")
            if workspace_id:
                return str(workspace_id)
        return "default"

    def _graph_for_id(self, graph_id: str) -> Optional[ArchitectureGraph]:
        if self._active_root and graph_id == self._active_root.graph_id:
            return self._active_root
        return self._active_subgraphs.get(graph_id)

    def _graph_title(self, graph_id: str) -> str:
        graph = self._graph_for_id(graph_id)
        if graph:
            return graph.title
        return graph_id

    def _enter_subgraph(self, graph_id: str) -> None:
        if graph_id not in self._active_subgraphs:
            return
        self._graph_stack.append(graph_id)
        self._set_graph(graph_id)

    def _back_to_parent(self) -> None:
        if len(self._graph_stack) <= 1:
            return
        self._graph_stack.pop()
        self._set_graph(self._graph_stack[-1])

    def _set_graph(self, graph_id: str) -> None:
        self._save_layout()
        graph = self._graph_for_id(graph_id)
        if not graph:
            return
        self._current_graph_id = graph_id
        self._current_graph = graph
        self._refresh_breadcrumb()
        self._render_current_graph()

    def _peek_menu_state(self, node: Node) -> tuple[bool, str]:
        if str(node.node_id or "").startswith("facet:") or str(node.node_type or "").strip().lower() == "facet":
            return False, "No deeper graph; open in Inspector."
        self._rebuild_peek_index()
        item_ref = itemref_from_node(node)
        children = self._peek_children_by_id.get(item_ref.id, [])
        if children:
            return True, ""
        loaded_only_reason = "Peek available only for container nodes (has containment children)."
        if has_unloaded_subgraph(self._peek_node_map.get(item_ref.id), self._active_subgraphs):
            return False, "Deeper hierarchy available; open subgraph to load first."
        return False, loaded_only_reason

    def _on_node_peek_requested(self, node: Node) -> None:
        self._enter_peek(node)

    def _on_node_double_click_in_peek(self, node: Node) -> bool:
        if not self._peek.peek_active:
            return False
        return self._toggle_peek_expand(node)

    def _toggle_peek_expand(self, node: Node) -> bool:
        item_ref = itemref_from_node(node)
        if item_ref not in self._peek.peek_visible:
            return False
        if item_ref in self._peek.peek_expanded:
            self._peek_collapse(item_ref)
        else:
            self._peek_expand(item_ref)
        return True

    def _enter_peek(self, node: Node) -> None:
        can_peek, reason = self._peek_menu_state(node)
        if not can_peek:
            self.status_label.setText(reason or "Peek available only for container nodes (has containment children).")
            return
        self._rebuild_peek_index()
        root = itemref_from_node(node)
        new_peek = PeekContext(peek_active=True, peek_root=root, include_external_context=False)
        new_peek.peek_visible.add(root)
        new_peek.parent_by_id[root.id] = None
        children = self._peek_children_by_id.get(root.id, [])
        budget = apply_expand_budget(
            children,
            current_visible_total=1,
            max_add_per_expand=MAX_PEEK_ADD_PER_EXPAND,
            max_visible_total=MAX_PEEK_VISIBLE_TOTAL,
        )
        for child_id in budget.allowed_child_ids:
            child_ref = item_ref_for_node_id(child_id)
            new_peek.peek_visible.add(child_ref)
            new_peek.parent_by_id.setdefault(child_id, root.id)
        if budget.allowed_child_ids:
            new_peek.peek_expanded.add(root)
        new_peek.peek_breadcrumb = [root]
        self._peek = new_peek
        self._peek_warning = ""
        if budget.blocked_total:
            self.status_label.setText("Too many items in Peek. Collapse nodes or narrow scope.")
        elif budget.clamped:
            self.status_label.setText(
                f"Peek budget applied: showing {len(budget.allowed_child_ids)} children, "
                f"+{budget.omitted_count} more filtered."
            )
        else:
            self.status_label.setText("Peek mode active.")
        self._update_peek_controls()
        self._render_current_graph()

    def _exit_peek(self) -> None:
        if not self._peek.peek_active:
            return
        self._peek = PeekContext()
        self._peek_warning = ""
        self._update_peek_controls()
        self._render_current_graph()
        self.status_label.setText("Exited Peek mode.")

    def _reset_peek_view(self) -> None:
        if not self._peek.peek_active or not self._peek.peek_root:
            return
        node = self._peek_node_map.get(self._peek.peek_root.id)
        if not node:
            self._peek_warning = "Peek root not found (stale). Exit Peek to return to normal view."
            self._update_peek_controls()
            self._render_current_graph()
            self.status_label.setText(self._peek_warning)
            return
        self._enter_peek(node)
        self.status_label.setText("Peek view reset.")

    def _collapse_all_peek(self) -> None:
        if not self._peek.peek_active or not self._peek.peek_root:
            return
        root = self._peek.peek_root
        self._peek.peek_visible = {root}
        self._peek.peek_expanded = set()
        self._peek.peek_breadcrumb = [root]
        self._peek.parent_by_id = {root.id: None}
        self._peek_warning = ""
        self._update_peek_controls()
        self._render_current_graph()
        self.status_label.setText("Peek collapsed to root.")

    def _peek_expand(self, item_ref: ItemRef) -> None:
        self._rebuild_peek_index()
        children = self._peek_children_by_id.get(item_ref.id, [])
        if not children:
            node = self._peek_node_map.get(item_ref.id)
            if has_unloaded_subgraph(node, self._active_subgraphs):
                self.status_label.setText("Deeper hierarchy available; open subgraph to load.")
            else:
                self.status_label.setText("No containment children available.")
            return
        budget = apply_expand_budget(
            children,
            current_visible_total=len(self._peek.peek_visible),
            max_add_per_expand=MAX_PEEK_ADD_PER_EXPAND,
            max_visible_total=MAX_PEEK_VISIBLE_TOTAL,
        )
        if budget.blocked_total:
            self.status_label.setText("Too many items in Peek. Collapse nodes or narrow scope.")
            return
        added = 0
        for child_id in budget.allowed_child_ids:
            child_ref = item_ref_for_node_id(child_id)
            if child_ref in self._peek.peek_visible:
                continue
            if child_id in self._peek.parent_by_id:
                continue
            self._peek.peek_visible.add(child_ref)
            self._peek.parent_by_id[child_id] = item_ref.id
            added += 1
        self._peek.peek_expanded.add(item_ref)
        self._set_peek_breadcrumb(item_ref)
        self._update_peek_controls()
        self._render_current_graph()
        if budget.clamped:
            self.status_label.setText(
                f"Peek budget applied: added {added} child nodes, +{budget.omitted_count} more filtered."
            )
        elif added:
            self.status_label.setText(f"Peek expanded: +{added} nodes.")

    def _peek_collapse(self, item_ref: ItemRef) -> None:
        descendants = collapse_subtree_ids(item_ref.id, self._peek.parent_by_id)
        for node_id in descendants:
            self._peek.peek_visible.discard(item_ref_for_node_id(node_id))
            self._peek.peek_expanded.discard(item_ref_for_node_id(node_id))
            self._peek.parent_by_id.pop(node_id, None)
        self._peek.peek_expanded.discard(item_ref)
        self._set_peek_breadcrumb(item_ref)
        self._update_peek_controls()
        self._render_current_graph()
        self.status_label.setText("Peek collapsed.")

    def _set_peek_breadcrumb(self, item_ref: Optional[ItemRef]) -> None:
        if not self._peek.peek_active or not self._peek.peek_root:
            self._peek.peek_breadcrumb = []
            return
        target = item_ref if item_ref and item_ref.kind == "node" else self._peek.peek_root
        chain_ids = breadcrumb_chain_ids(target.id, self._peek.parent_by_id)
        if not chain_ids or chain_ids[0] != self._peek.peek_root.id:
            chain_ids = [self._peek.peek_root.id]
        self._peek.peek_breadcrumb = [item_ref_for_node_id(node_id) for node_id in chain_ids]

    def _update_peek_controls(self) -> None:
        active = bool(self._peek.peek_active and self._peek.peek_root)
        self.peek_row.setVisible(active)
        if not active:
            self.peek_breadcrumb_label.setText("Peek: (inactive)")
            return
        labels: list[str] = []
        for item_ref in self._peek.peek_breadcrumb:
            node = self._peek_node_map.get(item_ref.id)
            labels.append(node.title if node else itemref_display_name(item_ref))
        if not labels and self._peek.peek_root:
            node = self._peek_node_map.get(self._peek.peek_root.id)
            labels = [node.title if node else itemref_display_name(self._peek.peek_root)]
        self.peek_breadcrumb_label.setText("Peek: " + " > ".join(labels))
        self.peek_exit_btn.setEnabled(True)
        self.peek_collapse_all_btn.setEnabled(True)
        self.peek_reset_btn.setEnabled(True)
        blocker = QtCore.QSignalBlocker(self.peek_external_toggle)
        self.peek_external_toggle.setChecked(bool(self._peek.include_external_context))
        del blocker

    def _rebuild_peek_index(self) -> None:
        node_map, children_by_id = build_containment_index(self._active_root, self._active_subgraphs)
        self._peek_node_map = node_map
        self._peek_children_by_id = children_by_id

    def _peek_graph_for_render(self) -> Optional[ArchitectureGraph]:
        if not self._peek.peek_active or not self._peek.peek_root:
            return None
        self._rebuild_peek_index()
        root = self._peek.peek_root
        root_node = self._peek_node_map.get(root.id)
        graph_id_prefix = self._current_graph_id or "unknown"
        if root_node is None:
            self._peek_warning = "Peek root not found (stale). Exit Peek to return to normal view."
            return ArchitectureGraph(
                graph_id=f"peek:{graph_id_prefix}:{root.id}:stale",
                title="Peek (stale)",
                nodes=[],
                edges=[],
            )
        self._peek_warning = ""
        if root not in self._peek.peek_visible:
            self._peek.peek_visible.add(root)
            self._peek.parent_by_id.setdefault(root.id, None)
        visible_ids = sorted(
            [ref.id for ref in self._peek.peek_visible if ref.kind == "node" and ref.id in self._peek_node_map]
        )
        nodes = [self._peek_node_map[node_id] for node_id in visible_ids]
        visible_set = set(visible_ids)
        edges: list[Edge] = []
        for src_id in visible_ids:
            for dst_id in self._peek_children_by_id.get(src_id, []):
                if dst_id not in visible_set:
                    continue
                edges.append(
                    Edge(
                        edge_id=f"peek:{src_id}:{dst_id}:contains",
                        src_node_id=src_id,
                        dst_node_id=dst_id,
                        kind="contains",
                    )
                )
        return ArchitectureGraph(
            graph_id=f"peek:{graph_id_prefix}:{root.id}",
            title=f"Peek: {root_node.title}",
            nodes=nodes,
            edges=edges,
        )

    # --- [NAV-30B] layout save/restore
    def _save_layout(self) -> None:
        if not self._render_graph_id:
            return
        positions = self.scene.node_positions()
        existing = layout_store.load_positions(self._workspace_id(), self._lens, self._render_graph_id)
        if existing:
            existing.update(positions)
            positions = existing
        layout_store.save_positions(self._workspace_id(), self._lens, self._render_graph_id, positions)

    def _render_current_graph(self) -> None:
        if not self._current_graph_id or not self._current_graph:
            return
        graph_to_render = self._current_graph
        diff_result = None
        if self._diff_mode and self._diff_compare_graph and self._diff_result:
            graph_to_render = self._diff_compare_graph
            diff_result = self._diff_result
        peek_graph = self._peek_graph_for_render()
        in_peek = peek_graph is not None
        if in_peek:
            graph_to_render = peek_graph
            diff_result = None
        self._render_graph_id = graph_to_render.graph_id
        positions = layout_store.load_positions(self._workspace_id(), self._lens, self._render_graph_id)
        overlay_graph = self._apply_runtime_overlay(graph_to_render)
        overlay_graph = self._apply_expectation_badges(overlay_graph)
        overlay_graph = self._apply_span_overlay(overlay_graph)
        overlay_graph = self._apply_crash_badge(overlay_graph)
        overlay_graph = self._apply_diff_removed_nodes(overlay_graph)
        total_nodes = len(overlay_graph.nodes)
        if in_peek:
            filtered = overlay_graph
        else:
            filtered = self._filtered_graph(overlay_graph)
        empty_message = None
        if not in_peek and self._lens == LENS_BUS and not _bus_nodes_present(graph_to_render):
            empty_message = "No bus nodes found for this graph."
            filtered = ArchitectureGraph(
                graph_id=filtered.graph_id,
                title=filtered.title,
                nodes=[],
                edges=[],
            )
        if in_peek and self._peek_warning:
            empty_message = self._peek_warning
        filtered = self._inject_system_map_facets(filtered, in_peek=in_peek)
        shown_nodes = len(filtered.nodes)
        if self._active_facet_selection and self._active_facet_selection.facet_id not in {
            node.node_id for node in filtered.nodes
        }:
            self._active_facet_selection = None
        if empty_message is None and shown_nodes == 0 and self._filters_active():
            empty_message = "No nodes match the current filters."
        self._update_filter_status(total_nodes, shown_nodes)
        self._update_mode_status(total_nodes, shown_nodes)
        self.scene.set_empty_message(empty_message)
        self._render_node_map = {node.node_id: node for node in filtered.nodes}
        self._facet_selection_by_id = self._facet_selection_index(filtered)
        self.scene.build_graph(filtered, positions, diff_result=diff_result)
        self.scene.set_icon_style(self._resolved_icon_style())
        self.scene.set_badge_layers(self._view_config.show_badge_layers)
        self._update_span_tints(filtered)
        self._apply_monitor_overlay(now=time.time())
        self._update_debug_status()
        self._ensure_status_timer()
        self._update_peek_controls()
        self._refresh_inspector_panel()

    def _enabled_facet_keys(self) -> list[str]:
        defaults = _facet_enabled_defaults_for_density(self._facet_settings.density)
        raw_enabled = dict(getattr(self._facet_settings, "enabled", {}))
        for key, value in raw_enabled.items():
            if key in defaults and isinstance(value, bool):
                defaults[key] = value
        return [key for key in view_config.FACET_KEYS if defaults.get(key, False)]

    def _facet_scope(self) -> str:
        scope = str(getattr(self._facet_settings, "facet_scope", "selected") or "selected").strip().lower()
        if scope in getattr(view_config, "FACET_SCOPES", ("selected", "peek_graph")):
            return scope
        return "selected"

    def _should_show_facets(self, *, in_peek: bool) -> bool:
        if self._source != SOURCE_DEMO:
            return False
        density = str(self._facet_settings.density or "").strip().lower()
        if density == "off":
            return False
        if in_peek:
            return bool(self._facet_settings.show_in_peek_view)
        return bool(self._facet_settings.show_in_normal_view)

    def _selected_owner_id(self, graph: ArchitectureGraph) -> Optional[str]:
        node_map = graph.node_map()
        chosen_id: Optional[str] = None

        if self.selected_item and self.selected_item.kind == "node":
            candidate_id = str(self.selected_item.id)
            if candidate_id.startswith("facet:") and self._active_facet_selection is not None:
                candidate_id = str(self._active_facet_selection.base_node_id or "")
            candidate_node = node_map.get(candidate_id)
            if candidate_node and str(candidate_node.node_type or "").strip().lower() == "module":
                chosen_id = candidate_id

        selected_module_ids: list[str] = []
        for item in self.scene.selectedItems():
            if not isinstance(item, NodeItem):
                continue
            node = item.node
            node_id = str(node.node_id or "")
            if node_id.startswith("facet:"):
                continue
            if str(node.node_type or "").strip().lower() != "module":
                continue
            if node_id not in node_map:
                continue
            selected_module_ids.append(node_id)
        if selected_module_ids:
            if chosen_id not in selected_module_ids:
                chosen_id = selected_module_ids[-1]
            if len(selected_module_ids) > 1 and chosen_id:
                hint_key = "|".join(sorted(selected_module_ids))
                if hint_key != self._facet_scope_multi_hint_key:
                    owner_node = node_map.get(chosen_id)
                    owner_label = owner_node.title if owner_node else chosen_id
                    self.status_label.setText(
                        f"Facets scope: using primary selection ({owner_label})."
                    )
                    self._facet_scope_multi_hint_key = hint_key
            else:
                self._facet_scope_multi_hint_key = None
        else:
            self._facet_scope_multi_hint_key = None
        return chosen_id

    @staticmethod
    def _container_owner_ids(graph: ArchitectureGraph) -> set[str]:
        owner_ids: set[str] = set()
        for edge in graph.edges:
            if str(edge.kind or "").strip().lower() == "contains":
                owner_ids.add(str(edge.src_node_id))
        return owner_ids

    def _candidate_facet_owner_ids(self, graph: ArchitectureGraph, *, in_peek: bool) -> list[str]:
        scope = self._facet_scope()
        if scope == "peek_graph" and in_peek:
            owners: list[str] = []
            for node in graph.nodes:
                node_id = str(node.node_id or "")
                if node_id.startswith("facet:"):
                    continue
                if str(node.node_type or "").strip().lower() != "module":
                    continue
                owners.append(node_id)
            return owners

        selected_owner = self._selected_owner_id(graph)
        if selected_owner:
            return [selected_owner]
        return []

    def _inject_system_map_facets(self, graph: ArchitectureGraph, *, in_peek: bool) -> ArchitectureGraph:
        if not self._should_show_facets(in_peek=in_peek):
            return graph
        enabled_keys = self._enabled_facet_keys()
        if not enabled_keys:
            return graph
        owner_ids = self._candidate_facet_owner_ids(graph, in_peek=in_peek)
        if not owner_ids:
            return graph
        node_map = graph.node_map()
        container_owner_ids = self._container_owner_ids(graph)
        existing_node_ids = {node.node_id for node in graph.nodes}
        nodes = list(graph.nodes)
        edges = list(graph.edges)
        for owner_id in owner_ids:
            base = node_map.get(owner_id)
            if base is None:
                continue
            owner_label = str(base.title or owner_id).strip() or owner_id
            owner_keys = list(enabled_keys)
            if owner_id in container_owner_ids:
                owner_keys = [key for key in owner_keys if key not in FACET_KEYS_ACTIVITY]
            for key in owner_keys:
                facet_id = f"facet:{base.node_id}:{key}"
                if facet_id in existing_node_ids:
                    continue
                facet_label = FACET_LABELS.get(key, key.replace("_", " ").title())
                nodes.append(
                    Node(
                        node_id=facet_id,
                        title=f"{owner_label} / {facet_label}",
                        node_type=FACET_NODE_TYPE,
                        metadata={
                            FACET_META_KEY: {
                                "owner_id": base.node_id,
                                "base_node_id": base.node_id,
                                "facet_kind": key,
                                "facet_key": key,
                                "facet_label": facet_label,
                                "owner_label": owner_label,
                            }
                        },
                    )
                )
                edges.append(
                    Edge(
                        edge_id=f"facet-edge:{base.node_id}:{key}",
                        src_node_id=base.node_id,
                        dst_node_id=facet_id,
                        kind=FACET_EDGE_KIND,
                        metadata={"relation": FACET_EDGE_RELATION},
                    )
                )
                existing_node_ids.add(facet_id)
        return ArchitectureGraph(
            graph_id=graph.graph_id,
            title=graph.title,
            nodes=nodes,
            edges=edges,
        )

    def _facet_selection_from_node(self, node: Optional[Node]) -> Optional[FacetSelection]:
        if node is None:
            return None
        metadata = node.metadata if isinstance(node.metadata, dict) else {}
        raw = metadata.get(FACET_META_KEY)
        if not isinstance(raw, dict):
            return None
        base_node_id = str(raw.get("owner_id", "") or raw.get("base_node_id", "") or "").strip()
        facet_key = str(raw.get("facet_kind", "") or raw.get("facet_key", "") or "").strip()
        facet_label = str(raw.get("facet_label", "") or node.title or "").strip()
        if not base_node_id or not facet_key:
            return None
        return FacetSelection(
            facet_id=str(node.node_id),
            base_node_id=base_node_id,
            facet_key=facet_key,
            facet_label=facet_label or facet_key,
        )

    def _facet_selection_index(self, graph: ArchitectureGraph) -> Dict[str, FacetSelection]:
        mapping: Dict[str, FacetSelection] = {}
        for node in graph.nodes:
            selection = self._facet_selection_from_node(node)
            if selection is None:
                continue
            mapping[selection.facet_id] = selection
        return mapping

    def _refresh_breadcrumb(self) -> None:
        while self.breadcrumb_layout.count():
            item = self.breadcrumb_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for idx, graph_id in enumerate(self._graph_stack):
            title = self._graph_title(graph_id)
            btn = QtWidgets.QPushButton(title)
            btn.setFlat(True)
            btn.clicked.connect(lambda _checked=False, index=idx: self._jump_to_index(index))
            self.breadcrumb_layout.addWidget(btn)
            if idx < len(self._graph_stack) - 1:
                sep = QtWidgets.QLabel(">")
                sep.setStyleSheet("color: #666;")
                self.breadcrumb_layout.addWidget(sep)
        self.back_btn.setEnabled(len(self._graph_stack) > 1)
        lens_title = self._lens_map.get(self._lens).title if self._lens in self._lens_map else self._lens
        self.lens_label.setText(f"Lens: {lens_title}")

    def _jump_to_index(self, index: int) -> None:
        if index < 0 or index >= len(self._graph_stack):
            return
        self._graph_stack = self._graph_stack[: index + 1]
        self._set_graph(self._graph_stack[-1])

    def _normalize_source_value(self, value: str) -> str:
        text = (value or "").strip()
        if text == "Demo":
            return SOURCE_DEMO
        if text in (SOURCE_DEMO, SOURCE_ATLAS, SOURCE_SNAPSHOT):
            return text
        return SOURCE_DEMO

    def _on_source_changed(self, value: str) -> None:
        normalized = self._normalize_source_value(value)
        if normalized != value:
            blocker = QtCore.QSignalBlocker(self.source_combo)
            self.source_combo.setCurrentText(normalized)
            del blocker
        if normalized == self._source:
            return
        self._save_layout()
        self._source = normalized
        self._update_action_state()
        if normalized == SOURCE_DEMO:
            self._set_active_graphs(self._demo_root, self._demo_subgraphs)
            self.status_label.setText("")
            return
        if normalized == SOURCE_ATLAS:
            self._build_atlas()
            if self._facet_settings.density != "off":
                self._show_facet_source_hint()
            return
        if normalized == SOURCE_SNAPSHOT:
            self._load_latest_snapshot(show_status=True)

    def _set_active_graphs(
        self,
        root: ArchitectureGraph,
        subgraphs: Dict[str, ArchitectureGraph],
    ) -> None:
        self._relation_index_normal = None
        self._relation_index_normal_key = None
        self._relation_index_compare = None
        self._relation_index_compare_key = None
        self._inspector_relations_state_key = None
        self._render_node_map = {}
        self._facet_selection_by_id = {}
        self._active_facet_selection = None
        self._active_root = root
        self._active_subgraphs = subgraphs
        self._graph_stack = [root.graph_id]
        self._current_graph_id = None
        self._current_graph = None
        self._set_graph(root.graph_id)

    def _update_action_state(self) -> None:
        self.capture_btn.setEnabled(self._source in (SOURCE_DEMO, SOURCE_ATLAS))
        self.load_btn.setEnabled(True)
        if hasattr(self, "removed_action"):
            self.removed_action.setEnabled(self._diff_mode and self._diff_result is not None)
        for action in getattr(self, "_diff_filter_actions", {}).values():
            action.setEnabled(self._diff_mode and self._diff_result is not None)
        self.open_window_btn.setEnabled(bool(self._allow_detach and self._on_open_window))
        if hasattr(self, "open_window_button"):
            self.open_window_button.setEnabled(bool(self._allow_detach and self._on_open_window))
        diff_visible = bool(self._diff_mode)
        if hasattr(self, "baseline_action"):
            self.baseline_action.setVisible(diff_visible)
        if hasattr(self, "compare_action"):
            self.compare_action.setVisible(diff_visible)
        self._sync_monitor_actions()
        self._update_mode_status(0, 0)

    def _build_view_menu(self) -> None:
        self.view_menu.clear()
        self.diff_action = QtGui.QAction("Diff Mode", self.view_menu)
        self.diff_action.setCheckable(True)
        self.diff_action.toggled.connect(self._on_diff_toggled)
        self.view_menu.addAction(self.diff_action)
        self.removed_action = QtGui.QAction("Removed Items...", self.view_menu)
        self.removed_action.triggered.connect(self._open_removed_dialog)
        self.view_menu.addAction(self.removed_action)
        diff_filters_menu = self.view_menu.addMenu("Diff Filters")
        self._diff_filter_actions: Dict[str, QtGui.QAction] = {}
        for key, label in _diff_filter_labels().items():
            action = QtGui.QAction(label, diff_filters_menu)
            action.setCheckable(True)
            action.toggled.connect(lambda checked=False, k=key: self._set_diff_filter(k, checked))
            diff_filters_menu.addAction(action)
            self._diff_filter_actions[key] = action
        self.view_menu.addSeparator()

        self.layers_menu = self.view_menu.addMenu("Layers")
        self.category_menu = self.layers_menu.addMenu("Categories")
        self.badge_layer_menu = self.layers_menu.addMenu("Badge Layers")

        theme_menu = self.view_menu.addMenu("Theme")
        self._theme_actions: Dict[str, QtGui.QAction] = {}
        theme_group = QtGui.QActionGroup(theme_menu)
        theme_group.setExclusive(True)
        for theme_id, label in [("neutral", "Neutral"), ("categorical", "Categorical")]:
            action = QtGui.QAction(label, theme_menu)
            action.setCheckable(True)
            action.setActionGroup(theme_group)
            action.triggered.connect(lambda _checked=False, value=theme_id: self._set_node_theme(value))
            theme_menu.addAction(action)
            self._theme_actions[theme_id] = action
        self.view_menu.addSeparator()
        self.facet_settings_action = QtGui.QAction("Facet Settings...", self.view_menu)
        self.facet_settings_action.triggered.connect(self._open_facet_settings)
        self.view_menu.addAction(self.facet_settings_action)
        self.monitor_menu = self.view_menu.addMenu("Monitoring")
        self.monitor_clear_action = QtGui.QAction("Clear state", self.monitor_menu)
        self.monitor_clear_action.triggered.connect(self._clear_monitor_state)
        self.monitor_menu.addAction(self.monitor_clear_action)
        self.monitor_menu.addSeparator()
        self.monitor_follow_action = QtGui.QAction("Follow last trace", self.monitor_menu)
        self.monitor_follow_action.setCheckable(True)
        self.monitor_follow_action.toggled.connect(self._on_monitor_follow_toggled)
        self.monitor_menu.addAction(self.monitor_follow_action)
        self.monitor_show_edge_action = QtGui.QAction("Show edge path", self.monitor_menu)
        self.monitor_show_edge_action.setCheckable(True)
        self.monitor_show_edge_action.toggled.connect(self._on_monitor_show_edge_toggled)
        self.monitor_menu.addAction(self.monitor_show_edge_action)
        self.monitor_menu.addSeparator()
        self.monitor_pin_action = QtGui.QAction("Pin Active Trace", self.monitor_menu)
        self.monitor_pin_action.triggered.connect(self._pin_active_monitor_trace)
        self.monitor_menu.addAction(self.monitor_pin_action)
        self.monitor_unpin_action = QtGui.QAction("Unpin Trace", self.monitor_menu)
        self.monitor_unpin_action.triggered.connect(self._unpin_monitor_trace)
        self.monitor_menu.addAction(self.monitor_unpin_action)

    def _build_filter_menu(self) -> None:
        self.filters_menu.clear()
        self._filter_actions: Dict[str, QtGui.QAction] = {}
        for key, label in _quick_filter_labels().items():
            action = QtGui.QAction(label, self.filters_menu)
            action.setCheckable(True)
            action.toggled.connect(lambda checked=False, k=key: self._set_quick_filter(k, checked))
            self.filters_menu.addAction(action)
            self._filter_actions[key] = action

    def _build_layer_menu(self) -> None:
        self._category_actions: Dict[str, QtGui.QAction] = {}
        self.category_menu.clear()
        for category in _category_keys():
            action = QtGui.QAction(category, self.category_menu)
            action.setCheckable(True)
            action.toggled.connect(self._on_category_toggled)
            self.category_menu.addAction(action)
            self._category_actions[category] = action

    def _build_badge_menu(self) -> None:
        self._badge_actions: Dict[str, QtGui.QAction] = {}
        self.badge_layer_menu.clear()
        for layer_id, label in _badge_layer_labels().items():
            action = QtGui.QAction(label, self.badge_layer_menu)
            action.setCheckable(True)
            action.toggled.connect(self._on_badge_layer_toggled)
            self.badge_layer_menu.addAction(action)
            self._badge_actions[layer_id] = action

    def _build_snapshot_menu(self) -> None:
        self.snapshot_menu.clear()
        self.snapshot_menu.addAction(self.capture_btn)
        self.snapshot_menu.addAction(self.load_btn)
        self.snapshot_menu.addSeparator()
        self.baseline_action = self._make_combo_action("Baseline:", self.baseline_combo, parent=self.snapshot_menu)
        self.compare_action = self._make_combo_action("Compare:", self.compare_combo, parent=self.snapshot_menu)
        self.snapshot_menu.addAction(self.baseline_action)
        self.snapshot_menu.addAction(self.compare_action)

    def _build_live_menu(self) -> None:
        self.live_menu.clear()
        self.pulse_settings_action = QtGui.QAction("Pulse Settings...", self.live_menu)
        self.pulse_settings_action.triggered.connect(self._open_pulse_settings)
        self.live_menu.addAction(self.pulse_settings_action)
        debug_menu = self.live_menu.addMenu("Debug")
        self.test_pulse_action = QtGui.QAction("Emit Test Pulse", debug_menu)
        self.test_pulse_action.triggered.connect(self._emit_test_pulse)
        debug_menu.addAction(self.test_pulse_action)

    def _build_presets_menu(self) -> None:
        self.presets_menu.clear()
        save_action = QtGui.QAction("Save Preset...", self.presets_menu)
        save_action.triggered.connect(self._save_preset)
        self.presets_menu.addAction(save_action)
        self.presets_menu.addSeparator()
        presets = view_config.load_view_presets(self._workspace_id())
        if not presets:
            empty = QtGui.QAction("No presets", self.presets_menu)
            empty.setEnabled(False)
            self.presets_menu.addAction(empty)
            return
        for name in sorted(presets.keys()):
            action = QtGui.QAction(name, self.presets_menu)
            action.triggered.connect(lambda _checked=False, n=name: self._apply_preset(n))
            self.presets_menu.addAction(action)

    def _build_more_menu(self) -> None:
        self.more_menu.clear()
        self.more_menu.addMenu(self.view_menu).setText("View")
        self.more_menu.addMenu(self.filters_menu).setText("Filters")
        self.more_menu.addMenu(self.live_menu).setText("Live")
        self.more_menu.addMenu(self.presets_menu).setText("Presets")
        if harness.is_enabled():
            harness_menu = self.more_menu.addMenu("Harness")
            self.harness_activity_action = QtGui.QAction("Emit test activity", harness_menu)
            self.harness_activity_action.triggered.connect(self._emit_harness_activity)
            harness_menu.addAction(self.harness_activity_action)
            self.harness_mismatch_action = QtGui.QAction("Emit EVA mismatch", harness_menu)
            self.harness_mismatch_action.triggered.connect(self._emit_harness_mismatch)
            harness_menu.addAction(self.harness_mismatch_action)
            self.harness_crash_action = QtGui.QAction("Write fake crash record", harness_menu)
            self.harness_crash_action.triggered.connect(self._emit_harness_crash)
            harness_menu.addAction(self.harness_crash_action)
            self.harness_toggle_inventory = QtGui.QAction("Toggle fake pack", harness_menu)
            self.harness_toggle_inventory.triggered.connect(self._toggle_harness_pack)
            harness_menu.addAction(self.harness_toggle_inventory)

    def _sync_view_controls(self) -> None:
        self._sync_lens_combo()
        self.source_combo.blockSignals(True)
        self.source_combo.setCurrentText(self._normalize_source_value(self._source))
        self.source_combo.blockSignals(False)
        self.live_toggle.blockSignals(True)
        self.live_toggle.setChecked(self._live_enabled)
        self.live_toggle.blockSignals(False)
        self.monitor_toggle.blockSignals(True)
        self.monitor_toggle.setChecked(self._monitor_enabled)
        self.monitor_toggle.blockSignals(False)
        if hasattr(self, "diff_action"):
            self.diff_action.blockSignals(True)
            self.diff_action.setChecked(self._diff_mode)
            self.diff_action.blockSignals(False)
        for category, action in self._category_actions.items():
            action.blockSignals(True)
            action.setChecked(self._view_config.show_categories.get(category, True))
            action.blockSignals(False)
        for layer_id, action in self._badge_actions.items():
            action.blockSignals(True)
            action.setChecked(self._view_config.show_badge_layers.get(layer_id, True))
            action.blockSignals(False)
        for style, action in getattr(self, "_style_actions", {}).items():
            action.blockSignals(True)
            action.setChecked(style == self._icon_style)
            action.blockSignals(False)
        self._sync_icon_style_combo()
        for theme_id, action in getattr(self, "_theme_actions", {}).items():
            action.blockSignals(True)
            action.setChecked(theme_id == (self._view_config.node_theme or "neutral"))
            action.blockSignals(False)
        for key, action in getattr(self, "_filter_actions", {}).items():
            action.blockSignals(True)
            action.setChecked(self._view_config.quick_filters.get(key, False))
            action.blockSignals(False)
        for key, action in getattr(self, "_diff_filter_actions", {}).items():
            action.blockSignals(True)
            action.setChecked(self._diff_filters.get(key, False))
            action.blockSignals(False)
        self._sync_monitor_actions()
        self._build_presets_menu()
        self._build_more_menu()

    @staticmethod
    def _make_combo_action(
        label: str,
        combo: QtWidgets.QComboBox,
        *,
        parent: QtWidgets.QMenu,
    ) -> QtWidgets.QWidgetAction:
        container = QtWidgets.QWidget(parent)
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.addWidget(QtWidgets.QLabel(label))
        layout.addWidget(combo, stretch=1)
        action = QtWidgets.QWidgetAction(parent)
        action.setDefaultWidget(container)
        return action

    def _sync_lens_combo(self) -> None:
        for idx in range(self.lens_combo.count()):
            lens_id = self.lens_combo.itemData(idx)
            if lens_id == self._lens:
                self.lens_combo.blockSignals(True)
                self.lens_combo.setCurrentIndex(idx)
                self.lens_combo.blockSignals(False)
                break
        self._sync_lens_palette_selection()

    def _log_lens_palette(self, message: str) -> None:
        try:
            log_buffer.LOG_BUFFER.append(f"lens_palette: {message}")
        except Exception:
            pass
        try:
            if os.environ.get("PHYSICSLAB_CODESEE_DEBUG", "0") != "1":
                return
        except Exception:
            return
        try:
            print(f"[codesee.lens_palette] {message}")
        except Exception:
            return

    def _bind_lens_palette_model_signals(self) -> None:
        return

    def _on_lens_palette_button_clicked(self) -> None:
        if self._is_typing_widget():
            return
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier:
            self._set_lens_palette_pinned(not self._lens_palette_pinned)
            if self._lens_palette_pinned and not self._lens_palette_visible:
                self._show_lens_palette()
            return
        self._toggle_lens_palette()

    def _toggle_lens_palette(self) -> None:
        if self._lens_palette_pinned and self._lens_palette_visible:
            return
        if self._lens_palette_visible:
            self._hide_lens_palette()
        else:
            self._show_lens_palette()

    def _on_lens_palette_escape(self) -> None:
        if self._is_typing_widget():
            return
        if self._lens_palette_visible:
            if self._lens_palette_pinned:
                self._set_lens_palette_pinned(False)
            self._hide_lens_palette()

    # --- [NAV-40A] ensure palette widget
    def _ensure_lens_palette(self) -> None:
        if self._lens_palette is not None:
            return
        palette = LensPaletteWidget(self)
        palette.set_lens_combo(self.lens_combo)
        palette.set_on_select(self._select_lens_from_palette)
        palette.set_on_close(self._hide_lens_palette)
        palette.set_on_pin(self._set_lens_palette_pinned)
        palette.set_on_diagnostics(self._open_codesee_diagnostics)
        palette.set_on_clear_recent(self._clear_lens_palette_recent)
        palette.set_on_clear_search(self._clear_lens_search)
        palette.set_on_float_palette(self._float_lens_palette)
        palette.set_on_reset_layout(self._reset_lens_palette_layout)
        palette.set_on_refresh_inventory(self._refresh_lens_inventory)
        palette.set_recent(self._lens_palette_recent)
        palette.set_active_lens(self._lens)
        palette.set_pinned(self._lens_palette_pinned)
        self._lens_palette = palette
        self._ensure_lens_palette_dock()
        if self._lens_palette:
            self._lens_palette.refresh()

    # --- [NAV-40B] ensure dock + apply flags
    def _ensure_lens_palette_dock(self) -> None:
        if self._lens_palette_dock is not None:
            return
        if not self._lens_palette:
            return
        dock = QtWidgets.QDockWidget("Lenses", self._dock_host)
        dock.setObjectName("codeseeLensPaletteDock")
        dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        dock.setAllowedAreas(
            QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
            | QtCore.Qt.DockWidgetArea.RightDockWidgetArea
            | QtCore.Qt.DockWidgetArea.BottomDockWidgetArea
            | QtCore.Qt.DockWidgetArea.TopDockWidgetArea
        )
        dock.setWidget(self._lens_palette)
        self._dock_host.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.installEventFilter(self)
        dock.topLevelChanged.connect(self._on_lens_palette_dock_floating_changed)
        dock.visibilityChanged.connect(self._on_lens_palette_dock_visibility_changed)
        dock.dockLocationChanged.connect(self._on_lens_palette_dock_location_changed)
        self._lens_palette_dock = dock
        if not self._dock_state_restored:
            self._restore_lens_palette_dock_state()
            self._dock_state_restored = True
        self._apply_lens_palette_flags()

    def _rebuild_lens_tiles(self) -> None:
        if self._lens_palette:
            self._lens_palette.refresh()

    def _clear_lens_search(self) -> None:
        if self._lens_palette and getattr(self._lens_palette, "_search", None):
            self._lens_palette._search.setText("")

    def _toggle_lens_palette_expanded(self) -> None:
        return

    def _update_lens_palette_sizing(self) -> None:
        return

    def _show_recent_lenses_menu(self) -> None:
        return

    def _clear_lens_palette_recent(self) -> None:
        self._lens_palette_recent = []
        if self._lens_palette:
            self._lens_palette.set_recent([])
        view_config.save_lens_palette_state(
            self._workspace_id(),
            pinned=self._lens_palette_pinned,
            recent=self._lens_palette_recent,
            dock_state=None,
            dock_geometry=None,
            palette_visible=self._lens_palette_visible,
            palette_floating=self._lens_palette_dock.isFloating() if self._lens_palette_dock else None,
        )

    def _float_lens_palette(self) -> None:
        self._set_lens_palette_pinned(False)
        if self._lens_palette_dock:
            self._lens_palette_dock.setFloating(True)
            self._lens_palette_dock.raise_()

    def _reset_lens_palette_layout(self) -> None:
        if self._lens_palette_dock:
            self._lens_palette_dock.setFloating(False)
            self._dock_host.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, self._lens_palette_dock)
        view_config.save_lens_palette_state(
            self._workspace_id(),
            pinned=self._lens_palette_pinned,
            recent=self._lens_palette_recent,
            dock_state="",
            dock_geometry="",
            palette_visible=self._lens_palette_visible,
            palette_floating=self._lens_palette_dock.isFloating() if self._lens_palette_dock else None,
        )

    def _refresh_lens_inventory(self) -> None:
        self._refresh_current_graph()

    def _open_codesee_diagnostics(self) -> None:
        if self._diagnostics_dialog is None:
            self._diagnostics_dialog = diagnostics_dialog.CodeSeeDiagnosticsDialog(
                snapshot_provider=lambda: diagnostics.codesee_diagnostics_snapshot(self),
                log_provider=log_buffer.LOG_BUFFER.get_lines,
                parent=self,
            )
            self._diagnostics_dialog.finished.connect(self._close_codesee_diagnostics)
        self._diagnostics_dialog.refresh()
        self._diagnostics_dialog.show()
        self._diagnostics_dialog.raise_()
        self._diagnostics_dialog.activateWindow()

    def _close_codesee_diagnostics(self, _result: int = 0) -> None:
        self._diagnostics_dialog = None

    def _remember_recent_lens(self, lens_id: str) -> None:

        if not lens_id:
            return
        recent = [item for item in self._lens_palette_recent if item != lens_id]
        recent.insert(0, lens_id)
        recent = recent[:6]
        self._lens_palette_recent = recent
        if self._lens_palette:
            self._lens_palette.set_recent(self._lens_palette_recent)
        view_config.save_lens_palette_state(
            self._workspace_id(),
            pinned=self._lens_palette_pinned,
            recent=self._lens_palette_recent,
        )

    def _apply_lens_palette_flags(self) -> None:
        if not self._lens_palette_dock or not self._lens_palette:
            return
        pinned = bool(self._lens_palette_pinned)
        self._dock_syncing = True
        try:
            self._lens_palette_dock.setFloating(not pinned)
        finally:
            self._dock_syncing = False
        self._lens_palette.set_pinned(pinned)

    def _on_lens_palette_dock_floating_changed(self, floating: bool) -> None:
        if self._dock_syncing:
            return
        pinned = not bool(floating)
        if pinned != self._lens_palette_pinned:
            self._lens_palette_pinned = pinned
            if self._lens_palette:
                self._lens_palette.set_pinned(pinned)
        self._apply_lens_palette_dock_size(floating=floating, force=not floating)
        if floating and self._lens_palette_visible:
            self._position_lens_palette()
        self._schedule_lens_palette_dock_save()

    def _on_lens_palette_dock_visibility_changed(self, visible: bool) -> None:
        self._lens_palette_visible = bool(visible)
        blocker = QtCore.QSignalBlocker(self.lens_palette_btn)
        self.lens_palette_btn.setChecked(self._lens_palette_visible)
        del blocker
        if self._lens_palette_visible and not self._lens_palette_pinned:
            self._install_lens_palette_event_filter()
        else:
            self._remove_lens_palette_event_filter()
        self._schedule_lens_palette_dock_save()

    def _on_lens_palette_dock_location_changed(self, _area: QtCore.Qt.DockWidgetArea) -> None:
        self._apply_lens_palette_dock_size(force=True)
        self._schedule_lens_palette_dock_save()

    def _schedule_lens_palette_dock_save(self) -> None:
        if self._dock_save_timer:
            self._dock_save_timer.start(350)

    # --- [NAV-40C] persist/restore dock state
    def _persist_lens_palette_dock_state(self) -> None:
        if not self._lens_palette_dock:
            return
        try:
            dock_state = bytes(self._dock_host.saveState())
            dock_geom = bytes(self._lens_palette_dock.saveGeometry())
        except Exception:
            return
        state_str = base64.b64encode(dock_state).decode("ascii") if dock_state else ""
        geom_str = base64.b64encode(dock_geom).decode("ascii") if dock_geom else ""
        view_config.save_lens_palette_state(
            self._workspace_id(),
            pinned=self._lens_palette_pinned,
            recent=self._lens_palette_recent,
            dock_state=state_str,
            dock_geometry=geom_str,
            palette_visible=self._lens_palette_visible,
            palette_floating=self._lens_palette_dock.isFloating(),
        )

    # --- [NAV-40C] persist/restore dock state
    def _restore_lens_palette_dock_state(self) -> None:
        if not self._lens_palette_dock:
            return
        palette_state = view_config.load_lens_palette_state(self._workspace_id())
        dock_state = palette_state.get("dock_state")
        if isinstance(dock_state, str) and dock_state:
            try:
                self._dock_host.restoreState(
                    QtCore.QByteArray.fromBase64(dock_state.encode("ascii"))
                )
            except Exception:
                pass
        dock_geom = palette_state.get("dock_geometry")
        if isinstance(dock_geom, str) and dock_geom:
            try:
                self._lens_palette_dock.restoreGeometry(
                    QtCore.QByteArray.fromBase64(dock_geom.encode("ascii"))
                )
            except Exception:
                pass
        visible = bool(palette_state.get("palette_visible", False))
        self._lens_palette_dock.setVisible(visible)
        floating = bool(palette_state.get("palette_floating", False))
        self._dock_syncing = True
        try:
            self._lens_palette_dock.setFloating(floating)
        finally:
            self._dock_syncing = False
        if not dock_state and not dock_geom:
            self._apply_lens_palette_dock_size(force=True)
        else:
            self._apply_lens_palette_dock_size(floating=floating)
        self._apply_lens_palette_dock_size(floating=floating)

    def _show_lens_palette(self) -> None:
        self._ensure_lens_palette()
        self._ensure_lens_palette_dock()
        if not self._lens_palette_dock:
            return
        self._rebuild_lens_tiles()
        self._apply_lens_palette_flags()
        self._apply_lens_palette_dock_size()
        if not self._lens_palette_pinned:
            self._position_lens_palette()
        self._lens_palette_dock.show()
        self._lens_palette_dock.raise_()
        self._lens_palette_visible = True
        self.lens_palette_btn.setChecked(True)
        if not self._lens_palette_pinned:
            self._install_lens_palette_event_filter()
        else:
            self._remove_lens_palette_event_filter()
        self._schedule_lens_palette_dock_save()

    def _hide_lens_palette(self) -> None:
        if self._lens_palette_dock:
            self._lens_palette_dock.hide()
        self._lens_palette_visible = False
        self.lens_palette_btn.setChecked(False)
        self._remove_lens_palette_event_filter()
        self._schedule_lens_palette_dock_save()

    def _position_lens_palette(self) -> None:
        if not self._lens_palette_dock:
            return
        if not self._lens_palette_dock.isFloating():
            return
        anchor = self.lens_palette_btn
        if not anchor:
            return
        global_pos = anchor.mapToGlobal(QtCore.QPoint(0, anchor.height()))
        self._lens_palette_dock.move(global_pos + QtCore.QPoint(0, 6))

    def _set_lens_palette_pinned(self, pinned: bool) -> None:
        self._lens_palette_pinned = bool(pinned)
        view_config.save_lens_palette_state(
            self._workspace_id(),
            pinned=self._lens_palette_pinned,
            recent=self._lens_palette_recent,
        )
        if self._lens_palette_dock:
            self._apply_lens_palette_flags()
            self._apply_lens_palette_dock_size(floating=self._lens_palette_dock.isFloating())
            if self._lens_palette_visible and not self._lens_palette_pinned:
                self._position_lens_palette()
        if self._lens_palette_pinned and not self._lens_palette_visible:
            self._show_lens_palette()
        self._schedule_lens_palette_dock_save()

    # --- [NAV-40D] dock size + repaint
    def _apply_lens_palette_dock_size(
        self, *, floating: Optional[bool] = None, force: bool = False
    ) -> None:
        if not self._lens_palette_dock:
            return
        if self._dock_size_syncing:
            return
        if floating is None:
            floating = self._lens_palette_dock.isFloating()
        if floating:
            # Let floating palette keep its own geometry without clamp.
            self._lens_palette_dock.setMinimumSize(0, 0)
            self._dock_last_floating = True
            return
        should_normalize = force or self._dock_last_floating in (True, None)
        try:
            self._dock_size_syncing = True
            if should_normalize:
                min_width = int(ui_scale.scale_px(320))
                min_height = int(ui_scale.scale_px(360))
                # Apply a one-time normalization size, then relax minimums for free resizing.
                self._lens_palette_dock.setMinimumWidth(min_width)
                self._lens_palette_dock.setMinimumHeight(min_height)
                try:
                    area = self._dock_host.dockWidgetArea(self._lens_palette_dock)
                    orientation = lens_palette_dock_orientation(area)
                    if orientation is not None:
                        size_hint = min_width if orientation == QtCore.Qt.Orientation.Horizontal else min_height
                        self._dock_host.resizeDocks(
                            [self._lens_palette_dock],
                            [size_hint],
                            orientation,
                        )
                except Exception:
                    pass
                QtCore.QTimer.singleShot(
                    0, lambda: self._lens_palette_dock.setMinimumSize(0, 0)
                )
            else:
                # Already docked; don't re-normalize or clamp user resizing.
                self._lens_palette_dock.setMinimumSize(0, 0)
            self._dock_last_floating = False
        finally:
            self._dock_size_syncing = False

    def _select_lens_from_palette(self, lens_id: str) -> None:
        prev = self._lens
        lens_id = str(lens_id or "")
        if lens_id and lens_id != self._lens:
            target_index = None
            for idx in range(self.lens_combo.count()):
                item_id = self.lens_combo.itemData(idx)
                item_label = self.lens_combo.itemText(idx)
                if item_id == lens_id or (
                    item_label and item_label.lower() == lens_id.lower()
                ):
                    target_index = idx
                    break
            if target_index is None:
                self._log_lens_palette(f"lens_id not found: {lens_id}")
            else:
                self._log_lens_palette(f"select {prev} -> {lens_id} (index {target_index})")
                self.lens_combo.setCurrentIndex(target_index)
        else:
            self._log_lens_palette(f"select ignored: {lens_id} (current {prev})")
        if lens_id:
            self._remember_recent_lens(lens_id)
        self._sync_lens_palette_selection()
        if not self._lens_palette_pinned:
            QtCore.QTimer.singleShot(0, self._hide_lens_palette)

    def _sync_lens_palette_selection(self) -> None:
        if self._lens_palette:
            self._lens_palette.set_active_lens(self._lens)

    def _install_lens_palette_event_filter(self) -> None:
        if self._lens_palette_event_filter_installed:
            return
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._lens_palette_event_filter_installed = True

    def _remove_lens_palette_event_filter(self) -> None:
        if not self._lens_palette_event_filter_installed:
            return
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._lens_palette_event_filter_installed = False

    def _global_rect(self, widget: QtWidgets.QWidget) -> QtCore.QRect:
        top_left = widget.mapToGlobal(QtCore.QPoint(0, 0))
        return QtCore.QRect(top_left, widget.size())

    def _is_typing_widget(self) -> bool:
        focus = QtWidgets.QApplication.focusWidget()
        if focus is None:
            return False
        return isinstance(
            focus,
            (
                QtWidgets.QLineEdit,
                QtWidgets.QTextEdit,
                QtWidgets.QPlainTextEdit,
                QtWidgets.QSpinBox,
                QtWidgets.QDoubleSpinBox,
                QtWidgets.QComboBox,
            ),
        )

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        lens_palette_dock = getattr(self, "_lens_palette_dock", None)
        lens_palette = getattr(self, "_lens_palette", None)
        lens_palette_btn = getattr(self, "lens_palette_btn", None)
        lens_palette_visible = bool(getattr(self, "_lens_palette_visible", False))
        lens_palette_pinned = bool(getattr(self, "_lens_palette_pinned", False))

        if lens_palette_dock and obj is lens_palette_dock:
            if event.type() == QtCore.QEvent.Type.Hide:
                self._lens_palette_visible = False
                if lens_palette_btn is not None:
                    lens_palette_btn.setChecked(False)
                self._remove_lens_palette_event_filter()
        if (
            lens_palette_visible
            and not lens_palette_pinned
            and event.type() == QtCore.QEvent.Type.MouseButtonPress
        ):
            mouse_event = event  # type: ignore[assignment]
            global_pos = None
            if hasattr(mouse_event, "globalPosition"):
                global_pos = mouse_event.globalPosition().toPoint()
            elif hasattr(mouse_event, "globalPos"):
                global_pos = mouse_event.globalPos()
            target = lens_palette_dock if lens_palette_dock else lens_palette
            if global_pos and target:
                try:
                    inside_target = target.frameGeometry().contains(global_pos)
                except RuntimeError:
                    inside_target = True
                if not inside_target:
                    inside_button = False
                    if lens_palette_btn is not None:
                        inside_button = self._global_rect(lens_palette_btn).contains(global_pos)
                    if not inside_button:
                        self._hide_lens_palette()
        try:
            return super().eventFilter(obj, event)
        except RuntimeError:
            return False

    def _sync_icon_style_combo(self) -> None:
        for idx in range(self.icon_style_combo.count()):
            style = self.icon_style_combo.itemData(idx)
            if style == self._icon_style:
                self.icon_style_combo.blockSignals(True)
                self.icon_style_combo.setCurrentIndex(idx)
                self.icon_style_combo.blockSignals(False)
                return

    def _on_lens_changed(self, index: int) -> None:
        lens_id = self.lens_combo.itemData(index)
        if not lens_id or lens_id == self._lens:
            return
        self._log_lens_palette(f"apply lens change: {self._lens} -> {lens_id}")
        self._save_layout()
        view_config.save_view_config(
            self._workspace_id(),
            self._view_config,
            last_lens_id=str(lens_id),
            icon_style=self._icon_style,
        )
        self._lens = str(lens_id)
        self._view_config = view_config.load_view_config(self._workspace_id(), self._lens)
        self._icon_style = self._view_config.icon_style
        self._node_theme = self._view_config.node_theme
        self._pulse_settings = self._view_config.pulse_settings
        self._facet_settings = self._view_config.facet_settings
        self._monitor_enabled = bool(self._view_config.monitor_enabled)
        self._monitor_follow_last_trace = bool(self._view_config.monitor_follow_last_trace)
        self._monitor_show_edge_path = bool(self._view_config.monitor_show_edge_path)
        self._monitor.set_follow_last_trace(self._monitor_follow_last_trace)
        self._monitor.set_span_stuck_seconds(int(self._view_config.span_stuck_seconds))
        self._sync_view_controls()
        self.scene.set_node_theme(self._node_theme)
        self._render_current_graph()
        self._refresh_breadcrumb()
        self._update_mode_status(0, 0)
        self._remember_recent_lens(str(lens_id))
        if self._lens_palette:
            self._lens_palette.set_active_lens(self._lens)
            self._lens_palette.refresh()

    def _on_icon_style_changed(self, _index: int) -> None:
        style = self.icon_style_combo.currentData()
        if not style or style == self._icon_style:
            return
        self._set_icon_style(str(style))

    def _on_category_toggled(self, _checked: bool) -> None:
        for category, action in self._category_actions.items():
            self._view_config.show_categories[category] = action.isChecked()
        self._persist_view_config()
        self._render_current_graph()

    def _on_badge_layer_toggled(self, _checked: bool) -> None:
        for layer_id, action in self._badge_actions.items():
            self._view_config.show_badge_layers[layer_id] = action.isChecked()
        self._persist_view_config()
        self.scene.set_badge_layers(self._view_config.show_badge_layers)
        self.scene.update()
        self._update_mode_status(0, 0)

    def _set_quick_filter(self, key: str, checked: bool) -> None:
        if key not in self._view_config.quick_filters:
            return
        self._view_config.quick_filters[key] = bool(checked)
        self._persist_view_config()
        self._render_current_graph()
        self._update_mode_status(0, 0)

    def _set_diff_filter(self, key: str, checked: bool) -> None:
        if key not in self._diff_filters:
            return
        self._diff_filters[key] = bool(checked)
        self._render_current_graph()
        self._update_mode_status(0, 0)

    def _persist_view_config(self) -> None:
        self._view_config.live_enabled = bool(self._live_enabled)
        self._view_config.monitor_enabled = bool(self._monitor_enabled)
        self._view_config.monitor_follow_last_trace = bool(self._monitor_follow_last_trace)
        self._view_config.monitor_show_edge_path = bool(self._monitor_show_edge_path)
        self._view_config.pulse_settings = self._pulse_settings
        self._view_config.facet_settings = self._facet_settings
        view_config.save_view_config(
            self._workspace_id(),
            self._view_config,
            last_lens_id=self._lens,
            icon_style=self._icon_style,
        )

    def _clear_all_filters(self) -> None:
        current_theme = self._node_theme
        current_pulse = self._pulse_settings
        current_facets = self._facet_settings
        current_stuck = self._view_config.span_stuck_seconds
        current_monitor_enabled = self._monitor_enabled
        current_monitor_follow = self._monitor_follow_last_trace
        current_monitor_show_path = self._monitor_show_edge_path
        self._view_config = view_config.reset_to_defaults(self._lens, icon_style=self._icon_style)
        self._view_config.node_theme = current_theme
        self._view_config.pulse_settings = current_pulse
        self._view_config.facet_settings = current_facets
        self._view_config.span_stuck_seconds = current_stuck
        self._view_config.monitor_enabled = bool(current_monitor_enabled)
        self._view_config.monitor_follow_last_trace = bool(current_monitor_follow)
        self._view_config.monitor_show_edge_path = bool(current_monitor_show_path)
        self._node_theme = current_theme
        self._pulse_settings = current_pulse
        self._facet_settings = current_facets
        self._monitor_enabled = bool(current_monitor_enabled)
        self._monitor_follow_last_trace = bool(current_monitor_follow)
        self._monitor_show_edge_path = bool(current_monitor_show_path)
        self._monitor.set_follow_last_trace(self._monitor_follow_last_trace)
        self._monitor.set_span_stuck_seconds(int(current_stuck))
        self._diff_filters = {key: False for key in self._diff_filters}
        self._sync_view_controls()
        self._persist_view_config()
        self._render_current_graph()
        self._update_mode_status(0, 0)

    def _sync_monitor_actions(self) -> None:
        trace_id = str(self._monitor_active_trace_id or "")
        short_trace = trace_id[:8] if trace_id else ""
        if hasattr(self, "monitor_follow_action"):
            self.monitor_follow_action.blockSignals(True)
            self.monitor_follow_action.setChecked(self._monitor_follow_last_trace)
            self.monitor_follow_action.blockSignals(False)
            self.monitor_follow_action.setEnabled(self._monitor_enabled)
        if hasattr(self, "monitor_show_edge_action"):
            self.monitor_show_edge_action.blockSignals(True)
            self.monitor_show_edge_action.setChecked(self._monitor_show_edge_path)
            self.monitor_show_edge_action.blockSignals(False)
            self.monitor_show_edge_action.setEnabled(self._monitor_enabled)
        if hasattr(self, "monitor_clear_action"):
            self.monitor_clear_action.setEnabled(self._monitor_enabled)
        if hasattr(self, "monitor_pin_action"):
            self.monitor_pin_action.setEnabled(self._monitor_enabled and bool(trace_id))
            if short_trace:
                self.monitor_pin_action.setText(f"Pin Active Trace ({short_trace})")
            else:
                self.monitor_pin_action.setText("Pin Active Trace")
        if hasattr(self, "monitor_unpin_action"):
            self.monitor_unpin_action.setEnabled(self._monitor_enabled and self._monitor_trace_pinned)

    def _apply_monitor_overlay(self, *, now: Optional[float] = None) -> None:
        if not hasattr(self, "scene") or not self.scene:
            return
        if not self._monitor_enabled or not self._render_node_map:
            self.scene.set_monitor_states({})
            self.scene.set_trace_highlight([], set(), color=MONITOR_TRACE_COLOR)
            self._monitor_active_trace_id = None
            self._sync_monitor_actions()
            return
        current_now = float(time.time() if now is None else now)
        self._monitor.tick(current_now)
        states = self._monitor.snapshot_states()
        self.scene.set_monitor_states(states)
        edges, nodes, trace_id = self._monitor.snapshot_trace()
        if self._monitor_show_edge_path:
            self.scene.set_trace_highlight(edges, nodes, color=MONITOR_TRACE_COLOR)
        else:
            self.scene.set_trace_highlight([], set(), color=MONITOR_TRACE_COLOR)
        self._monitor_active_trace_id = trace_id
        self._sync_monitor_actions()

    def _clear_monitor_state(self) -> None:
        self._monitor.clear()
        self._monitor_trace_pinned = False
        self._monitor_active_trace_id = None
        self._apply_monitor_overlay(now=time.time())
        self._update_mode_status(0, 0)
        self.status_label.setText("Monitoring state cleared.")

    def _on_monitor_follow_toggled(self, checked: bool) -> None:
        self._monitor_follow_last_trace = bool(checked)
        self._monitor.set_follow_last_trace(self._monitor_follow_last_trace)
        self._persist_view_config()
        self._apply_monitor_overlay(now=time.time())
        self._update_mode_status(0, 0)

    def _on_monitor_show_edge_toggled(self, checked: bool) -> None:
        self._monitor_show_edge_path = bool(checked)
        self._persist_view_config()
        self._apply_monitor_overlay(now=time.time())
        self._update_mode_status(0, 0)

    def _pin_active_monitor_trace(self) -> None:
        trace_id = str(self._monitor_active_trace_id or "").strip()
        if not trace_id:
            return
        self._monitor.pin_trace(trace_id)
        self._monitor_trace_pinned = True
        self._apply_monitor_overlay(now=time.time())
        self._update_mode_status(0, 0)
        self.status_label.setText(f"Pinned trace {trace_id[:8]}.")

    def _unpin_monitor_trace(self) -> None:
        self._monitor.unpin_trace()
        self._monitor_trace_pinned = False
        self._apply_monitor_overlay(now=time.time())
        self._update_mode_status(0, 0)
        self.status_label.setText("Trace pin cleared.")

    def _filtered_graph(self, graph: ArchitectureGraph) -> ArchitectureGraph:
        lens = self._active_lens()
        now = time.time()
        stuck_threshold = max(1, int(self._view_config.span_stuck_seconds))
        nodes = []
        node_map: Dict[str, Node] = {}
        for node in graph.nodes:
            if not lens.node_predicate(node):
                continue
            if not _category_visible(node, self._view_config.show_categories):
                continue
            if not _passes_quick_filters(
                node,
                self._view_config.quick_filters,
                now=now,
                stuck_threshold=stuck_threshold,
            ):
                continue
            if self._diff_mode and self._diff_result:
                if not _passes_diff_filters(node.node_id, self._diff_result, self._diff_filters):
                    continue
            node_map[node.node_id] = node
            nodes.append(node)
        edges = []
        for edge in graph.edges:
            src = node_map.get(edge.src_node_id)
            dst = node_map.get(edge.dst_node_id)
            if not src or not dst:
                continue
            if not lens.edge_predicate(edge, src, dst):
                continue
            edges.append(edge)
        return ArchitectureGraph(
            graph_id=graph.graph_id,
            title=graph.title,
            nodes=nodes,
            edges=edges,
        )

    def _active_lens(self) -> LensSpec:
        lens = self._lens_map.get(self._lens)
        if lens:
            return lens
        return get_lens(self._lens)

    # --- [NAV-60A] apply runtime overlay
    def _apply_runtime_overlay(self, graph: ArchitectureGraph) -> ArchitectureGraph:
        if not self._live_enabled or not self._overlay_badges:
            return graph
        nodes = []
        for node in graph.nodes:
            overlay = self._overlay_badges.get(node.node_id)
            if overlay:
                merged = list(node.badges) + list(overlay)
                nodes.append(
                    Node(
                        node_id=node.node_id,
                        title=node.title,
                        node_type=node.node_type,
                        subgraph_id=node.subgraph_id,
                        badges=merged,
                        severity_state=node.severity_state,
                        checks=node.checks,
                        spans=node.spans,
                    )
                )
            else:
                nodes.append(node)
        return ArchitectureGraph(
            graph_id=graph.graph_id,
            title=graph.title,
            nodes=nodes,
            edges=graph.edges,
        )

    # --- [NAV-60B] apply expectation badges / span overlay
    def _apply_expectation_badges(self, graph: ArchitectureGraph) -> ArchitectureGraph:
        if not self._overlay_checks and not any(node.checks for node in graph.nodes):
            return graph
        nodes = []
        for node in graph.nodes:
            checks = list(node.checks)
            overlay = self._overlay_checks.get(node.node_id, [])
            if overlay:
                checks.extend(overlay)
            mismatch_badges = []
            for check in checks:
                if not check.passed:
                    mismatch_badges.append(_badge_for_check(check))
            if mismatch_badges or overlay:
                merged_badges = list(node.badges) + mismatch_badges
                nodes.append(
                    Node(
                        node_id=node.node_id,
                        title=node.title,
                        node_type=node.node_type,
                        subgraph_id=node.subgraph_id,
                        badges=merged_badges,
                        severity_state=node.severity_state,
                        checks=checks,
                        spans=node.spans,
                    )
                )
            else:
                nodes.append(node)
        return ArchitectureGraph(
            graph_id=graph.graph_id,
            title=graph.title,
            nodes=nodes,
            edges=graph.edges,
        )

    def _apply_span_overlay(self, graph: ArchitectureGraph) -> ArchitectureGraph:
        spans_by_node: Dict[str, list[SpanRecord]] = {}
        for node in graph.nodes:
            if node.spans:
                spans_by_node[node.node_id] = list(node.spans)
        runtime_spans: list[SpanRecord] = []
        if self._runtime_hub:
            runtime_spans.extend(self._runtime_hub.list_active_spans())
            runtime_spans.extend(self._runtime_hub.list_recent_spans())
        if runtime_spans:
            graph_node_ids = {node.node_id for node in graph.nodes}
            fallback_id = _span_fallback_node_id(graph, self._workspace_id())
            for span in runtime_spans:
                node_id = span.node_id
                if not node_id or node_id not in graph_node_ids:
                    node_id = fallback_id
                if node_id:
                    spans_by_node.setdefault(node_id, []).append(span)
        if not spans_by_node:
            return graph
        now = time.time()
        threshold = max(1, int(self._view_config.span_stuck_seconds))
        nodes: list[Node] = []
        for node in graph.nodes:
            spans = spans_by_node.get(node.node_id)
            if not spans:
                nodes.append(node)
                continue
            deduped: list[SpanRecord] = []
            seen = set()
            for span in spans:
                if span.span_id in seen:
                    continue
                deduped.append(span)
                seen.add(span.span_id)
            spans = deduped
            merged_badges = list(node.badges)
            merged_badges = _merge_span_badges(merged_badges, spans, now, threshold)
            nodes.append(
                Node(
                    node_id=node.node_id,
                    title=node.title,
                    node_type=node.node_type,
                    subgraph_id=node.subgraph_id,
                    badges=merged_badges,
                    severity_state=node.severity_state,
                    checks=node.checks,
                    spans=spans,
                )
            )
        return ArchitectureGraph(
            graph_id=graph.graph_id,
            title=graph.title,
            nodes=nodes,
            edges=graph.edges,
        )

    def _update_span_tints(self, graph: ArchitectureGraph) -> None:
        if not self._pulse_settings.tint_active_spans:
            self.scene.set_span_tints([], color=None, strength=0.0)
            return
        active_nodes: list[str] = []
        for node in graph.nodes:
            if any(span.status == "active" for span in node.spans or []):
                active_nodes.append(node.node_id)
        strength = max(0.08, min(0.35, float(self._pulse_settings.pulse_min_alpha)))
        self.scene.set_span_tints(active_nodes, color=QtGui.QColor("#4c6ef5"), strength=strength)

    def _on_ui_scale_changed(self, cfg: ui_scale.UiScaleConfig) -> None:
        clear_icon_cache()
        self._apply_density(cfg)
        self._render_current_graph()

    # --- [NAV-70A] UI scale / density
    def _apply_density(self, cfg: ui_scale.UiScaleConfig) -> None:
        spacing = ui_scale.density_spacing(8)
        if self._root_layout:
            self._root_layout.setSpacing(spacing)
        if self._breadcrumb_row:
            self._breadcrumb_row.setSpacing(spacing)
        if self._source_row:
            self._source_row.setSpacing(spacing)
        if self._mode_status_layout:
            self._mode_status_layout.setSpacing(spacing)
        if self._filter_status_layout:
            self._filter_status_layout.setSpacing(spacing)
        if getattr(self, "_debug_status_layout", None):
            self._debug_status_layout.setSpacing(spacing)

    def _filters_active(self) -> bool:
        if view_config.is_filtered(self._view_config):
            return True
        if self._lens != DEFAULT_LENS:
            return True
        if any(self._diff_filters.values()):
            return True
        if self._diff_mode:
            return True
        return False

    def _update_filter_status(self, total: int, shown: int) -> None:
        active = self._filters_active()
        self.filter_status_row.setVisible(active)
        if not active:
            return
        summary = _quick_filter_summary(self._view_config)
        diff_summary = _diff_filter_summary(self._diff_filters)
        label = f"Showing {shown} / {total} nodes"
        if summary:
            label = f"{label} | Filters: {summary}"
        if diff_summary:
            label = f"{label} | Diff: {diff_summary}"
        self.filter_status_label.setText(label)
        chips = view_config.build_active_filter_chips(self._view_config)
        lens_title = self._lens_map.get(self._lens).title if self._lens in self._lens_map else self._lens
        chips.insert(0, f"Lens: {lens_title}")
        if self._diff_mode:
            chips.append("Diff Mode")
        if diff_summary:
            chips.append(f"Diff: {diff_summary}")
        self._set_filter_chips(chips)

    def _set_filter_chips(self, chips: list[str]) -> None:
        while self.filter_chips_layout.count():
            item = self.filter_chips_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for chip in chips:
            label = QtWidgets.QLabel(chip)
            label.setStyleSheet(
                "background: #f0f0f0; border: 1px solid #ddd; border-radius: 8px; padding: 2px 6px; color: #333;"
            )
            self.filter_chips_layout.addWidget(label)
        self.filter_chips_layout.addStretch()

    def _update_debug_status(self) -> None:
        if not hasattr(self, "debug_status_row"):
            return
        if not self._runtime_hub:
            self.debug_status_row.setVisible(False)
            return
        event_count = self._runtime_hub.event_count()
        last_ts = self._runtime_hub.last_event_ts() or "n/a"
        signals = self.scene.signals_active_count() if self.scene else 0
        pulses = self.scene.active_pulse_count() if self.scene else 0
        spans = self._runtime_hub.active_span_count()
        bus_state = "bus:on" if self._runtime_hub.bus_connected() else "bus:off"
        self.debug_status_label.setText(
            f"{bus_state} | Events: {event_count} (last {last_ts}) | Signals: {signals} | Pulses: {pulses} | Spans: {spans}"
        )
        self.debug_status_row.setVisible(True)

    def _ensure_status_timer(self) -> None:
        if not self._status_timer:
            return
        active_signals = self.scene.signals_active_count() if self.scene else 0
        active_spans = self._runtime_hub.active_span_count() if self._runtime_hub else 0
        if active_signals or active_spans:
            if not self._status_timer.isActive():
                self._status_timer.start()

    # --- [NAV-70B] status tick
    def _on_status_tick(self) -> None:
        self._update_debug_status()
        self._refresh_span_activity()
        if self._monitor_enabled:
            self._apply_monitor_overlay(now=time.time())
            self._update_mode_status(0, 0)
        active_signals = self.scene.signals_active_count() if self.scene else 0
        active_spans = self._runtime_hub.active_span_count() if self._runtime_hub else 0
        if not active_signals and not active_spans:
            self._status_timer.stop()

    def _show_status_menu(self, node: Node, statuses: list, global_pos: QtCore.QPoint) -> None:
        if not statuses:
            return
        menu = QtWidgets.QMenu(self)
        total = 0
        normalized: list[dict] = []
        def _normalize_label(text: str) -> str:
            # Strip capped overflow markers like "8+" so the menu shows exact counts.
            return re.sub(r"(\d+)\+", r"\1", text)
        for status in statuses:
            count_raw = status.get("count", 1)
            count = 1
            if isinstance(count_raw, int):
                count = count_raw
            elif isinstance(count_raw, str):
                digits = "".join(ch for ch in count_raw if ch.isdigit())
                if digits:
                    count = int(digits)
            label = str(status.get("label") or "Status")
            detail = status.get("detail")
            if isinstance(label, str):
                label = _normalize_label(label)
            if isinstance(detail, str):
                detail = _normalize_label(detail)
            if not isinstance(count_raw, (int, str)):
                match = re.search(r"(\d+)", label if label else "")
                if match:
                    count = int(match.group(1))
            total += count
            normalized.append(
                {
                    **status,
                    "count": count,
                    "label": label,
                    "detail": detail,
                    "active_count": int(status.get("active_count", count)),
                    "total_count": int(status.get("total_count", count)),
                }
            )
        totals = {
            "Context": [0, 0],
            "Activity": [0, 0],
            "Pulses": [0, 0],
            "Signals": [0, 0],
            "Errors": [0, 0],
        }
        for status in normalized:
            key = str(status.get("key") or "")
            active_count = int(status.get("active_count", status.get("count", 1)))
            total_count = int(status.get("total_count", status.get("count", 1)))
            if key == "context":
                totals["Context"][0] += active_count
                totals["Context"][1] += total_count
            elif key == "pulse":
                totals["Pulses"][0] += active_count
                totals["Pulses"][1] += total_count
            elif key == "signal":
                totals["Signals"][0] += active_count
                totals["Signals"][1] += total_count
            elif key == "activity" or key.startswith("activity."):
                totals["Activity"][0] += active_count
                totals["Activity"][1] += total_count
            elif key in ("error", "state.error", "state.crash", "state.warn", "probe.fail", "expect.mismatch"):
                totals["Errors"][0] += active_count
                totals["Errors"][1] += total_count
        if any(active or total for active, total in totals.values()):
            totals_action = QtGui.QAction("Counts: Active now / Total (session)", menu)
            totals_action.setEnabled(False)
            menu.addAction(totals_action)
            for name, value in totals.items():
                active, total = value
                if active <= 0 and total <= 0:
                    continue
                total_line = QtGui.QAction(f"{name}: {_format_active_total(active, total)}", menu)
                total_line.setEnabled(False)
                menu.addAction(total_line)
        menu.addSeparator()
        for status in normalized:
            label = str(status.get("label") or "Status")
            detail = status.get("detail")
            if detail:
                label = f"{label}: {detail}"
            active_count = int(status.get("active_count", status.get("count", 1)))
            total_count = int(status.get("total_count", status.get("count", 1)))
            label = f"{label} ({_format_active_total(active_count, total_count)})"
            last_seen = status.get("last_seen")
            if isinstance(last_seen, (int, float)):
                label = f"{label} â€” {self._format_age(float(last_seen))} ago"
            action = QtGui.QAction(label, menu)
            icon = self._status_icon(status.get("color"))
            if icon:
                action.setIcon(icon)
            menu.addAction(action)
        menu.addSeparator()
        legend = [
            "M = Monitor state",
            "C = Current screen context",
            "A = Recent activity",
            "P = Pulse active",
            "S = Signals",
            "! = Error",
        ]
        for item in legend:
            legend_action = QtGui.QAction(item, menu)
            legend_action.setEnabled(False)
            menu.addAction(legend_action)
        menu.exec(global_pos)

    def _status_icon(self, color) -> Optional[QtGui.QIcon]:
        size = int(max(8, ui_scale.scale_px(10)))
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        if isinstance(color, QtGui.QColor):
            tint = color
        elif color:
            tint = QtGui.QColor(color)
        else:
            tint = QtGui.QColor("#666")
        painter.setBrush(tint)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, size, size)
        painter.end()
        return QtGui.QIcon(pixmap)

    def _format_age(self, age_s: float) -> str:
        if age_s < 1.0:
            return "0s"
        if age_s < 60.0:
            return f"{int(age_s)}s"
        if age_s < 3600.0:
            return f"{int(age_s // 60)}m"
        return f"{int(age_s // 3600)}h"

    def _refresh_span_activity(self) -> None:
        if not self._runtime_hub:
            return
        active_spans = self._runtime_hub.list_active_spans()
        if not active_spans:
            return
        self._render_current_graph()
        if self._pulse_settings.tint_active_spans:
            nodes = _active_span_node_ids(active_spans, limit=8)
            for node_id in nodes:
                self.scene.bump_activity(
                    node_id,
                    color=QtGui.QColor("#4c6ef5"),
                    strength=0.3,
                    linger_ms=int(self._pulse_settings.arrive_linger_ms),
                    fade_ms=int(self._pulse_settings.fade_ms),
                )
        if self._reduced_motion:
            return
        now = time.monotonic()
        if now - self._last_span_pulse < 2.5:
            return
        self._last_span_pulse = now
        nodes = _active_span_node_ids(active_spans, limit=4)
        for node_id in nodes:
            self.scene.flash_node_with_settings(
                node_id,
                color=QtGui.QColor("#4c6ef5"),
                settings=self._pulse_settings,
            )

    def _refresh_snapshot_history(self) -> None:
        self._snapshot_entries = snapshot_index.list_snapshots_sorted(self._workspace_id())
        baseline_path = self.baseline_combo.currentData()
        compare_path = self.compare_combo.currentData()
        self.baseline_combo.blockSignals(True)
        self.compare_combo.blockSignals(True)
        self.baseline_combo.clear()
        self.compare_combo.clear()
        self.baseline_combo.addItem("None", None)
        self.compare_combo.addItem("None", None)
        for entry in self._snapshot_entries:
            label = _snapshot_label(entry)
            path = entry.get("path")
            self.baseline_combo.addItem(label, path)
            self.compare_combo.addItem(label, path)
        if baseline_path:
            _set_combo_by_data(self.baseline_combo, baseline_path)
        if compare_path:
            _set_combo_by_data(self.compare_combo, compare_path)
        self.baseline_combo.blockSignals(False)
        self.compare_combo.blockSignals(False)
        self._update_action_state()

    def _on_baseline_changed(self, _index: int) -> None:
        if self._diff_mode:
            self._update_diff_result()
            self._render_current_graph()

    def _on_compare_changed(self, _index: int) -> None:
        if self._diff_mode:
            self._update_diff_result()
            self._render_current_graph()

    def _on_diff_toggled(self, checked: bool) -> None:
        self._diff_mode = checked
        if checked:
            self._update_diff_result()
        else:
            self._diff_result = None
            self._diff_baseline_graph = None
            self._diff_compare_graph = None
            self._diff_filters = {key: False for key in self._diff_filters}
            self._sync_view_controls()
        self._update_action_state()
        self._render_current_graph()

    def _on_live_toggled(self, checked: bool) -> None:
        if self._safe_mode:
            self._live_enabled = False
            self.live_toggle.blockSignals(True)
            self.live_toggle.setChecked(False)
            self.live_toggle.blockSignals(False)
            return
        if not self._runtime_hub:
            self._live_enabled = False
            self.live_toggle.blockSignals(True)
            self.live_toggle.setChecked(False)
            self.live_toggle.blockSignals(False)
            return
        self._live_enabled = checked
        self._persist_view_config()
        self._update_action_state()
        self._render_current_graph()
        self._update_debug_status()

    def _on_monitor_toggled(self, checked: bool) -> None:
        self._monitor_enabled = bool(checked)
        self._persist_view_config()
        self._render_current_graph()
        self._apply_monitor_overlay(now=time.time())
        self._sync_monitor_actions()
        self._update_action_state()
        self._update_mode_status(0, 0)
        self._update_debug_status()

    def _open_in_window(self) -> None:
        if self._on_open_window:
            self._on_open_window()

    def _refresh_current_graph(self) -> None:
        if self._source == SOURCE_ATLAS:
            self._build_atlas()
            return
        if self._source == SOURCE_SNAPSHOT:
            self._load_latest_snapshot(show_status=True)
            return
        if self._source == SOURCE_DEMO:
            self._set_active_graphs(self._demo_root, self._demo_subgraphs)
            return

    def _emit_test_pulse(self) -> None:
        target_id, source_id = self._select_pulse_nodes()
        if not target_id:
            return
        node_ids = [target_id]
        if source_id and source_id != target_id:
            node_ids = [source_id, target_id]
        event = CodeSeeEvent(
            ts=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            kind=EVENT_TEST_PULSE,
            severity="info",
            message="Test pulse",
            node_ids=node_ids,
            source="codesee",
            source_node_id=source_id,
            target_node_id=target_id,
        )
        if self._runtime_hub:
            self._runtime_hub.publish(event)
        self._emit_live_signal(event)
        self._update_debug_status()
        self._ensure_status_timer()

    def _select_pulse_nodes(self) -> tuple[Optional[str], Optional[str]]:
        graph = self._current_graph
        if self._diff_mode and self._diff_compare_graph:
            graph = self._diff_compare_graph
        if not graph or not graph.nodes:
            return None, None
        target_id = None
        for node in graph.nodes:
            if node.node_id.startswith("workspace:") or node.node_id == "system:app_ui":
                target_id = node.node_id
                break
        if not target_id:
            target_id = graph.nodes[0].node_id
        source_id = None
        for node in graph.nodes:
            if node.node_id != target_id:
                source_id = node.node_id
                break
        return target_id, source_id or target_id

    def _update_diff_result(self) -> None:
        baseline_path = self.baseline_combo.currentData()
        compare_path = self.compare_combo.currentData()
        if not baseline_path or not compare_path or baseline_path == compare_path:
            self._diff_result = None
            self._diff_baseline_graph = None
            self._diff_compare_graph = None
            self.status_label.setText("Select two different snapshots for diff mode.")
            self._update_action_state()
            return
        baseline_graph = self._load_snapshot_by_path(str(baseline_path))
        compare_graph = self._load_snapshot_by_path(str(compare_path))
        if not baseline_graph or not compare_graph:
            self._diff_result = None
            self._diff_baseline_graph = None
            self._diff_compare_graph = None
            self.status_label.setText("Snapshot diff load failed.")
            self._update_action_state()
            return
        self._diff_baseline_graph = baseline_graph
        self._diff_compare_graph = compare_graph
        self._diff_result = diff_snapshots(baseline_graph, compare_graph)
        summary = (
            f"Diff: +{len(self._diff_result.nodes_added)} "
            f"-{len(self._diff_result.nodes_removed)} "
            f"I{len(self._diff_result.nodes_changed)}"
        )
        self.status_label.setText(summary)
        self._update_action_state()

    # --- [NAV-70C] runtime event handler
    def _on_runtime_event(self, event: CodeSeeEvent) -> None:
        now = time.time()
        for node_id in event.node_ids or []:
            events = self._events_by_node.setdefault(node_id, [])
            events.append(event)
            if len(events) > self._overlay_limit:
                self._events_by_node[node_id] = events[-self._overlay_limit :]
            if self._live_enabled:
                self._add_overlay_badge(node_id, event)
                self._add_overlay_check(node_id, event)
        self._monitor.on_event(event)
        if self._live_enabled:
            self._render_current_graph()
            self._emit_live_signal(event)
        if event.kind in (EVENT_SPAN_START, EVENT_SPAN_UPDATE, EVENT_SPAN_END) and not self._live_enabled:
            self._render_current_graph()
        if self._monitor_enabled:
            self._apply_monitor_overlay(now=now)
            self._update_mode_status(0, 0)
        self._update_debug_status()
        self._ensure_status_timer()

    def _add_overlay_badge(self, node_id: str, event: CodeSeeEvent) -> None:
        key = _badge_key_for_event(event)
        if not key:
            return
        badge = badge_from_key(key, detail=event.message, timestamp=event.ts)
        overlay = self._overlay_badges.setdefault(node_id, [])
        overlay.append(badge)
        if len(overlay) > self._overlay_limit:
            self._overlay_badges[node_id] = overlay[-self._overlay_limit :]

    def _add_overlay_check(self, node_id: str, event: CodeSeeEvent) -> None:
        if event.kind != EVENT_EXPECT_CHECK or not isinstance(event.payload, dict):
            return
        check = check_from_dict(event.payload)
        if not check:
            return
        overlay = self._overlay_checks.setdefault(node_id, [])
        overlay.append(check)
        if len(overlay) > self._overlay_limit:
            self._overlay_checks[node_id] = overlay[-self._overlay_limit :]

    def _emit_live_signal(self, event: CodeSeeEvent) -> None:
        if not _pulse_topic_enabled(self._pulse_settings, event.kind):
            return
        node_ids = event.node_ids or []
        target_id = event.target_node_id or (node_ids[-1] if node_ids else None)
        source_id = event.source_node_id
        if not source_id and len(node_ids) > 1:
            source_id = node_ids[0]
        if not source_id and isinstance(event.source, str):
            if event.source in ("app_ui", "codesee", "ui"):
                source_id = "system:app_ui"
        if not target_id:
            return
        color = _event_color(event)
        self.scene.emit_signal(
            source_id=source_id,
            target_id=target_id,
            kind=event.kind,
            color=color,
            settings=self._pulse_settings,
        )
        self.scene.bump_activity(
            target_id,
            color=color,
            strength=float(self._pulse_settings.pulse_alpha),
            linger_ms=int(self._pulse_settings.arrive_linger_ms),
            fade_ms=int(self._pulse_settings.fade_ms),
        )

    # --- [NAV-80A] snapshot load + removed dialog + pulse settings
    def _load_snapshot_by_path(self, path_value: str) -> Optional[ArchitectureGraph]:
        try:
            return snapshot_io.read_snapshot(Path(path_value))
        except Exception:
            return None

    def _open_removed_dialog(self) -> None:
        if not self._diff_result:
            return
        dialog = CodeSeeRemovedDialog(self._diff_result, parent=self)
        dialog.exec()

    def _resolved_icon_style(self) -> str:
        return icon_pack.resolve_style(self._icon_style, self._reduced_motion)

    def _set_icon_style(self, style: str) -> None:
        if not style:
            return
        self._icon_style = style
        self._view_config.icon_style = style
        icon_pack.save_style(self._workspace_id(), style)
        self._persist_view_config()
        self.scene.set_icon_style(self._resolved_icon_style())
        if self._lens_palette:
            self._rebuild_lens_tiles()

    def _set_node_theme(self, theme: str) -> None:
        if not theme:
            return
        self._node_theme = str(theme)
        self._view_config.node_theme = self._node_theme
        self._persist_view_config()
        self.scene.set_node_theme(self._node_theme)
        self.scene.update()

    def _open_pulse_settings(self) -> None:
        new_settings = open_pulse_settings(self, self._pulse_settings)
        if new_settings is None:
            return
        self._pulse_settings = new_settings
        self._view_config.pulse_settings = self._pulse_settings
        self._persist_view_config()
        self._render_current_graph()

    def _on_set_facet_density(self, density: str) -> None:
        normalized = str(density or "").strip().lower()
        if normalized not in view_config.FACET_DENSITIES:
            normalized = "minimal"
        current_enabled = _facet_enabled_defaults_for_density(normalized)
        for key, value in dict(getattr(self._facet_settings, "enabled", {})).items():
            if key in current_enabled and isinstance(value, bool):
                current_enabled[key] = value
        self._facet_settings = view_config.FacetSettings(
            density=normalized,
            enabled=current_enabled,
            facet_scope=self._facet_scope(),
            show_in_normal_view=bool(self._facet_settings.show_in_normal_view),
            show_in_peek_view=bool(self._facet_settings.show_in_peek_view),
        )
        self._view_config.facet_settings = self._facet_settings
        self._persist_view_config()
        self._render_current_graph()
        if self._source != SOURCE_DEMO and normalized != "off":
            self._show_facet_source_hint()

    def _on_set_facet_scope(self, scope: str) -> None:
        normalized = str(scope or "").strip().lower()
        if normalized not in getattr(view_config, "FACET_SCOPES", ("selected", "peek_graph")):
            normalized = "selected"
        if normalized == self._facet_scope():
            return
        self._facet_settings = view_config.FacetSettings(
            density=self._facet_settings.density,
            enabled=dict(getattr(self._facet_settings, "enabled", {})),
            facet_scope=normalized,
            show_in_normal_view=bool(self._facet_settings.show_in_normal_view),
            show_in_peek_view=bool(self._facet_settings.show_in_peek_view),
        )
        self._view_config.facet_settings = self._facet_settings
        self._persist_view_config()
        self._render_current_graph()
        if self._source != SOURCE_DEMO:
            self._show_facet_source_hint()

    def _on_toggle_facet_enabled(self, key: str, enabled: bool) -> None:
        if key not in view_config.FACET_KEYS:
            return
        next_enabled = dict(getattr(self._facet_settings, "enabled", {}))
        next_enabled[key] = bool(enabled)
        self._facet_settings = view_config.FacetSettings(
            density=self._facet_settings.density,
            enabled=next_enabled,
            facet_scope=self._facet_scope(),
            show_in_normal_view=bool(self._facet_settings.show_in_normal_view),
            show_in_peek_view=bool(self._facet_settings.show_in_peek_view),
        )
        self._view_config.facet_settings = self._facet_settings
        self._persist_view_config()
        self._render_current_graph()

    def _on_open_facet_settings(self) -> None:
        self._open_facet_settings()

    def _open_facet_settings(self) -> None:
        new_settings = open_facet_settings(self, self._facet_settings)
        if new_settings is None:
            return
        density = str(new_settings.density or "").strip().lower()
        if density not in view_config.FACET_DENSITIES:
            density = "minimal"
        enabled = _facet_enabled_defaults_for_density(density)
        for key, value in dict(getattr(new_settings, "enabled", {})).items():
            if key in enabled and isinstance(value, bool):
                enabled[key] = value
        facet_scope = str(getattr(new_settings, "facet_scope", "selected") or "selected").strip().lower()
        if facet_scope not in getattr(view_config, "FACET_SCOPES", ("selected", "peek_graph")):
            facet_scope = "selected"
        self._facet_settings = view_config.FacetSettings(
            density=density,
            enabled=enabled,
            facet_scope=facet_scope,
            show_in_normal_view=bool(new_settings.show_in_normal_view),
            show_in_peek_view=bool(new_settings.show_in_peek_view),
        )
        self._view_config.facet_settings = self._facet_settings
        self._persist_view_config()
        self._render_current_graph()
        if self._source != SOURCE_DEMO and density != "off":
            self._show_facet_source_hint()

    def _show_facet_source_hint(self) -> None:
        self.status_label.setText(FACET_SOURCE_HINT)

    def _save_preset(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(self, "Save preset", "Preset name:")
        if not ok:
            return
        preset_name = (name or "").strip()
        if not preset_name:
            return
        preset = view_config.build_view_preset(
            self._view_config,
            lens_id=self._lens,
            icon_style=self._icon_style,
            node_theme=self._node_theme,
        )
        view_config.save_view_preset(self._workspace_id(), preset_name, preset)
        self._build_presets_menu()
        self._build_more_menu()

    def _apply_preset(self, name: str) -> None:
        presets = view_config.load_view_presets(self._workspace_id())
        preset = presets.get(name)
        if not isinstance(preset, dict):
            return
        lens_id = preset.get("lens_id") or self._lens
        self._lens = str(lens_id)
        self._view_config = view_config.default_view_config(self._lens, icon_style=self._icon_style)
        self._view_config = view_config.apply_view_preset(self._view_config, preset)
        icon_style = preset.get("icon_style")
        if isinstance(icon_style, str) and icon_style:
            self._icon_style = icon_style
        node_theme = preset.get("node_theme")
        if isinstance(node_theme, str) and node_theme:
            self._node_theme = node_theme
            self._view_config.node_theme = node_theme
        self._live_enabled = bool(self._view_config.live_enabled)
        self._monitor_enabled = bool(self._view_config.monitor_enabled)
        self._monitor_follow_last_trace = bool(self._view_config.monitor_follow_last_trace)
        self._monitor_show_edge_path = bool(self._view_config.monitor_show_edge_path)
        self._monitor.set_follow_last_trace(self._monitor_follow_last_trace)
        self._monitor.set_span_stuck_seconds(int(self._view_config.span_stuck_seconds))
        self._pulse_settings = self._view_config.pulse_settings
        self._facet_settings = self._view_config.facet_settings
        self._sync_view_controls()
        self.scene.set_node_theme(self._node_theme)
        self.scene.set_icon_style(self._resolved_icon_style())
        self._render_current_graph()
        self._update_mode_status(0, 0)

    def _emit_harness_activity(self) -> None:
        if not harness.is_enabled() or not self._runtime_hub:
            return
        graph = self._current_graph
        if self._diff_mode and self._diff_compare_graph:
            graph = self._diff_compare_graph
        node_ids = [node.node_id for node in graph.nodes] if graph else []
        source_id, target_id, ids = harness.pick_pulse_nodes(node_ids)
        harness.emit_test_activity(
            self._runtime_hub,
            source_id=source_id,
            target_id=target_id,
            node_ids=ids,
        )

    def _emit_harness_mismatch(self) -> None:
        if not harness.is_enabled() or not self._runtime_hub:
            return
        graph = self._current_graph
        if self._diff_mode and self._diff_compare_graph:
            graph = self._diff_compare_graph
        node_ids = [node.node_id for node in graph.nodes] if graph else []
        target = "system:content_system" if "system:content_system" in node_ids else (node_ids[0] if node_ids else None)
        if not target:
            return
        harness.emit_mismatch(self._runtime_hub, node_id=target)
        self._render_current_graph()

    def _emit_harness_crash(self) -> None:
        if not harness.is_enabled():
            return
        path = harness.write_fake_crash(self._workspace_id())
        if path:
            self._crash_record = crash_io.read_latest_crash(self._workspace_id())
            self._render_current_graph()

    def _toggle_harness_pack(self) -> None:
        if not harness.is_enabled():
            return
        state = harness.toggle_fake_pack()
        if self._source == SOURCE_ATLAS:
            self._build_atlas()
        else:
            self.status_label.setText(f"Harness pack {'enabled' if state else 'disabled'} (switch to Atlas).")

    def _ensure_inspector_panel(self) -> None:
        if self._inspector_panel is not None and self._inspector_dock is not None:
            return
        panel = CodeSeeInspectorPanel(
            on_back=self._on_inspector_back,
            on_forward=self._on_inspector_forward,
            on_lock_toggled=self._on_inspector_lock_toggled,
            on_relation_selected=self._on_inspector_relation_selected,
            on_relation_inspect=self._on_inspector_relation_inspect,
            parent=self,
        )
        panel.set_navigation_state(can_back=False, can_forward=False)
        panel.set_empty("Select a node to inspect.")
        dock = QtWidgets.QDockWidget("Inspector", self._dock_host)
        dock.setObjectName("codeseeInspectorDock")
        dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        dock.setAllowedAreas(
            QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
            | QtCore.Qt.DockWidgetArea.RightDockWidgetArea
            | QtCore.Qt.DockWidgetArea.BottomDockWidgetArea
            | QtCore.Qt.DockWidgetArea.TopDockWidgetArea
        )
        dock.setWidget(panel)
        self._dock_host.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.setMinimumWidth(int(ui_scale.scale_px(320)))
        self._inspector_panel = panel
        self._inspector_dock = dock

    def _inspect_node(self, node: Node, badge: Optional[Badge]) -> None:
        self._active_facet_selection = self._facet_selection_from_node(node)
        item_ref = itemref_from_node(node)
        self.selected_item = item_ref
        if self._peek.peek_active:
            self._set_peek_breadcrumb(item_ref)
        if not self.inspector_locked:
            self._set_inspected_item(item_ref, push_history=True)
        else:
            self.status_label.setText("Inspector pinned; selection updated only.")
            self._refresh_inspector_panel()
        if badge:
            self.status_label.setText(f"Inspected {node.title} via badge: {badge.title}")
        if self._inspector_dock:
            self._inspector_dock.show()
            self._inspector_dock.raise_()

    def _on_scene_selection_changed(self) -> None:
        scene = getattr(self, "scene", None)
        if scene is None:
            return
        try:
            selected_items = scene.selectedItems()
        except RuntimeError:
            return
        node_item = next((item for item in selected_items if isinstance(item, NodeItem)), None)
        if not node_item:
            return
        self._active_facet_selection = self._facet_selection_from_node(node_item.node)
        item_ref = itemref_from_node(node_item.node)
        self.selected_item = item_ref
        if self._peek.peek_active:
            self._set_peek_breadcrumb(item_ref)
        if not self.inspector_locked:
            self._set_inspected_item(item_ref, push_history=True)
        else:
            self._refresh_inspector_panel()

    def _set_inspected_item(self, item_ref: ItemRef, *, push_history: bool) -> None:
        self.inspected_item = item_ref
        if push_history:
            self._push_inspected_history(item_ref)
        self._refresh_inspector_panel()

    def _push_inspected_history(self, item_ref: ItemRef) -> None:
        if self.inspected_history_index >= 0:
            current = self.inspected_history[self.inspected_history_index]
            if current == item_ref:
                return
        if self.inspected_history_index < len(self.inspected_history) - 1:
            self.inspected_history = self.inspected_history[: self.inspected_history_index + 1]
        self.inspected_history.append(item_ref)
        self.inspected_history_index = len(self.inspected_history) - 1

    def _on_inspector_back(self) -> None:
        if self.inspected_history_index <= 0:
            return
        self.inspected_history_index -= 1
        self.inspected_item = self.inspected_history[self.inspected_history_index]
        self._refresh_inspector_panel()

    def _on_inspector_forward(self) -> None:
        if self.inspected_history_index >= len(self.inspected_history) - 1:
            return
        self.inspected_history_index += 1
        self.inspected_item = self.inspected_history[self.inspected_history_index]
        self._refresh_inspector_panel()

    def _on_inspector_lock_toggled(self, locked: bool) -> None:
        self.inspector_locked = bool(locked)
        self._refresh_inspector_panel()

    def _on_inspector_relation_selected(self, item_ref: ItemRef) -> None:
        self._active_facet_selection = None
        self.selected_item = item_ref
        if self._peek.peek_active:
            self._set_peek_breadcrumb(item_ref)
        if not self.inspector_locked:
            self._set_inspected_item(item_ref, push_history=True)
            return
        self.status_label.setText("Inspector pinned; selection updated only.")
        self._refresh_inspector_panel()

    def _on_inspector_relation_inspect(self, item_ref: ItemRef) -> None:
        self._active_facet_selection = None
        self.selected_item = item_ref
        if self._peek.peek_active:
            self._set_peek_breadcrumb(item_ref)
        self._set_inspected_item(item_ref, push_history=True)

    def _resolve_node_for_item(self, item_ref: ItemRef) -> Optional[Node]:
        if item_ref.kind != "node":
            return None
        graph = self._current_graph
        if self._diff_mode and self._diff_compare_graph:
            graph = self._diff_compare_graph
        if graph:
            resolved = graph.get_node(item_ref.id)
            if resolved is not None:
                return resolved
        return self._render_node_map.get(item_ref.id)

    def _inspector_properties(self, node: Node) -> Dict[str, str]:
        props: Dict[str, str] = {
            "node_type": str(node.node_type),
            "subgraph_id": str(node.subgraph_id or ""),
            "severity": str(node.effective_severity()),
            "badges": str(len(node.badges)),
            "checks": str(len(node.checks)),
            "spans": str(len(node.spans)),
        }
        metadata = node.metadata if isinstance(node.metadata, dict) else {}
        for key in sorted(metadata.keys()):
            value = metadata.get(key)
            if isinstance(value, (dict, list, tuple, set)):
                props[f"meta.{key}"] = repr(value)
            else:
                props[f"meta.{key}"] = "" if value is None else str(value)
        return props

    def _graph_revision_key(
        self,
        root: Optional[ArchitectureGraph],
        subgraphs: Dict[str, ArchitectureGraph],
    ) -> tuple:
        root_key: Optional[tuple] = None
        if root is not None:
            root_key = (str(root.graph_id), len(root.nodes), len(root.edges), id(root))
        subgraph_keys = []
        for graph_id in sorted(subgraphs.keys()):
            graph = subgraphs.get(graph_id)
            if graph is None:
                continue
            subgraph_keys.append((str(graph.graph_id), len(graph.nodes), len(graph.edges), id(graph)))
        return (root_key, tuple(subgraph_keys))

    def _relation_index_for_inspector(self) -> RelationIndex:
        if self._diff_mode and self._diff_compare_graph is not None:
            graph = self._diff_compare_graph
            key = (str(graph.graph_id), len(graph.nodes), len(graph.edges), id(graph))
            if self._relation_index_compare is None or self._relation_index_compare_key != key:
                self._relation_index_compare = build_relation_index(graph, {})
                self._relation_index_compare_key = key
            return self._relation_index_compare

        key = self._graph_revision_key(self._active_root, self._active_subgraphs)
        if self._relation_index_normal is None or self._relation_index_normal_key != key:
            self._relation_index_normal = build_relation_index(self._active_root, self._active_subgraphs)
            self._relation_index_normal_key = key
        return self._relation_index_normal

    def _relation_revision_key_for_inspector(self) -> tuple:
        if self._diff_mode and self._diff_compare_graph is not None:
            graph = self._diff_compare_graph
            return ("diff", str(graph.graph_id), len(graph.nodes), len(graph.edges), id(graph))
        return ("active", self._graph_revision_key(self._active_root, self._active_subgraphs))

    def _refresh_inspector_panel(self) -> None:
        self._ensure_inspector_panel()
        if not self._inspector_panel:
            return
        can_back = self.inspected_history_index > 0
        can_forward = 0 <= self.inspected_history_index < len(self.inspected_history) - 1
        self._inspector_panel.set_navigation_state(can_back=can_back, can_forward=can_forward)
        self._inspector_panel.set_locked(self.inspector_locked)
        item_ref = self.inspected_item
        if item_ref is None:
            self._inspector_relations_state_key = None
            self._inspector_panel.set_empty("Select a node to inspect.")
            return
        node = self._resolve_node_for_item(item_ref)
        if node is None:
            self._inspector_relations_state_key = None
            self._inspector_panel.set_stale(item_ref)
            return
        facet_selection = self._facet_selection_by_id.get(item_ref.id) or self._facet_selection_from_node(node)
        if facet_selection is not None:
            self._active_facet_selection = facet_selection
        else:
            self._active_facet_selection = None
        name = node.title or itemref_display_name(item_ref)
        summary = "Overview details are available. Use Relations and Activity tabs for deeper context."
        self._inspector_panel.set_content(
            item_ref=item_ref,
            name=name,
            kind=item_ref.kind,
            summary=summary,
            properties=self._inspector_properties(node),
        )
        if facet_selection is not None:
            self._refresh_facet_inspector(item_ref, node, facet_selection)
            return
        self._inspector_panel.show_activity(
            mode="activity",
            title=f"{name} activity",
            items=self._build_activity_rows_for_node(item_ref.id, mode="activity"),
            activate=False,
        )
        relation_revision = self._relation_revision_key_for_inspector()
        state_key = (item_ref.kind, item_ref.id, relation_revision)
        if self._inspector_relations_state_key == state_key:
            return
        relation_index = self._relation_index_for_inspector()

        def provider(category: str, offset: int, limit: int, filter_text: str):
            return query_relation_page(
                relation_index,
                item_ref,
                category,
                offset,
                limit,
                filter_text,
            )

        self._inspector_panel.set_relations_provider(item_ref, provider)
        self._inspector_relations_state_key = state_key

    def _refresh_facet_inspector(self, item_ref: ItemRef, node: Node, selection: FacetSelection) -> None:
        if not self._inspector_panel:
            return
        base_ref = ItemRef(kind="node", id=selection.base_node_id)
        base_node = self._resolve_node_for_item(base_ref)
        base_name = base_node.title if base_node is not None else selection.base_node_id
        title = f"{base_name} / {selection.facet_label}"
        self._inspector_panel.set_content(
            item_ref=item_ref,
            name=title,
            kind="facet",
            summary="Facet node selected. Canvas remains stable while Inspector focuses the selected facet.",
            properties={
                "facet_key": selection.facet_key,
                "base_node_id": selection.base_node_id,
                "facet_label": selection.facet_label,
            },
        )
        if selection.facet_key in FACET_KEYS_RELATIONS:
            relation_revision = self._relation_revision_key_for_inspector()
            state_key = ("facet_rel", item_ref.id, selection.facet_key, selection.base_node_id, relation_revision)
            if self._inspector_relations_state_key != state_key:
                relation_index = self._relation_index_for_inspector()

                def provider(category: str, offset: int, limit: int, filter_text: str):
                    return query_relation_page(
                        relation_index,
                        base_ref,
                        category,
                        offset,
                        limit,
                        filter_text,
                    )

                self._inspector_panel.set_relations_provider(base_ref, provider)
                self._inspector_relations_state_key = state_key
            self._inspector_panel.show_relations(
                mode=selection.facet_key,
                title=f"{selection.facet_label} for {base_name}",
            )
            self._inspector_panel.select_tab("relations")
            return

        self._inspector_relations_state_key = ("facet_act", item_ref.id, selection.facet_key, selection.base_node_id)
        self._inspector_panel.show_activity(
            mode=selection.facet_key,
            title=f"{selection.facet_label} for {base_name}",
            items=self._build_activity_rows_for_node(selection.base_node_id, mode=selection.facet_key),
        )
        self._inspector_panel.select_tab("activity")

    def _build_activity_rows_for_node(self, node_id: str, *, mode: str) -> list[dict[str, str]]:
        mode_key = (mode or "").strip().lower()
        rows: list[dict[str, str]] = []
        events = list(self._events_by_node.get(node_id, []))
        for event in reversed(events[-120:]):
            if not _event_matches_activity_mode(event, mode_key):
                continue
            rows.append(
                {
                    "when": str(event.ts or ""),
                    "type": str(event.kind or ""),
                    "source": str(event.source or "runtime"),
                    "detail": str(event.message or event.detail or ""),
                }
            )
            if len(rows) >= 80:
                break
        if mode_key in ("spans", "runs", "activity") and self._runtime_hub:
            span_rows = _span_rows_for_node(
                self._runtime_hub.list_active_spans() + self._runtime_hub.list_recent_spans(),
                node_id=node_id,
                mode=mode_key,
                limit=max(0, 80 - len(rows)),
            )
            rows.extend(span_rows)
        if not rows:
            rows.append(
                {
                    "when": "",
                    "type": mode_key or "activity",
                    "source": "codesee",
                    "detail": f"No data yet for {(mode_key or 'activity').replace('_', ' ')}.",
                }
            )
        return rows[:80]

    def _build_atlas(self) -> None:
        ctx = CollectorContext(
            workspace_id=self._workspace_id(),
            workspace_info=self._workspace_info_provider() or {},
            bus=self._bus,
            content_adapter=self._content_adapter,
        )
        if self._safe_mode:
            try:
                root, subgraphs = build_atlas_graph(ctx)
            except Exception as exc:
                self.status_label.setText(f"Atlas build failed: {exc}")
                return
        else:
            root, subgraphs = build_atlas_graph(ctx)
        self._atlas_root = root
        self._atlas_subgraphs = subgraphs
        self._set_active_graphs(root, subgraphs)
        self.status_label.setText("Atlas graph ready.")

    def _snapshot_dir(self) -> Path:
        return Path("data") / "workspaces" / self._workspace_id() / "codesee" / "snapshots"

    def _latest_snapshot_path(self) -> Optional[Path]:
        directory = self._snapshot_dir()
        if not directory.exists():
            return None
        snapshots = sorted(directory.glob("*.json"))
        if not snapshots:
            return None
        return snapshots[-1]

    def _sanitize_graph_id(self, graph_id: str) -> str:
        safe = graph_id.replace(":", "_").replace("/", "_")
        return safe or "graph"

    def _capture_snapshot(self) -> None:
        if not self._current_graph:
            self.status_label.setText("No graph loaded to snapshot.")
            return
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        safe_graph = self._sanitize_graph_id(self._current_graph.graph_id)
        path = self._snapshot_dir() / f"{timestamp}_{safe_graph}.json"
        metadata = {
            "source": self._source,
            "workspace_id": self._workspace_id(),
            "graph_id": self._current_graph.graph_id,
            "lens_id": self._lens,
            "timestamp": timestamp,
        }
        graph_to_save = self._apply_runtime_overlay(self._current_graph)
        graph_to_save = self._apply_expectation_badges(graph_to_save)
        graph_to_save = self._apply_span_overlay(graph_to_save)
        graph_to_save = self._apply_crash_badge(graph_to_save)
        snapshot_io.write_snapshot(graph_to_save, path, metadata)
        self.status_label.setText(f"Snapshot saved: {path.name}")
        self._refresh_snapshot_history()
        if self._runtime_hub:
            event = CodeSeeEvent(
                ts=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                kind=EVENT_APP_ACTIVITY,
                severity="info",
                message=f"Snapshot captured: {path.name}",
                node_ids=["system:app_ui"],
                detail=str(path),
                source="codesee",
            )
            self._runtime_hub.publish(event)

    def _load_latest_snapshot_action(self) -> None:
        self._load_latest_snapshot(show_status=True)

    def _load_latest_snapshot(self, *, show_status: bool) -> None:
        path = self._latest_snapshot_path()
        if not path:
            if show_status:
                self.status_label.setText("No snapshots found.")
            return
        try:
            graph = snapshot_io.read_snapshot(path)
        except Exception as exc:
            if show_status:
                self.status_label.setText(f"Snapshot load failed: {exc}")
            return
        self._snapshot_graph = graph
        self._set_active_graphs(graph, {})
        if show_status:
            self.status_label.setText(f"Snapshot loaded: {path.name}")
        self._update_mode_status(0, 0)

    def set_crash_view(self, enabled: bool) -> None:
        self._crash_view = bool(enabled)
        if self._crash_view:
            self._source = SOURCE_SNAPSHOT
            self.source_combo.blockSignals(True)
            self.source_combo.setCurrentText(SOURCE_SNAPSHOT)
            self.source_combo.blockSignals(False)
            self._load_crash_record()
            self._load_latest_snapshot(show_status=True)
        else:
            self._crash_record = None
            self._crash_node_id = None
            self._update_crash_actions()
        self._update_mode_status(0, 0)
        self._render_current_graph()

    def _load_crash_record(self) -> None:
        self._crash_record = crash_io.read_latest_crash(self._workspace_id())
        self._crash_node_id = None
        self._update_crash_actions()

    def _apply_crash_badge(self, graph: ArchitectureGraph) -> ArchitectureGraph:
        if not self._crash_view or not self._crash_record:
            return graph
        node_map = {node.node_id: node for node in graph.nodes}
        target_id = "system:app_ui"
        if target_id not in node_map:
            workspace_node = f"workspace:{self._workspace_id()}"
            if workspace_node in node_map:
                target_id = workspace_node
            elif graph.nodes:
                target_id = graph.nodes[0].node_id
            else:
                target_id = "system:app_ui"
        self._crash_node_id = target_id
        badge = _crash_badge_from_record(self._crash_record)
        if target_id in node_map:
            node = node_map[target_id]
            node_map[target_id] = Node(
                node_id=node.node_id,
                title=node.title,
                node_type=node.node_type,
                subgraph_id=node.subgraph_id,
                badges=list(node.badges) + [badge],
                severity_state=node.severity_state,
                checks=node.checks,
                spans=node.spans,
            )
            nodes = list(node_map.values())
        else:
            nodes = list(node_map.values())
            nodes.append(
                Node(
                    node_id=target_id,
                    title="app_ui",
                    node_type="System",
                    badges=[badge],
                )
            )
        return ArchitectureGraph(
            graph_id=graph.graph_id,
            title=graph.title,
            nodes=nodes,
            edges=graph.edges,
        )

    def _apply_diff_removed_nodes(self, graph: ArchitectureGraph) -> ArchitectureGraph:
        if not self._diff_mode or not self._diff_result or not self._diff_baseline_graph:
            return graph
        if not self._diff_result.nodes_removed:
            return graph
        baseline_map = {node.node_id: node for node in self._diff_baseline_graph.nodes}
        nodes = list(graph.nodes)
        existing_ids = {node.node_id for node in nodes}
        for node_id in sorted(self._diff_result.nodes_removed):
            if node_id in existing_ids:
                continue
            baseline = baseline_map.get(node_id)
            if not baseline:
                continue
            nodes.append(
                Node(
                    node_id=baseline.node_id,
                    title=f"Removed: {baseline.title}",
                    node_type=baseline.node_type,
                    subgraph_id=None,
                    badges=list(baseline.badges),
                    severity_state=baseline.severity_state,
                    checks=list(baseline.checks),
                    spans=list(baseline.spans),
                    metadata={**(baseline.metadata or {}), "diff_state": "removed"},
                )
            )
        return ArchitectureGraph(
            graph_id=graph.graph_id,
            title=graph.title,
            nodes=nodes,
            edges=graph.edges,
        )

    def _update_mode_status(self, total_nodes: int, shown_nodes: int) -> None:
        lens_title = self._lens_map.get(self._lens).title if self._lens in self._lens_map else self._lens
        live_state = "On" if self._live_enabled else "Off"
        diff_state = "On" if self._diff_mode else "Off"
        monitor_state = None
        if self._monitor_enabled:
            trace_id = str(self._monitor_active_trace_id or "")
            trace_text = trace_id[:8] if trace_id else "none"
            pin_state = " pinned" if self._monitor_trace_pinned else ""
            monitor_state = f"On ({trace_text}{pin_state})"
        filter_count = len(view_config.build_active_filter_chips(self._view_config))
        filter_count += sum(1 for value in self._diff_filters.values() if value)
        diff_counts = None
        if self._diff_mode and self._diff_result:
            diff_counts = (
                f"+{len(self._diff_result.nodes_added)} "
                f"-{len(self._diff_result.nodes_removed)} "
                f"Î”{len(self._diff_result.nodes_changed)}"
            )
        screen_label = f"Screen: {self._screen_context}" if self._screen_context else None
        bus_state = "Disconnected"
        active_spans = 0
        active_pulses = 0
        last_event = "n/a"
        if self._runtime_hub:
            bus_state = "Connected" if self._runtime_hub.bus_connected() else "Disconnected"
            active_spans = self._runtime_hub.active_span_count()
            last_event = self._runtime_hub.last_event_ts() or "n/a"
            active_pulses = self.scene.active_pulse_count() if self.scene else 0
        parts = [
            f"Source: {self._source}",
            f"Lens: {lens_title}",
            screen_label,
            f"Live: {live_state}",
            f"Diff: {diff_state}",
            f"Monitor: {monitor_state}" if monitor_state else None,
            f"Delta: {diff_counts}" if diff_counts else None,
            f"Bus: {bus_state}",
            f"Spans: {active_spans}",
            f"Last activity: {last_event}",
            f"Filters: {filter_count}",
        ]
        if self._live_enabled:
            parts.insert(6, f"Active pulses: {active_pulses}")
        if total_nodes > 0:
            parts.append(f"Showing: {shown_nodes}/{total_nodes}")
        if self._crash_view:
            parts.append(f"Crash View: {_format_crash_timestamp(self._crash_record)}")
        self.mode_status_label.setText(" | ".join([part for part in parts if part]))
        self._update_crash_actions()

    def _update_crash_actions(self) -> None:
        has_crash = bool(self._crash_record)
        self.crash_open_btn.setVisible(has_crash)
        self.crash_open_btn.setEnabled(has_crash)
        self.crash_clear_btn.setVisible(has_crash)
        self.crash_clear_btn.setEnabled(has_crash)

    def _open_crash_folder(self) -> None:
        path = crash_io.crash_dir(self._workspace_id())
        try:
            path.mkdir(parents=True, exist_ok=True)
            url = QtCore.QUrl.fromLocalFile(str(path.resolve()))
            QtGui.QDesktopServices.openUrl(url)
        except Exception:
            return

    def _clear_crash_record(self) -> None:
        crash_io.clear_latest_crash(self._workspace_id())
        self._crash_record = None
        self._crash_node_id = None
        self._update_mode_status(0, 0)
        self._render_current_graph()


# endregion NAV-20 CodeSeeScreen

# === [NAV-90] Module helpers (toggle/buttons/labels/filters/spans/badges) =====
# region NAV-90 Module helpers
# --- [NAV-90A] toggle/button UI helpers
def _style_from_label(label: str) -> str:
    for style, value in ICON_STYLE_LABELS.items():
        if value == label:
            return style
    return icon_pack.ICON_STYLE_AUTO


def _toggle_style() -> str:
    return (
        "QToolButton[codesee_toggle=\"true\"] {"
        " padding: 4px 8px; color: #e6e6e6; background: #323232;"
        " border: 1px solid #2b2b2b; border-radius: 4px; }"
        "QToolButton[codesee_toggle=\"true\"]:hover { background: #3a3a3a; }"
        "QToolButton[codesee_toggle=\"true\"]:checked {"
        " background: #3f3f3f; border: 1px solid #5a5a5a; color: #f0f0f0; }"
    )


def _make_toggle_button(label: str, handler: Callable[[], None]) -> QtWidgets.QToolButton:
    btn = QtWidgets.QToolButton()
    btn.setText(label)
    btn.setAutoRaise(False)
    btn.setCheckable(True)
    btn.toggled.connect(handler)
    return btn


def _apply_toggle_style(buttons: list[QtWidgets.QToolButton], style: str) -> None:
    for button in buttons:
        button.setProperty("codesee_toggle", True)
        button.setStyleSheet(style)


def _combo_action(label: str, combo: QtWidgets.QComboBox, *, parent: QtWidgets.QMenu) -> QtWidgets.QWidgetAction:
    container = QtWidgets.QWidget(parent)
    layout = QtWidgets.QHBoxLayout(container)
    layout.setContentsMargins(6, 2, 6, 2)
    layout.addWidget(QtWidgets.QLabel(label))
    layout.addWidget(combo, stretch=1)
    action = QtWidgets.QWidgetAction(parent)
    action.setDefaultWidget(container)
    return action


def _snapshot_label(entry: dict) -> str:
    timestamp = entry.get("timestamp") or entry.get("filename") or "snapshot"
    source = entry.get("source") or "Unknown"
    graph_id = entry.get("graph_id") or "graph"
    return f"{timestamp} | {source} | {graph_id}"


def _set_combo_by_data(combo: QtWidgets.QComboBox, value: Optional[str]) -> None:
    if value is None:
        return
    for idx in range(combo.count()):
        if combo.itemData(idx) == value:
            combo.setCurrentIndex(idx)
            return


def _format_active_total(active: int, total: int) -> str:
    return f"{int(active)} / {int(total)}"


def _facet_enabled_defaults_for_density(density: str) -> Dict[str, bool]:
    normalized = str(density or "").strip().lower()
    if normalized not in view_config.FACET_DENSITIES:
        normalized = "minimal"
    enabled = {key: False for key in view_config.FACET_KEYS}
    if normalized == "off":
        return enabled
    for key in ("deps", "activity"):
        enabled[key] = True
    if normalized in ("standard", "expanded", "debug"):
        for key in ("packs", "entry_points", "signals", "errors", "spans"):
            enabled[key] = True
    if normalized in ("expanded", "debug"):
        for key in ("runs", "logs"):
            enabled[key] = True
    if normalized == "debug":
        for key in view_config.FACET_KEYS:
            enabled[key] = True
    return enabled


def _event_matches_activity_mode(event: CodeSeeEvent, mode: str) -> bool:
    if mode in ("", "activity", "logs"):
        return True
    if mode == "errors":
        return event.severity in ("error", "crash", "failure") or event.kind in (EVENT_APP_ERROR, EVENT_APP_CRASH)
    if mode == "signals":
        return event.kind in (EVENT_BUS_REQUEST, EVENT_BUS_REPLY, EVENT_TEST_PULSE)
    if mode == "spans":
        return event.kind in (EVENT_SPAN_START, EVENT_SPAN_UPDATE, EVENT_SPAN_END)
    if mode == "runs":
        return event.kind in (EVENT_JOB_UPDATE, EVENT_SPAN_START, EVENT_SPAN_END)
    return True


def _span_rows_for_node(
    spans: list[SpanRecord],
    *,
    node_id: str,
    mode: str,
    limit: int,
) -> list[dict[str, str]]:
    if limit <= 0:
        return []
    rows: list[dict[str, str]] = []
    for span in reversed(spans):
        if span.node_id != node_id:
            continue
        if mode == "runs" and span.status not in ("active", "failed", "done", "success", "ok"):
            continue
        rows.append(
            {
                "when": f"{span.updated_ts:.2f}" if span.updated_ts else "",
                "type": f"span.{span.status}",
                "source": str(span.source_id or "runtime"),
                "detail": str(span.message or span.label or span.span_id),
            }
        )
        if len(rows) >= limit:
            break
    return rows

# --- [NAV-90B] badge keys + labels + filter summaries
def _badge_key_for_event(event: CodeSeeEvent) -> Optional[str]:
    if event.kind == EVENT_EXPECT_CHECK:
        if isinstance(event.payload, dict) and not event.payload.get("passed", True):
            return "expect.mismatch"
    if event.severity == "crash" or event.kind == EVENT_APP_CRASH:
        return "state.crash"
    if event.severity == "error" or event.kind == EVENT_APP_ERROR:
        return "state.error"
    if event.severity == "warn":
        return "state.warn"
    if event.kind == EVENT_JOB_UPDATE:
        return "state.warn"
    if event.kind in (EVENT_BUS_REQUEST, EVENT_BUS_REPLY):
        return "activity.muted"
    if event.kind == EVENT_APP_ACTIVITY:
        return "activity.muted"
    return None


def _event_color(event: CodeSeeEvent) -> QtGui.QColor:
    if event.severity == "crash":
        return QtGui.QColor("#111")
    if event.severity == "error":
        return QtGui.QColor("#c0392b")
    if event.severity == "failure":
        return QtGui.QColor("#7b3fb3")
    if event.severity == "warn":
        return QtGui.QColor("#d68910")
    return QtGui.QColor("#4c6ef5")


def _category_keys() -> list[str]:
    return [
        "Workspace",
        "Pack",
        "Block",
        "Subcomponent",
        "Artifact",
        "Lab",
        "Extension",
        "Plugin",
        "Topic",
        "Unit",
        "Lesson",
        "Activity",
        "System",
    ]


def _badge_layer_labels() -> Dict[str, str]:
    return {
        "health": "Health",
        "correctness": "Correctness",
        "connectivity": "Connectivity",
        "policy": "Policy",
        "perf": "Performance",
        "activity": "Activity",
    }


def _quick_filter_labels() -> Dict[str, str]:
    return {
        "only_errors": "Only errors",
        "only_failures": "Only failures",
        "only_expecting": "Only expecting",
        "only_mismatches": "Only mismatches",
        "only_active": "Only active",
        "only_stuck": "Only stuck",
    }


def _diff_filter_labels() -> Dict[str, str]:
    return {
        "only_added": "Only added",
        "only_removed": "Only removed",
        "only_changed": "Only changed",
    }


def _quick_filter_summary(config: view_config.ViewConfig) -> str:
    labels = []
    for key, label in _quick_filter_labels().items():
        if config.quick_filters.get(key):
            labels.append(label.replace("Only ", "").strip())
    return " + ".join(labels)


def _diff_filter_summary(filters: Dict[str, bool]) -> str:
    labels = []
    for key, label in _diff_filter_labels().items():
        if filters.get(key):
            labels.append(label.replace("Only ", "").strip())
    return " + ".join(labels)


# --- [NAV-90C] filters + pulse topic enablement
def _pulse_topic_enabled(settings: view_config.PulseSettings, kind: str) -> bool:
    enabled = getattr(settings, "topic_enabled", None)
    if not isinstance(enabled, dict):
        return True
    if kind not in enabled:
        return True
    return bool(enabled.get(kind, True))


def _category_visible(node: Node, categories: Dict[str, bool]) -> bool:
    node_type = (node.node_type or "").strip()
    if node_type in categories:
        return categories.get(node_type, True)
    return True


def _passes_quick_filters(
    node: Node,
    quick_filters: Dict[str, bool],
    *,
    now: float,
    stuck_threshold: int,
) -> bool:
    if not any(quick_filters.values()):
        return True
    badges = node.badges or []
    keys = {badge.key for badge in badges}
    severity = node.effective_severity()
    if quick_filters.get("only_errors"):
        has_error = any(key.startswith("state.error") for key in keys) or severity == "error"
        if not has_error:
            return False
    if quick_filters.get("only_failures"):
        has_failure = "probe.fail" in keys or severity in ("probe.fail", "correctness", "failure")
        if not has_failure:
            return False
    if quick_filters.get("only_expecting"):
        if "expect.value" not in keys:
            return False
    if quick_filters.get("only_mismatches"):
        if not _node_has_mismatch(node):
            return False
    if quick_filters.get("only_active"):
        if not _node_has_active_span(node):
            return False
    if quick_filters.get("only_stuck"):
        if not _node_has_stuck_span(node, now, stuck_threshold):
            return False
    return True


def _passes_diff_filters(
    node_id: str,
    diff_result: DiffResult,
    diff_filters: Dict[str, bool],
) -> bool:
    if not any(diff_filters.values()):
        return True
    if diff_filters.get("only_added") and node_id in diff_result.nodes_added:
        return True
    if diff_filters.get("only_removed") and node_id in diff_result.nodes_removed:
        return True
    if diff_filters.get("only_changed") and node_id in diff_result.nodes_changed:
        return True
    return False


def _bus_nodes_present(graph: ArchitectureGraph) -> bool:
    for node in graph.nodes:
        if node.node_type != "System":
            continue
        token = f"{node.node_id} {node.title}".lower()
        if "bus" in token:
            return True
    return False


def _node_has_mismatch(node: Node) -> bool:
    for check in node.checks or []:
        if not check.passed:
            return True
    return False


def _ext_nodes(node: Node) -> bool:
    node_type = (node.node_type or "").strip()
    return node_type in (
        "Workspace",
        "Pack",
        "Block",
        "Subcomponent",
        "Artifact",
        "Lab",
        "Extension",
        "Plugin",
        "System",
    )


def _ext_edges(edge, src: Node, dst: Node) -> bool:
    return edge.kind in ("depends", "provides", "consumes", "loads", "contains")


# --- [NAV-90D] span helpers
def _node_has_active_span(node: Node) -> bool:
    for span in node.spans or []:
        if span.status == "active":
            return True
    return False


def _node_has_stuck_span(node: Node, now: float, stuck_threshold: int) -> bool:
    for span in node.spans or []:
        if _span_is_stuck(span, now, stuck_threshold):
            return True
    return False


def _span_fallback_node_id(graph: ArchitectureGraph, workspace_id: str) -> Optional[str]:
    node_ids = {node.node_id for node in graph.nodes}
    if "system:content_system" in node_ids:
        return "system:content_system"
    if "system:app_ui" in node_ids:
        return "system:app_ui"
    workspace_node = f"workspace:{workspace_id}"
    if workspace_node in node_ids:
        return workspace_node
    if graph.nodes:
        return graph.nodes[0].node_id
    return None


# --- [NAV-90E] badge builders + crash helpers
def _badge_for_check(check: EVACheck) -> Badge:
    return Badge(
        key="expect.mismatch",
        rail="bottom",
        title="Mismatch",
        summary=check.message or "Expected vs actual mismatch.",
        detail=str(check.context) if check.context else None,
        severity="failure",
        timestamp=str(check.ts),
    )


def _crash_badge_from_record(record: dict) -> Badge:
    message = str(record.get("message") or "Crash detected.")
    exc_type = str(record.get("exception_type") or "Crash")
    summary = f"{exc_type}: {message}"
    timestamp = str(record.get("ts") or "")
    return Badge(
        key="state.crash",
        rail="top",
        title="Crash",
        summary=summary,
        detail=str(record.get("where") or "startup"),
        severity="crash",
        timestamp=timestamp,
    )


def _format_crash_timestamp(record: Optional[dict]) -> str:
    if not isinstance(record, dict):
        return "n/a"
    ts = record.get("ts")
    if isinstance(ts, (int, float)):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    return "n/a"


def _merge_span_badges(
    badges: list[Badge],
    spans: list[SpanRecord],
    now: float,
    threshold: int,
) -> list[Badge]:
    if not spans:
        return badges
    existing_keys = {badge.key for badge in badges}
    active = [span for span in spans if span.status == "active"]
    stuck = [span for span in active if _span_is_stuck(span, now, threshold)]
    failed = [span for span in spans if span.status == "failed"]
    extras: list[Badge] = []
    if active and "activity.active" not in existing_keys:
        extras.append(
            Badge(
                key="activity.active",
                rail="top",
                title="Active",
                summary=f"{len(active)} active span(s)",
                detail=_span_titles(active, limit=3),
                severity="normal",
            )
        )
    if stuck and "activity.stuck" not in existing_keys:
        extras.append(
            Badge(
                key="activity.stuck",
                rail="top",
                title="Stuck",
                summary=f"{len(stuck)} stuck span(s)",
                detail=_span_titles(stuck, limit=3),
                severity="warn",
            )
        )
    if failed and "state.error" not in existing_keys:
        extras.append(
            Badge(
                key="state.error",
                rail="top",
                title="Span Failed",
                summary=f"{len(failed)} span(s) failed",
                detail=_span_titles(failed, limit=3),
                severity="error",
            )
        )
    return badges + extras


def _span_titles(spans: list[SpanRecord], limit: int = 3) -> Optional[str]:
    titles = [span.label for span in spans if span.label]
    if not titles:
        return None
    sliced = titles[:limit]
    if len(titles) > limit:
        sliced.append("...")
    return ", ".join(sliced)


def _active_span_node_ids(spans: list[SpanRecord], limit: int = 4) -> list[str]:
    seen = set()
    nodes: list[str] = []
    for span in spans:
        if span.node_id and span.node_id not in seen:
            nodes.append(span.node_id)
            seen.add(span.node_id)
        if len(nodes) >= limit:
            break
    return nodes


# endregion NAV-90 Module helpers

# === [NAV-99] Smoke test entrypoints =========================================
def run_pulse_smoke_test() -> None:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    hub = CodeSeeRuntimeHub()
    screen = CodeSeeScreen(
        on_back=lambda: None,
        workspace_info_provider=lambda: {"id": "default"},
        runtime_hub=hub,
        allow_detach=False,
    )
    screen.live_toggle.setChecked(True)
    screen._pulse_settings.travel_speed_px_per_s = 200
    result = {"events": 0, "signals": 0, "activity_before": 0}

    def _emit() -> None:
        hub.publish_test_pulse(node_ids=["module.ui", "module.runtime_bus"])

    def _check_before_rebuild() -> None:
        result["activity_before"] = (
            screen.scene.pulse_state_count() + screen.scene.signals_active_count()
        )

    def _rebuild() -> None:
        screen._set_active_graphs(screen._demo_root, screen._demo_subgraphs)

    def _check() -> None:
        result["events"] = hub.event_count()
        result["signals"] = screen.scene.signals_active_count()
        app.quit()

    QtCore.QTimer.singleShot(80, _emit)
    QtCore.QTimer.singleShot(120, _check_before_rebuild)
    QtCore.QTimer.singleShot(160, _rebuild)
    QtCore.QTimer.singleShot(260, _check)
    QtCore.QTimer.singleShot(1500, app.quit)
    app.exec()
    if result["events"] <= 0:
        raise AssertionError("expected at least one event")
    if result["activity_before"] <= 0:
        raise AssertionError("expected signal activity before rebuild")
