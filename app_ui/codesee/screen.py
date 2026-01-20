from __future__ import annotations

import base64
import functools
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PyQt6 import QtCore, QtGui, QtSvg, QtWidgets

from app_ui import config as ui_config
from app_ui.widgets.app_header import AppHeader
from app_ui.widgets.workspace_selector import WorkspaceSelector

from . import crash_io, harness, icon_pack, layout_store, snapshot_index, snapshot_io, view_config
from .badges import Badge, badge_from_key, sort_by_priority
from .canvas.items import clear_icon_cache
from .canvas.scene import GraphScene
from .canvas.view import GraphView
from .collectors.atlas_builder import build_atlas_graph
from .collectors.base import CollectorContext
from .demo_graphs import build_demo_root_graph, build_demo_subgraphs
from .diff import DiffResult, NodeChange, diff_snapshots
from .expectations import EVACheck, check_from_dict
from .graph_model import ArchitectureGraph, Node
from .lenses import LENS_ATLAS, LENS_BUS, LENS_CONTENT, LENS_PLATFORM, LensSpec, get_lens, get_lenses
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
from .runtime.hub import CodeSeeRuntimeHub
from app_ui import ui_scale
from app_ui import versioning

DEFAULT_LENS = LENS_ATLAS
LENS_EXT = "extensibility"
SOURCE_DEMO = "Demo"
SOURCE_ATLAS = "Atlas"
SOURCE_SNAPSHOT = "Snapshot (Latest)"
ICON_STYLE_LABELS = {
    icon_pack.ICON_STYLE_AUTO: "Auto",
    icon_pack.ICON_STYLE_COLOR: "Color",
    icon_pack.ICON_STYLE_MONO: "Mono",
}
_LENS_ICON_CACHE: Dict[tuple[str, str, int, str], QtGui.QPixmap] = {}


def _lens_palette_lens_ids() -> list[str]:
    return [LENS_ATLAS, LENS_PLATFORM, LENS_CONTENT, LENS_BUS, LENS_EXT]


def _lens_tile_spec() -> list[dict[str, str]]:
    return [
        {"id": LENS_EXT, "title": "Deps", "icon": "probe.pass"},
        {"id": LENS_CONTENT, "title": "Content", "icon": "expect.value"},
        {"id": LENS_ATLAS, "title": "Atlas", "icon": "conn.offline"},
        {"id": LENS_PLATFORM, "title": "Platform", "icon": "state.warn"},
        {"id": LENS_BUS, "title": "Bus", "icon": "perf.slow"},
    ]


def _filter_lens_tiles(query: str, tiles: list[dict[str, str]]) -> list[dict[str, str]]:
    if not query:
        return list(tiles)
    needle = query.strip().lower()
    if not needle:
        return list(tiles)
    filtered = []
    for tile in tiles:
        title = tile.get("title", "").lower()
        lens_id = tile.get("id", "").lower()
        if needle in title or needle in lens_id:
            filtered.append(tile)
    return filtered


def _fallback_lens_pixmap(size: int, tint: Optional[QtGui.QColor]) -> QtGui.QPixmap:
    tint_key = tint.name() if tint else ""
    cache_key = ("__fallback__", "color", int(size), tint_key)
    cached = _LENS_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    side = max(1, int(size))
    pixmap = QtGui.QPixmap(side, side)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    color = tint if tint is not None else QtGui.QColor("#8aa0b5")
    pen = QtGui.QPen(color)
    pen.setWidth(max(1, int(side * 0.08)))
    painter.setPen(pen)
    margin = max(2, int(side * 0.18))
    rect = pixmap.rect().adjusted(margin, margin, -margin, -margin)
    radius = max(2, int(side * 0.18))
    painter.drawRoundedRect(rect, radius, radius)
    painter.end()
    _LENS_ICON_CACHE[cache_key] = pixmap
    return pixmap


def _lens_palette_icon_pixmap(
    icon_key: str, style: str, size: int, tint: Optional[QtGui.QColor]
) -> Optional[QtGui.QPixmap]:
    try:
        path = icon_pack.resolve_icon_path(icon_key, style)
    except Exception:
        return _fallback_lens_pixmap(size, tint)
    if not path:
        return _fallback_lens_pixmap(size, tint)
    tint_key = tint.name() if tint else ""
    cache_key = (str(path), style, int(size), tint_key)
    cached = _LENS_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    side = max(1, int(size))
    pixmap = QtGui.QPixmap(side, side)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    try:
        renderer = QtSvg.QSvgRenderer(str(path))
        if not renderer.isValid():
            return _fallback_lens_pixmap(size, tint)
        painter = QtGui.QPainter(pixmap)
        renderer.render(painter)
        if tint is not None:
            painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), tint)
        painter.end()
    except Exception:
        return _fallback_lens_pixmap(size, tint)
    _LENS_ICON_CACHE[cache_key] = pixmap
    return pixmap


class LensPaletteWidget(QtWidgets.QFrame):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._lens_combo: Optional[QtWidgets.QComboBox] = None
        self._bound_model: Optional[QtCore.QAbstractItemModel] = None
        self._refresh_scheduled = False
        self._refreshing = False
        self._pending_refresh_reason = ""
        self._model_connect_count = 0
        self._dbg_seen: set[str] = set()
        self._on_select: Optional[Callable[[str], None]] = None
        self._on_close: Optional[Callable[[], None]] = None
        self._on_pin: Optional[Callable[[bool], None]] = None
        self._pinned = False
        self._expanded = False
        self._active_lens_id = ""
        self._recent: list[str] = []
        self._tile_buttons: Dict[str, QtWidgets.QToolButton] = {}
        self._tile_widgets: list[QtWidgets.QToolButton] = []

        self.setObjectName("codeseeLensPalette")
        self.setWindowFlags(QtCore.Qt.WindowType.Widget)
        self.setStyleSheet(
            "QFrame#codeseeLensPalette { background: #1b1f27; border: 1px solid #2a2f38; border-radius: 12px; }"
            "QLabel { color: #cfd8dc; }"
            "QLineEdit { background: #252a33; color: #cfd8dc; border: 1px solid #2f3540; border-radius: 8px; padding: 6px 8px; }"
            "QToolButton#lensPalettePin { color: #cfd8dc; padding: 2px 6px; }"
            "QToolButton#lensPalettePin:checked { background: #2b3b55; border-radius: 4px; }"
            "QToolButton[lens_tile=\"true\"] { color: #cfd8dc; background: transparent; border: 1px solid transparent; border-radius: 10px; padding: 6px; }"
            "QToolButton[lens_tile=\"true\"]:hover { border: 1px solid #2f3540; background: #222733; }"
            "QToolButton[lens_tile=\"true\"]:checked { border: 1px solid #3b5bdb; background: #222733; color: #ffffff; }"
        )
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.MinimumExpanding,
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header_row = QtWidgets.QHBoxLayout()
        header_label = QtWidgets.QLabel("Lenses")
        header_row.addWidget(header_label)
        header_row.addStretch()
        self._close_btn = QtWidgets.QToolButton()
        self._close_btn.setText("×")
        self._close_btn.setToolTip("Close")
        self._close_btn.setAutoRaise(True)
        self._close_btn.clicked.connect(self._emit_close)
        header_row.addWidget(self._close_btn)
        self._pin_btn = QtWidgets.QToolButton()
        self._pin_btn.setObjectName("lensPalettePin")
        self._pin_btn.setText("Pin")
        self._pin_btn.setToolTip("Pin palette")
        self._pin_btn.setCheckable(True)
        self._pin_btn.toggled.connect(self._emit_pin)
        header_row.addWidget(self._pin_btn)
        layout.addLayout(header_row)

        search_row = QtWidgets.QHBoxLayout()
        self._search = QtWidgets.QLineEdit()
        self._search.setPlaceholderText("Search")
        self._search.textChanged.connect(lambda: self.request_refresh("search"))
        self._search.returnPressed.connect(lambda: self.request_refresh("search_enter"))
        search_icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogContentsView)
        self._search.addAction(search_icon, QtWidgets.QLineEdit.ActionPosition.LeadingPosition)
        search_row.addWidget(self._search)
        search_btn = QtWidgets.QToolButton()
        search_btn.setIcon(search_icon)
        search_btn.setToolTip("Search lenses")
        search_btn.setAutoRaise(True)
        search_btn.clicked.connect(lambda: self.request_refresh("search_button"))
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)

        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color: #9aa4b2; padding: 2px 4px;")
        self._status.setMinimumHeight(int(ui_scale.scale_px(18)))
        layout.addWidget(self._status)

        self._empty_banner = QtWidgets.QLabel("")
        self._empty_banner.setStyleSheet("color: #9aa4b2; padding: 2px 4px;")
        self._empty_banner.setVisible(False)
        layout.addWidget(self._empty_banner)

        self._grid_container = QtWidgets.QWidget()
        self._grid_container.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self._grid_container.setMinimumHeight(int(ui_scale.scale_px(160)))
        self._grid = QtWidgets.QGridLayout(self._grid_container)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)

        empty_state = QtWidgets.QWidget()
        empty_layout = QtWidgets.QVBoxLayout(empty_state)
        empty_layout.setContentsMargins(8, 20, 8, 20)
        empty_layout.setSpacing(6)
        empty_layout.addStretch()
        self._empty_title = QtWidgets.QLabel("No results")
        self._empty_title.setStyleSheet("color: #cfd8dc; font-weight: 600;")
        empty_layout.addWidget(self._empty_title, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        self._empty_subtitle = QtWidgets.QLabel("Try a different search")
        self._empty_subtitle.setStyleSheet("color: #9aa4b2;")
        empty_layout.addWidget(self._empty_subtitle, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addStretch()

        stack_widget = QtWidgets.QWidget()
        stack_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self._stack = QtWidgets.QStackedLayout(stack_widget)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._grid_container)
        self._stack.addWidget(empty_state)

        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(stack_widget)
        layout.addWidget(self._scroll)
        layout.setStretch(layout.indexOf(self._scroll), 1)

        footer_row = QtWidgets.QHBoxLayout()
        self._recent_btn = QtWidgets.QToolButton()
        self._recent_btn.setText("Recent")
        self._recent_btn.setToolTip("Recently used lenses")
        self._recent_btn.clicked.connect(self._show_recent_menu)
        footer_row.addWidget(self._recent_btn)
        footer_row.addStretch()
        self._more_btn = QtWidgets.QToolButton()
        self._more_btn.setText("More… >")
        self._more_btn.clicked.connect(self._toggle_expanded)
        footer_row.addWidget(self._more_btn)
        layout.addLayout(footer_row)

        self._apply_sizing()

    def set_lens_combo(self, combo: QtWidgets.QComboBox) -> None:
        self._lens_combo = combo
        self._bind_model_signals()
        self.request_refresh("set_lens_combo")

    def set_on_select(self, callback: Callable[[str], None]) -> None:
        self._on_select = callback

    def set_on_close(self, callback: Callable[[], None]) -> None:
        self._on_close = callback

    def set_on_pin(self, callback: Callable[[bool], None]) -> None:
        self._on_pin = callback

    def set_recent(self, recent: list[str]) -> None:
        self._recent = list(recent or [])

    def set_active_lens(self, lens_id: str) -> None:
        self._active_lens_id = lens_id or ""
        for tile_id, button in self._tile_buttons.items():
            button.setChecked(tile_id == self._active_lens_id)
        if self._active_lens_id:
            self._dbg_once(f"active:{self._active_lens_id}", f"palette active lens={self._active_lens_id}")

    def set_pinned(self, pinned: bool) -> None:
        self._pinned = bool(pinned)
        # Prevent recursive pin toggles when syncing state programmatically.
        blocker = QtCore.QSignalBlocker(self._pin_btn)
        self._pin_btn.setChecked(self._pinned)
        del blocker
        self._apply_sizing()
        self._dbg_once(f"pin:{self._pinned}", f"palette pin={self._pinned}")

    def is_pinned(self) -> bool:
        return self._pinned

    def request_refresh(self, reason: str = "signal") -> None:
        if self._refreshing or self._refresh_scheduled:
            self._pending_refresh_reason = reason
            return
        self._refresh_scheduled = True
        self._pending_refresh_reason = reason
        QtCore.QTimer.singleShot(0, self._refresh_once)

    def refresh(self) -> None:
        self.request_refresh("explicit")

    def _refresh_once(self) -> None:
        if self._refreshing:
            return
        self._refresh_scheduled = False
        self._refreshing = True
        try:
            self._refresh_impl()
        finally:
            self._refreshing = False

    def _refresh_impl(self) -> None:
        if not self._lens_combo:
            return
        entries = self._lens_entries()
        query = self._search.text() if self._search else ""
        tiles = _filter_lens_tiles(query, entries)
        query_key = query.strip()
        if query_key:
            self._dbg_once(
                f"query:{query_key}",
                f"palette query={query_key!r} matches={len(tiles)}",
            )
        else:
            self._dbg_once("query:empty", f"palette query='' matches={len(tiles)}")
        self._update_status(entries, tiles, query)
        self._clear_grid()
        if not tiles:
            self._show_empty(entries, query)
            return
        self._empty_banner.setVisible(False)
        self._stack.setCurrentIndex(0)
        columns = 3
        icon_style = icon_pack.ICON_STYLE_MONO
        icon_size = int(ui_scale.scale_px(26))
        tint = QtGui.QColor("#86b7ff")
        row = 0
        col = 0
        for entry in tiles:
            lens_id = entry.get("id") or ""
            title = entry.get("title") or lens_id
            icon_key = entry.get("icon") or "probe.pass"
            button = QtWidgets.QToolButton(self._grid_container)
            button.setProperty("lens_tile", True)
            button.setText(title)
            button.setToolButtonStyle(
                QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon
            )
            button.setCheckable(True)
            button.setAutoRaise(False)
            button.setIconSize(QtCore.QSize(icon_size, icon_size))
            button.setFixedSize(
                int(ui_scale.scale_px(92)),
                int(ui_scale.scale_px(76)),
            )
            pixmap = _lens_palette_icon_pixmap(icon_key, icon_style, icon_size, tint)
            if pixmap:
                button.setIcon(QtGui.QIcon(pixmap))
            button.clicked.connect(
                functools.partial(self._emit_select, lens_id)
            )
            self._grid.addWidget(button, row, col)
            self._tile_buttons[lens_id] = button
            self._tile_widgets.append(button)
            col += 1
            if col >= columns:
                col = 0
                row += 1
        self.set_active_lens(self._active_lens_id)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self._dbg_once("palette_open", "palette opened")
        self.request_refresh("show")

    def _lens_entries(self) -> list[dict[str, str]]:
        if not self._lens_combo:
            return []
        tile_icon_map = {tile.get("id"): tile.get("icon") for tile in _lens_tile_spec()}
        entries: list[dict[str, str]] = []
        for idx in range(self._lens_combo.count()):
            lens_id = self._lens_combo.itemData(idx)
            title = self._lens_combo.itemText(idx)
            lens_id_str = str(lens_id) if isinstance(lens_id, str) and lens_id else ""
            title_str = str(title) if title else lens_id_str
            entry_id = lens_id_str or title_str or f"lens-{idx}"
            entries.append(
                {
                    "id": entry_id,
                    "title": title_str or entry_id,
                    "icon": tile_icon_map.get(entry_id) or "probe.pass",
                }
            )
        return entries

    def _on_model_changed(self, *_args: object) -> None:
        self.request_refresh("model_changed")

    def _disconnect_model_signals(self, model: QtCore.QAbstractItemModel) -> None:
        for signal in (
            model.modelReset,
            model.rowsInserted,
            model.rowsRemoved,
            model.dataChanged,
        ):
            try:
                signal.disconnect(self._on_model_changed)
            except TypeError:
                pass

    def _bind_model_signals(self) -> None:
        if not self._lens_combo:
            return
        model = self._lens_combo.model()
        if model is None:
            return
        if model is self._bound_model:
            return
        if self._bound_model is not None:
            self._disconnect_model_signals(self._bound_model)
        self._bound_model = model
        model.modelReset.connect(self._on_model_changed)
        model.rowsInserted.connect(self._on_model_changed)
        model.rowsRemoved.connect(self._on_model_changed)
        model.dataChanged.connect(self._on_model_changed)
        self._model_connect_count += 1
        self._dbg_once(
            f"model_connect:{self._model_connect_count}",
            f"palette model connected count={self._model_connect_count}",
        )

    def _update_status(self, entries: list[dict[str, str]], tiles: list[dict[str, str]], query: str) -> None:
        q = query.strip()
        if not entries:
            self._status.setText("No lenses available (try Refresh)")
        elif q and not tiles:
            self._status.setText(f'No results for "{q}" (Lenses: {len(entries)})')
        else:
            self._status.setText(f"Lenses: {len(entries)} | Matches: {len(tiles)}")

    def _show_empty(self, entries: list[dict[str, str]], query: str) -> None:
        if not entries:
            self._empty_title.setText("No lenses available")
            self._empty_subtitle.setText("Try Refresh")
            self._empty_banner.setText("No lenses available")
        elif query.strip():
            self._empty_title.setText("No results")
            self._empty_subtitle.setText(f'No results for "{query.strip()}"')
            self._empty_banner.setText(f'No results for "{query.strip()}"')
        else:
            self._empty_title.setText("No results")
            self._empty_subtitle.setText("Try a different search")
            self._empty_banner.setText("No lenses to show")
        self._empty_banner.setVisible(True)
        self._stack.setCurrentIndex(1)

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._tile_buttons.clear()
        self._tile_widgets.clear()

    def _emit_select(self, lens_id: str) -> None:
        if self._on_select:
            self._on_select(lens_id)

    def _emit_close(self) -> None:
        if self._on_close:
            self._on_close()

    def _emit_pin(self, checked: bool) -> None:
        if self._on_pin:
            self._on_pin(bool(checked))

    def _toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self._more_btn.setText("Less" if self._expanded else "More… >")
        self._apply_sizing()
        self._dbg_once(f"expanded:{self._expanded}", f"palette expanded={self._expanded}")

    def _debug_enabled(self) -> bool:
        try:
            return os.environ.get("PHYSICSLAB_CODESEE_DEBUG", "0") == "1"
        except Exception:
            return False

    def _dbg(self, message: str) -> None:
        if not self._debug_enabled():
            return
        try:
            print(f"[codesee.lens_palette] {message}")
        except Exception:
            return

    def _dbg_once(self, key: str, message: str) -> None:
        if key in self._dbg_seen:
            return
        self._dbg_seen.add(key)
        self._dbg(message)

    def _apply_sizing(self) -> None:
        base = 260 if not self._expanded else 420
        min_height = int(ui_scale.scale_px(base))
        self.setMinimumHeight(min_height)
        if self._pinned:
            self.setMaximumHeight(16777215)
        else:
            self.setMaximumHeight(min_height)
        scroll_min = 160 if not self._expanded else 280
        self._scroll.setMinimumHeight(int(ui_scale.scale_px(scroll_min)))

    def _show_recent_menu(self) -> None:
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("QMenu { background: #1b1f27; color: #cfd8dc; }")
        added = False
        for lens_id in self._recent:
            label = self._label_for_id(lens_id)
            action = menu.addAction(label)
            action.triggered.connect(
                functools.partial(self._emit_select, lens_id)
            )
            added = True
        if not added:
            action = menu.addAction("No recent lenses")
            action.setEnabled(False)
        menu.exec(self._recent_btn.mapToGlobal(QtCore.QPoint(0, 24)))

    def _label_for_id(self, lens_id: str) -> str:
        if not self._lens_combo:
            return lens_id
        for idx in range(self._lens_combo.count()):
            if self._lens_combo.itemData(idx) == lens_id:
                return self._lens_combo.itemText(idx) or lens_id
        return lens_id

    def _log(self, message: str) -> None:
        self._dbg(message)


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
        self._build_info = versioning.get_build_info()
        palette_state = view_config.load_lens_palette_state(self._workspace_id())
        self._lens_palette_pinned = bool(palette_state.get("pinned", False))
        self._lens_palette_recent = list(palette_state.get("recent", []))
        self._lens_palette: Optional[LensPaletteWidget] = None
        self._lens_palette_visible = bool(palette_state.get("palette_visible", False))
        self._lens_palette_event_filter_installed = False
        if self._runtime_hub:
            self._runtime_hub.set_workspace_id(self._workspace_id())

        self._demo_root = build_demo_root_graph()
        self._demo_subgraphs = build_demo_subgraphs()
        self._atlas_root: Optional[ArchitectureGraph] = None
        self._atlas_subgraphs: Dict[str, ArchitectureGraph] = {}
        self._snapshot_graph: Optional[ArchitectureGraph] = None

        self._active_root: Optional[ArchitectureGraph] = self._demo_root
        self._active_subgraphs: Dict[str, ArchitectureGraph] = self._demo_subgraphs
        self._source = SOURCE_SNAPSHOT if self._safe_mode else SOURCE_DEMO
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
        self._dock_container = QtWidgets.QWidget()
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
        self.source_combo.setCurrentText(self._source)
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
        toggle_style = _toggle_style()
        _apply_toggle_style([self.live_toggle], toggle_style)
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
        self._dock_save_timer = QtCore.QTimer(self)
        self._dock_save_timer.setSingleShot(True)
        self._dock_save_timer.timeout.connect(self._persist_lens_palette_dock_state)

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
            on_status_badges=self._show_status_menu,
            icon_style=self._resolved_icon_style(),
            node_theme=self._node_theme,
        )
        self.scene.set_reduced_motion(self._reduced_motion)
        self.view = GraphView(self.scene)
        self.view.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self.view, stretch=1)

        if not self._dock_host_external:
            self._dock_host.setCentralWidget(self._dock_container)
            outer_layout = QtWidgets.QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)
            outer_layout.setSpacing(0)
            outer_layout.addWidget(self._dock_host)

        ui_scale.register_listener(self._on_ui_scale_changed)
        self._apply_density(ui_scale.get_config())
        self._refresh_snapshot_history()
        self._sync_view_controls()
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
        self._diff_mode = False
        self._diff_result = None
        self._diff_baseline_graph = None
        self._diff_compare_graph = None
        self._diff_filters = {key: False for key in self._diff_filters}
        self._live_enabled = bool(self._view_config.live_enabled)
        self._events_by_node.clear()
        self._overlay_badges.clear()
        self._overlay_checks.clear()
        if self._crash_view:
            self._load_crash_record()
        self._sync_view_controls()
        self.scene.set_icon_style(self._resolved_icon_style())
        self.scene.set_node_theme(self._node_theme)
        self.scene.set_badge_layers(self._view_config.show_badge_layers)
        self._refresh_snapshot_history()
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
        self._render_graph_id = graph_to_render.graph_id
        positions = layout_store.load_positions(self._workspace_id(), self._lens, self._render_graph_id)
        overlay_graph = self._apply_runtime_overlay(graph_to_render)
        overlay_graph = self._apply_expectation_badges(overlay_graph)
        overlay_graph = self._apply_span_overlay(overlay_graph)
        overlay_graph = self._apply_crash_badge(overlay_graph)
        overlay_graph = self._apply_diff_removed_nodes(overlay_graph)
        total_nodes = len(overlay_graph.nodes)
        filtered = self._filtered_graph(overlay_graph)
        shown_nodes = len(filtered.nodes)
        empty_message = None
        if self._lens == LENS_BUS and not _bus_nodes_present(graph_to_render):
            empty_message = "No bus nodes found for this graph."
            filtered = ArchitectureGraph(
                graph_id=filtered.graph_id,
                title=filtered.title,
                nodes=[],
                edges=[],
            )
        if empty_message is None and shown_nodes == 0 and self._filters_active():
            empty_message = "No nodes match the current filters."
        self._update_filter_status(total_nodes, shown_nodes)
        self._update_mode_status(total_nodes, shown_nodes)
        self.scene.set_empty_message(empty_message)
        self.scene.build_graph(filtered, positions, diff_result=diff_result)
        self.scene.set_icon_style(self._resolved_icon_style())
        self.scene.set_badge_layers(self._view_config.show_badge_layers)
        self._update_span_tints(filtered)
        self._update_debug_status()
        self._ensure_status_timer()

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

    def _on_source_changed(self, value: str) -> None:
        if value == self._source:
            return
        self._save_layout()
        self._source = value
        self._update_action_state()
        if value == SOURCE_DEMO:
            self._set_active_graphs(self._demo_root, self._demo_subgraphs)
            self.status_label.setText("")
            return
        if value == SOURCE_ATLAS:
            self._build_atlas()
            return
        if value == SOURCE_SNAPSHOT:
            self._load_latest_snapshot(show_status=True)

    def _set_active_graphs(
        self,
        root: ArchitectureGraph,
        subgraphs: Dict[str, ArchitectureGraph],
    ) -> None:
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
        self.live_toggle.blockSignals(True)
        self.live_toggle.setChecked(self._live_enabled)
        self.live_toggle.blockSignals(False)
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

    def _ensure_lens_palette(self) -> None:
        if self._lens_palette is not None:
            return
        palette = LensPaletteWidget(self)
        palette.set_lens_combo(self.lens_combo)
        palette.set_on_select(self._select_lens_from_palette)
        palette.set_on_close(self._hide_lens_palette)
        palette.set_on_pin(self._set_lens_palette_pinned)
        palette.set_recent(self._lens_palette_recent)
        palette.set_active_lens(self._lens)
        palette.set_pinned(self._lens_palette_pinned)
        self._lens_palette = palette
        self._ensure_lens_palette_dock()
        if self._lens_palette:
            self._lens_palette.refresh()

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
        )
        dock.setTitleBarWidget(QtWidgets.QWidget(dock))
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
        return

    def _toggle_lens_palette_expanded(self) -> None:
        return

    def _update_lens_palette_sizing(self) -> None:
        return

    def _show_recent_lenses_menu(self) -> None:
        return

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
        self._schedule_lens_palette_dock_save()

    def _schedule_lens_palette_dock_save(self) -> None:
        if self._dock_save_timer:
            self._dock_save_timer.start(350)

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

    def _show_lens_palette(self) -> None:
        self._ensure_lens_palette()
        self._ensure_lens_palette_dock()
        if not self._lens_palette_dock:
            return
        self._rebuild_lens_tiles()
        self._apply_lens_palette_flags()
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
            if self._lens_palette_visible and not self._lens_palette_pinned:
                self._position_lens_palette()
        if self._lens_palette_pinned and not self._lens_palette_visible:
            self._show_lens_palette()
        self._schedule_lens_palette_dock_save()

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
        if self._lens_palette_dock and obj is self._lens_palette_dock:
            if event.type() == QtCore.QEvent.Type.Hide:
                self._lens_palette_visible = False
                self.lens_palette_btn.setChecked(False)
                self._remove_lens_palette_event_filter()
        if (
            self._lens_palette_visible
            and not self._lens_palette_pinned
            and event.type() == QtCore.QEvent.Type.MouseButtonPress
        ):
            mouse_event = event  # type: ignore[assignment]
            global_pos = None
            if hasattr(mouse_event, "globalPosition"):
                global_pos = mouse_event.globalPosition().toPoint()
            elif hasattr(mouse_event, "globalPos"):
                global_pos = mouse_event.globalPos()
            target = self._lens_palette_dock if self._lens_palette_dock else self._lens_palette
            if global_pos and target:
                if not target.frameGeometry().contains(global_pos):
                    if not self._global_rect(self.lens_palette_btn).contains(global_pos):
                        self._hide_lens_palette()
        return super().eventFilter(obj, event)

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
        view_config.save_view_config(
            self._workspace_id(),
            self._view_config,
            last_lens_id=self._lens,
            icon_style=self._icon_style,
        )

    def _clear_all_filters(self) -> None:
        current_theme = self._node_theme
        current_pulse = self._pulse_settings
        current_stuck = self._view_config.span_stuck_seconds
        self._view_config = view_config.reset_to_defaults(self._lens, icon_style=self._icon_style)
        self._view_config.node_theme = current_theme
        self._view_config.pulse_settings = current_pulse
        self._view_config.span_stuck_seconds = current_stuck
        self._node_theme = current_theme
        self._pulse_settings = current_pulse
        self._diff_filters = {key: False for key in self._diff_filters}
        self._sync_view_controls()
        self._persist_view_config()
        self._render_current_graph()
        self._update_mode_status(0, 0)

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

    def _on_status_tick(self) -> None:
        self._update_debug_status()
        self._refresh_span_activity()
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
                label = f"{label} — {self._format_age(float(last_seen))} ago"
            action = QtGui.QAction(label, menu)
            icon = self._status_icon(status.get("color"))
            if icon:
                action.setIcon(icon)
            menu.addAction(action)
        menu.addSeparator()
        legend = [
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

    def _on_runtime_event(self, event: CodeSeeEvent) -> None:
        for node_id in event.node_ids or []:
            events = self._events_by_node.setdefault(node_id, [])
            events.append(event)
            if len(events) > self._overlay_limit:
                self._events_by_node[node_id] = events[-self._overlay_limit :]
            if self._live_enabled:
                self._add_overlay_badge(node_id, event)
                self._add_overlay_check(node_id, event)
        if self._live_enabled:
            self._render_current_graph()
            self._emit_live_signal(event)
        if event.kind in (EVENT_SPAN_START, EVENT_SPAN_UPDATE, EVENT_SPAN_END) and not self._live_enabled:
            self._render_current_graph()
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
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Pulse Settings")
        layout = QtWidgets.QVBoxLayout(dialog)
        form = QtWidgets.QFormLayout()

        speed = QtWidgets.QSpinBox()
        speed.setRange(100, 5000)
        speed.setValue(int(self._pulse_settings.travel_speed_px_per_s))
        form.addRow("Travel speed (px/s)", speed)

        travel_duration = QtWidgets.QSpinBox()
        travel_duration.setRange(0, 5000)
        travel_duration.setValue(int(self._pulse_settings.travel_duration_ms))
        form.addRow("Travel duration (ms, 0=auto)", travel_duration)

        duration = QtWidgets.QSpinBox()
        duration.setRange(150, 2000)
        duration.setValue(int(self._pulse_settings.pulse_duration_ms))
        form.addRow("Pulse duration (ms)", duration)

        linger = QtWidgets.QSpinBox()
        linger.setRange(0, 2000)
        linger.setValue(int(self._pulse_settings.arrive_linger_ms))
        form.addRow("Node sticky (ms)", linger)

        fade = QtWidgets.QSpinBox()
        fade.setRange(100, 3000)
        fade.setValue(int(self._pulse_settings.fade_ms))
        form.addRow("Fade (ms)", fade)

        curve = QtWidgets.QComboBox()
        curve.addItem("Linear", "linear")
        curve.addItem("Ease Out", "ease")
        curve_index = curve.findData(self._pulse_settings.fade_curve)
        if curve_index >= 0:
            curve.setCurrentIndex(curve_index)
        form.addRow("Fade curve", curve)

        radius = QtWidgets.QSpinBox()
        radius.setRange(4, 24)
        radius.setValue(int(self._pulse_settings.pulse_radius_px))
        form.addRow("Pulse radius (px)", radius)

        alpha = QtWidgets.QDoubleSpinBox()
        alpha.setRange(0.1, 1.0)
        alpha.setSingleStep(0.05)
        alpha.setDecimals(2)
        alpha.setValue(float(self._pulse_settings.pulse_alpha))
        form.addRow("Pulse alpha", alpha)

        min_alpha = QtWidgets.QDoubleSpinBox()
        min_alpha.setRange(0.0, 0.8)
        min_alpha.setSingleStep(0.05)
        min_alpha.setDecimals(2)
        min_alpha.setValue(float(self._pulse_settings.pulse_min_alpha))
        form.addRow("Min intensity", min_alpha)

        intensity = QtWidgets.QDoubleSpinBox()
        intensity.setRange(0.2, 2.0)
        intensity.setSingleStep(0.1)
        intensity.setDecimals(2)
        intensity.setValue(float(self._pulse_settings.intensity_multiplier))
        form.addRow("Intensity multiplier", intensity)

        trail_length = QtWidgets.QSpinBox()
        trail_length.setRange(1, 8)
        trail_length.setValue(int(getattr(self._pulse_settings, "trail_length", 3)))
        form.addRow("Trail length (dots)", trail_length)

        trail_spacing = QtWidgets.QSpinBox()
        trail_spacing.setRange(30, 400)
        trail_spacing.setValue(int(getattr(self._pulse_settings, "trail_spacing_ms", 70)))
        form.addRow("Trail spacing (ms)", trail_spacing)

        tint_active = QtWidgets.QCheckBox("Tint node while active span runs")
        tint_active.setChecked(bool(self._pulse_settings.tint_active_spans))
        form.addRow(tint_active)

        max_signals = QtWidgets.QSpinBox()
        max_signals.setRange(1, 20)
        max_signals.setValue(int(self._pulse_settings.max_concurrent_signals))
        form.addRow("Max concurrent", max_signals)

        topic_group = QtWidgets.QGroupBox("Pulse topics")
        topic_layout = QtWidgets.QVBoxLayout(topic_group)
        topic_checks: Dict[str, QtWidgets.QCheckBox] = {}
        for key, label in _pulse_topic_labels().items():
            checkbox = QtWidgets.QCheckBox(label)
            enabled = bool(getattr(self._pulse_settings, "topic_enabled", {}).get(key, True))
            checkbox.setChecked(enabled)
            topic_layout.addWidget(checkbox)
            topic_checks[key] = checkbox
        layout.addWidget(topic_group)

        layout.addLayout(form)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        self._pulse_settings = view_config.PulseSettings(
            travel_speed_px_per_s=int(speed.value()),
            travel_duration_ms=int(travel_duration.value()),
            arrive_linger_ms=int(linger.value()),
            fade_ms=int(fade.value()),
            pulse_duration_ms=int(duration.value()),
            pulse_radius_px=int(radius.value()),
            pulse_alpha=float(alpha.value()),
            pulse_min_alpha=float(min_alpha.value()),
            intensity_multiplier=float(intensity.value()),
            fade_curve=str(curve.currentData() or "linear"),
            trail_length=int(trail_length.value()),
            trail_spacing_ms=int(trail_spacing.value()),
            max_concurrent_signals=int(max_signals.value()),
            tint_active_spans=bool(tint_active.isChecked()),
            topic_enabled={key: bool(check.isChecked()) for key, check in topic_checks.items()},
        )
        self._view_config.pulse_settings = self._pulse_settings
        self._persist_view_config()
        self._render_current_graph()

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
        self._pulse_settings = self._view_config.pulse_settings
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

    def _inspect_node(self, node: Node, badge: Optional[Badge]) -> None:
        graph = self._current_graph
        if self._diff_mode and self._diff_compare_graph:
            graph = self._diff_compare_graph
        if not graph:
            return
        diff_state = None
        diff_change = None
        if self._diff_mode and self._diff_result:
            if node.node_id in self._diff_result.nodes_added:
                diff_state = "added"
            elif node.node_id in self._diff_result.nodes_changed:
                diff_state = "changed"
                diff_change = self._diff_result.node_change_details.get(node.node_id)
        events = []
        if self._runtime_hub:
            events = self._runtime_hub.query(node.node_id, limit=20)
        elif node.node_id in self._events_by_node:
            events = list(self._events_by_node[node.node_id])
        crash_record = None
        crash_build = None
        if self._crash_view and self._crash_record and node.node_id == self._crash_node_id:
            crash_record = self._crash_record
            if isinstance(crash_record, dict):
                crash_build = crash_record.get("build")
        dialog = CodeSeeInspectorDialog(
            node,
            graph,
            badge,
            diff_state,
            diff_change,
            events,
            crash_record,
            self._build_info,
            crash_build,
            self._view_config.span_stuck_seconds,
            parent=self,
        )
        dialog.exec()

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
        filter_count = len(view_config.build_active_filter_chips(self._view_config))
        filter_count += sum(1 for value in self._diff_filters.values() if value)
        diff_counts = None
        if self._diff_mode and self._diff_result:
            diff_counts = (
                f"+{len(self._diff_result.nodes_added)} "
                f"-{len(self._diff_result.nodes_removed)} "
                f"Δ{len(self._diff_result.nodes_changed)}"
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


def _pulse_topic_labels() -> Dict[str, str]:
    return {
        "app.activity": "App activity",
        "app.error": "App error",
        "app.crash": "App crash",
        "job.update": "Job update",
        "span.start": "Span start",
        "span.update": "Span update",
        "span.end": "Span end",
        "bus.request": "Bus request",
        "bus.reply": "Bus reply",
        "expect.check": "Expectation check",
        "codesee.test_pulse": "Test pulse",
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


def _span_is_stuck(span: SpanRecord, now: float, threshold: int) -> bool:
    if span.status != "active":
        return False
    last_ts = span.updated_ts or span.started_ts
    if not last_ts:
        return False
    return (now - last_ts) >= float(threshold)


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


class CodeSeeInspectorDialog(QtWidgets.QDialog):
    def __init__(
        self,
        node: Node,
        graph: ArchitectureGraph,
        selected_badge: Optional[Badge],
        diff_state: Optional[str],
        diff_change: Optional[NodeChange],
        events: list[CodeSeeEvent],
        crash_record: Optional[dict],
        build_info: Optional[dict],
        crash_build_info: Optional[dict],
        span_stuck_seconds: int,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Code See Inspector")
        self.setMinimumWidth(480)

        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel(node.title)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        meta = QtWidgets.QLabel(f"ID: {node.node_id} | Type: {node.node_type}")
        meta.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(meta)

        meta_label = QtWidgets.QLabel("Extensions & Metadata")
        meta_label.setStyleSheet("color: #444;")
        layout.addWidget(meta_label)
        meta_text = QtWidgets.QPlainTextEdit()
        meta_text.setReadOnly(True)
        meta_text.setPlainText(_format_metadata(node.metadata))
        layout.addWidget(meta_text)

        build_label = QtWidgets.QLabel("Build")
        build_label.setStyleSheet("color: #444;")
        layout.addWidget(build_label)
        build_text = QtWidgets.QPlainTextEdit()
        build_text.setReadOnly(True)
        build_text.setPlainText(_format_build_info(build_info, crash_build_info))
        layout.addWidget(build_text)

        if selected_badge:
            selected = QtWidgets.QLabel(f"Selected badge: {_format_badge_line(selected_badge)}")
            selected.setWordWrap(True)
            layout.addWidget(selected)

        if diff_state:
            diff_label = QtWidgets.QLabel(f"Diff status: {diff_state}")
            diff_label.setStyleSheet("color: #555;")
            layout.addWidget(diff_label)
            if diff_change:
                diff_details = QtWidgets.QPlainTextEdit()
                diff_details.setReadOnly(True)
                diff_details.setPlainText(_format_diff_change(diff_change))
                layout.addWidget(diff_details)

        badges_label = QtWidgets.QLabel("Badges")
        badges_label.setStyleSheet("color: #444;")
        layout.addWidget(badges_label)
        badges_text = QtWidgets.QPlainTextEdit()
        badges_text.setReadOnly(True)
        badges_text.setPlainText(_format_badges(node.badges))
        layout.addWidget(badges_text)

        activity_label = QtWidgets.QLabel("Activity")
        activity_label.setStyleSheet("color: #444;")
        layout.addWidget(activity_label)
        activity_text = QtWidgets.QPlainTextEdit()
        activity_text.setReadOnly(True)
        activity_text.setPlainText(_format_spans(node.spans, span_stuck_seconds))
        layout.addWidget(activity_text)

        edges_label = QtWidgets.QLabel("Edges")
        edges_label.setStyleSheet("color: #444;")
        layout.addWidget(edges_label)
        edges_text = QtWidgets.QPlainTextEdit()
        edges_text.setReadOnly(True)
        edges_text.setPlainText(_format_edges(graph, node))
        layout.addWidget(edges_text)

        events_label = QtWidgets.QLabel("Recent events")
        events_label.setStyleSheet("color: #444;")
        layout.addWidget(events_label)
        events_text = QtWidgets.QPlainTextEdit()
        events_text.setReadOnly(True)
        events_text.setPlainText(_format_events(events))
        layout.addWidget(events_text)

        if crash_record:
            crash_label = QtWidgets.QLabel("Crash")
            crash_label.setStyleSheet("color: #444;")
            layout.addWidget(crash_label)
            crash_text = QtWidgets.QPlainTextEdit()
            crash_text.setReadOnly(True)
            crash_text.setPlainText(_format_crash_record(crash_record))
            layout.addWidget(crash_text)

        checks_label = QtWidgets.QLabel("Expected vs Actual")
        checks_label.setStyleSheet("color: #444;")
        layout.addWidget(checks_label)
        checks_text = QtWidgets.QPlainTextEdit()
        checks_text.setReadOnly(True)
        checks_text.setPlainText(_format_checks(node.checks))
        layout.addWidget(checks_text)

        close_row = QtWidgets.QHBoxLayout()
        close_row.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)


class CodeSeeRemovedDialog(QtWidgets.QDialog):
    def __init__(self, diff_result: DiffResult, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Removed Items")
        self.setMinimumWidth(420)

        layout = QtWidgets.QVBoxLayout(self)
        nodes_label = QtWidgets.QLabel("Removed Nodes")
        nodes_label.setStyleSheet("color: #444;")
        layout.addWidget(nodes_label)
        nodes_text = QtWidgets.QPlainTextEdit()
        nodes_text.setReadOnly(True)
        nodes_text.setPlainText(_format_removed_nodes(diff_result))
        layout.addWidget(nodes_text)

        edges_label = QtWidgets.QLabel("Removed Edges")
        edges_label.setStyleSheet("color: #444;")
        layout.addWidget(edges_label)
        edges_text = QtWidgets.QPlainTextEdit()
        edges_text.setReadOnly(True)
        edges_text.setPlainText(_format_removed_edges(diff_result))
        layout.addWidget(edges_text)

        close_row = QtWidgets.QHBoxLayout()
        close_row.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)


def _format_badges(badges: list[Badge]) -> str:
    if not badges:
        return "No badges."
    lines = []
    for badge in sort_by_priority(badges):
        lines.append(_format_badge_line(badge))
        if badge.detail:
            lines.append(f"  detail: {badge.detail}")
        if badge.timestamp:
            lines.append(f"  timestamp: {badge.timestamp}")
    return "\n".join(lines)


def _format_badge_line(badge: Badge) -> str:
    line = f"{badge.key} ({badge.rail}) - {badge.title}: {badge.summary}"
    return line.strip()


def _format_edges(graph: ArchitectureGraph, node: Node) -> str:
    node_map = graph.node_map()
    outgoing = []
    incoming = []
    for edge in graph.edges:
        if edge.src_node_id == node.node_id:
            dst = node_map.get(edge.dst_node_id)
            dst_label = dst.title if dst else edge.dst_node_id
            outgoing.append(f"{edge.kind} -> {dst_label} ({edge.dst_node_id})")
        if edge.dst_node_id == node.node_id:
            src = node_map.get(edge.src_node_id)
            src_label = src.title if src else edge.src_node_id
            incoming.append(f"{edge.kind} <- {src_label} ({edge.src_node_id})")
    if not outgoing and not incoming:
        return "No edges."
    lines = []
    if outgoing:
        lines.append("Outgoing:")
        lines.extend(f"- {line}" for line in outgoing)
    if incoming:
        lines.append("Incoming:")
        lines.extend(f"- {line}" for line in incoming)
    return "\n".join(lines)


def _format_diff_change(change: NodeChange) -> str:
    lines = ["Before:", f"  title: {change.before.title}", f"  type: {change.before.node_type}"]
    lines.append(f"  severity: {change.severity_before}")
    lines.append("  badges:")
    lines.extend(f"    - {_format_badge_line(badge)}" for badge in change.badges_before)
    lines.append("After:")
    lines.append(f"  title: {change.after.title}")
    lines.append(f"  type: {change.after.node_type}")
    lines.append(f"  severity: {change.severity_after}")
    lines.append("  badges:")
    lines.extend(f"    - {_format_badge_line(badge)}" for badge in change.badges_after)
    lines.append(f"Changed fields: {', '.join(change.fields_changed)}")
    return "\n".join(lines)


def _format_removed_nodes(diff_result: DiffResult) -> str:
    if not diff_result.nodes_removed:
        return "No removed nodes."
    return "\n".join(sorted(diff_result.nodes_removed))


def _format_removed_edges(diff_result: DiffResult) -> str:
    if not diff_result.edges_removed:
        return "No removed edges."
    lines = []
    for src, dst, kind in sorted(diff_result.edges_removed):
        lines.append(f"{kind}: {src} -> {dst}")
    return "\n".join(lines)


def _format_events(events: list[CodeSeeEvent]) -> str:
    if not events:
        return "No recent events."
    lines = []
    for event in events:
        line = f"{event.ts} | {event.kind} | {event.severity}: {event.message}"
        if event.detail:
            line = f"{line}\n  {event.detail}"
        lines.append(line)
    return "\n".join(lines)


def _format_metadata(metadata: dict) -> str:
    if not metadata:
        return "No metadata."
    lines = []
    for key in sorted(metadata.keys()):
        value = metadata.get(key)
        if isinstance(value, dict):
            lines.append(f"{key}:")
            for sub_key in sorted(value.keys()):
                lines.append(f"  {sub_key}: {value.get(sub_key)}")
            continue
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _format_spans(spans: list[SpanRecord], stuck_threshold_s: int, limit: int = 6) -> str:
    if not spans:
        return "No activity spans."
    now = time.time()
    sorted_spans = sorted(
        spans,
        key=lambda s: s.updated_ts or s.started_ts or 0.0,
        reverse=True,
    )[:limit]
    lines = []
    for span in sorted_spans:
        status = span.status or "active"
        if _span_is_stuck(span, now, stuck_threshold_s):
            status = "stuck"
        ts = span.updated_ts or span.started_ts
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "n/a"
        progress = ""
        if span.progress is not None:
            if 0.0 <= span.progress <= 1.0:
                progress = f" ({int(span.progress * 100)}%)"
            else:
                progress = f" ({span.progress})"
        message = f" - {span.message}" if span.message else ""
        lines.append(f"{stamp} | {status.upper()} | {span.label}{progress}{message}")
    return "\n".join(lines)


def _format_build_info(build: Optional[dict], crash_build: Optional[dict]) -> str:
    build = build if isinstance(build, dict) else {}
    crash_build = crash_build if isinstance(crash_build, dict) else {}
    app_version = build.get("app_version") or "unknown"
    build_id = build.get("build_id") or "unknown"
    lines = [f"Current: {app_version} ({build_id})"]
    if crash_build:
        crash_version = crash_build.get("app_version") or "unknown"
        crash_id = crash_build.get("build_id") or "unknown"
        if crash_version != app_version or crash_id != build_id:
            lines.append(f"Crash: {crash_version} ({crash_id})")
    return "\n".join(lines)


def _format_checks(checks: list[EVACheck], limit: int = 5) -> str:
    if not checks:
        return "No expectation checks."
    recent = sorted(checks, key=lambda c: c.ts or 0.0, reverse=True)[:limit]
    lines = []
    for check in recent:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(check.ts)) if check.ts else "n/a"
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"{stamp} | {status} | {check.message}")
        lines.append(f"  expected: {check.expected}")
        lines.append(f"  actual: {check.actual}")
        lines.append(f"  mode: {check.mode}")
        if check.tolerance is not None:
            lines.append(f"  tolerance: {check.tolerance}")
        if check.context:
            lines.append(f"  context: {check.context}")
    return "\n".join(lines)


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


def _format_crash_record(record: dict, limit_lines: int = 12) -> str:
    ts = record.get("ts")
    stamp = "n/a"
    if isinstance(ts, (int, float)):
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    exc_type = record.get("exception_type") or "Crash"
    message = record.get("message") or ""
    where = record.get("where") or "startup"
    traceback_text = record.get("traceback") or ""
    lines = traceback_text.splitlines()
    if limit_lines and len(lines) > limit_lines:
        lines = lines[-limit_lines:]
    excerpt = "\n".join(lines).strip() or "(traceback unavailable)"
    return (
        f"Time: {stamp}\n"
        f"Where: {where}\n"
        f"Type: {exc_type}\n"
        f"Message: {message}\n"
        f"Traceback:\n{excerpt}"
    )


def _format_crash_timestamp(record: Optional[dict]) -> str:
    if not isinstance(record, dict):
        return "n/a"
    ts = record.get("ts")
    if isinstance(ts, (int, float)):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    return "n/a"


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
