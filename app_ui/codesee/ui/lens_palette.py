# =============================================================================
# NAV INDEX (search these tags)
# [NAV-00] Imports / constants
# [NAV-10] Lens tile spec + filtering
# [NAV-20] Dock orientation helper
# [NAV-30] Icon/pixmap cache helpers
# [NAV-40] LensPaletteWidget
# =============================================================================

# === [NAV-00] Imports / constants ============================================
# region NAV-00 Imports / constants
from __future__ import annotations

import functools
import os
from typing import Callable, Dict, Optional

from PyQt6 import QtCore, QtGui, QtSvg, QtWidgets

from app_ui import ui_scale

from .. import icon_pack
from ..lenses import LENS_ATLAS, LENS_BUS, LENS_CONTENT, LENS_PLATFORM

LENS_EXT = "extensibility"
_LENS_ICON_CACHE: Dict[tuple[str, str, int, str], QtGui.QPixmap] = {}
# endregion NAV-00 Imports / constants


# === [NAV-10] Lens tile spec + filtering =====================================
# region NAV-10 Lens tile spec + filtering
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
# endregion NAV-10 Lens tile spec + filtering


# === [NAV-20] Dock orientation helper ========================================
# region NAV-20 Dock orientation helper
def lens_palette_dock_orientation(
    area: QtCore.Qt.DockWidgetArea,
) -> Optional[QtCore.Qt.Orientation]:
    if area in (
        QtCore.Qt.DockWidgetArea.LeftDockWidgetArea,
        QtCore.Qt.DockWidgetArea.RightDockWidgetArea,
    ):
        return QtCore.Qt.Orientation.Horizontal
    if area in (
        QtCore.Qt.DockWidgetArea.TopDockWidgetArea,
        QtCore.Qt.DockWidgetArea.BottomDockWidgetArea,
    ):
        return QtCore.Qt.Orientation.Vertical
    return None
# endregion NAV-20 Dock orientation helper


# === [NAV-30] Icon/pixmap cache helpers ======================================
# region NAV-30 Icon/pixmap cache helpers
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
# endregion NAV-30 Icon/pixmap cache helpers


# === [NAV-40] LensPaletteWidget ==============================================
# region NAV-40 LensPaletteWidget
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
        self._on_diagnostics: Optional[Callable[[], None]] = None
        self._on_clear_recent: Optional[Callable[[], None]] = None
        self._on_clear_search: Optional[Callable[[], None]] = None
        self._on_float_palette: Optional[Callable[[], None]] = None
        self._on_reset_layout: Optional[Callable[[], None]] = None
        self._on_refresh_inventory: Optional[Callable[[], None]] = None
        self._on_trail_focus_toggled: Optional[Callable[[bool], None]] = None
        self._pinned = False
        self._expanded = False
        self._active_lens_id = ""
        self._recent: list[str] = []
        self._tile_buttons: Dict[str, QtWidgets.QToolButton] = {}
        self._tile_widgets: list[QtWidgets.QToolButton] = []
        self._trail_focus_syncing = False

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
            "QToolButton#lensPaletteTrail { color: #cfd8dc; background: #222733; border: 1px solid #2f3540; border-radius: 8px; padding: 4px 10px; }"
            "QToolButton#lensPaletteTrail:checked { background: #2c3e63; border: 1px solid #4c6ef5; color: #ffffff; }"
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

        self._trail_row = QtWidgets.QWidget()
        trail_layout = QtWidgets.QHBoxLayout(self._trail_row)
        trail_layout.setContentsMargins(0, 0, 0, 0)
        trail_layout.setSpacing(6)
        self._trail_label = QtWidgets.QLabel("Trail")
        self._trail_toggle = QtWidgets.QToolButton()
        self._trail_toggle.setObjectName("lensPaletteTrail")
        self._trail_toggle.setCheckable(True)
        self._trail_toggle.setText("OFF")
        self._trail_toggle.toggled.connect(self._on_trail_toggle_changed)
        trail_layout.addWidget(self._trail_label)
        trail_layout.addStretch()
        trail_layout.addWidget(self._trail_toggle)
        self._trail_row.setVisible(False)
        layout.addWidget(self._trail_row)

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
        self._more_btn.setText("More... >")
        self._more_btn.setToolTip("Palette actions")
        self._more_btn.clicked.connect(self._show_more_menu)
        footer_row.addWidget(self._more_btn)
        layout.addLayout(footer_row)

        self._more_menu = QtWidgets.QMenu(self)
        self._more_menu.setStyleSheet(
            "QMenu { background: #1b1f27; color: #cfd8dc; border: 1px solid #2a2f38; }"
            "QMenu::item { padding: 6px 24px 6px 24px; }"
            "QMenu::item:selected { background: #242a35; }"
            "QMenu::separator { height: 1px; background: #2a2f38; margin: 4px 8px; }"
        )

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

    def set_on_diagnostics(self, callback: Callable[[], None]) -> None:
        self._on_diagnostics = callback

    def set_on_clear_recent(self, callback: Callable[[], None]) -> None:
        self._on_clear_recent = callback

    def set_on_clear_search(self, callback: Callable[[], None]) -> None:
        self._on_clear_search = callback

    def set_on_float_palette(self, callback: Callable[[], None]) -> None:
        self._on_float_palette = callback

    def set_on_reset_layout(self, callback: Callable[[], None]) -> None:
        self._on_reset_layout = callback

    def set_on_refresh_inventory(self, callback: Callable[[], None]) -> None:
        self._on_refresh_inventory = callback

    def set_on_trail_focus_toggled(self, callback: Callable[[bool], None]) -> None:
        self._on_trail_focus_toggled = callback

    def set_trail_focus_control(self, *, visible: bool, enabled: bool, checked: bool) -> None:
        self._trail_row.setVisible(bool(visible))
        self._trail_toggle.setEnabled(bool(enabled))
        self._trail_focus_syncing = True
        try:
            self._trail_toggle.setChecked(bool(checked))
            self._trail_toggle.setText("ON" if bool(checked) else "OFF")
        finally:
            self._trail_focus_syncing = False

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

    def _on_trail_toggle_changed(self, checked: bool) -> None:
        self._trail_toggle.setText("ON" if bool(checked) else "OFF")
        if self._trail_focus_syncing:
            return
        if self._on_trail_focus_toggled:
            self._on_trail_focus_toggled(bool(checked))

    def _menu_icon(self, icon_key: str) -> QtGui.QIcon:
        icon_size = int(ui_scale.scale_px(16))
        tint = QtGui.QColor("#9fb8ff")
        pixmap = _lens_palette_icon_pixmap(icon_key, icon_pack.ICON_STYLE_MONO, icon_size, tint)
        if pixmap:
            return QtGui.QIcon(pixmap)
        return QtGui.QIcon()

    def _build_more_menu(self) -> None:
        self._more_menu.clear()

        manage_action = QtGui.QAction(self._menu_icon("state.info"), "Manage Lenses...", self._more_menu)
        manage_action.setEnabled(False)
        self._more_menu.addAction(manage_action)

        add_action = QtGui.QAction(self._menu_icon("state.add"), "Add Lens... (Coming soon)", self._more_menu)
        add_action.setEnabled(False)
        self._more_menu.addAction(add_action)

        delete_action = QtGui.QAction(self._menu_icon("state.delete"), "Delete Lens... (Coming soon)", self._more_menu)
        delete_action.setEnabled(False)
        self._more_menu.addAction(delete_action)

        install_action = QtGui.QAction(self._menu_icon("state.download"), "Install Lens Pack...", self._more_menu)
        install_action.setEnabled(False)
        self._more_menu.addAction(install_action)

        refresh_action = QtGui.QAction(self._menu_icon("state.refresh"), "Refresh Lens Inventory", self._more_menu)
        refresh_action.triggered.connect(self._refresh_inventory_action)
        self._more_menu.addAction(refresh_action)

        plugin_action = QtGui.QAction(self._menu_icon("state.plugin"), "Plugin Registry... (Coming soon)", self._more_menu)
        plugin_action.setEnabled(False)
        self._more_menu.addAction(plugin_action)

        self._more_menu.addSeparator()

        float_action = QtGui.QAction(self._menu_icon("state.float"), "Float Palette", self._more_menu)
        float_action.triggered.connect(self._float_palette_action)
        self._more_menu.addAction(float_action)

        reset_action = QtGui.QAction(self._menu_icon("state.reset"), "Reset Palette Layout", self._more_menu)
        reset_action.triggered.connect(self._reset_layout_action)
        self._more_menu.addAction(reset_action)

        self._more_menu.addSeparator()

        clear_recent = QtGui.QAction(self._menu_icon("state.clear"), "Clear Recent", self._more_menu)
        clear_recent.triggered.connect(self._clear_recent_action)
        self._more_menu.addAction(clear_recent)

        clear_search = QtGui.QAction(self._menu_icon("state.search"), "Clear Search", self._more_menu)
        clear_search.triggered.connect(self._clear_search_action)
        self._more_menu.addAction(clear_search)

        diagnostics_action = QtGui.QAction(self._menu_icon("state.info"), "Diagnostics (CodeSee)...", self._more_menu)
        diagnostics_action.triggered.connect(self._emit_diagnostics)
        self._more_menu.addAction(diagnostics_action)

    def _show_more_menu(self) -> None:
        self._build_more_menu()
        self._more_menu.exec(self._more_btn.mapToGlobal(QtCore.QPoint(0, 24)))

    def _emit_diagnostics(self) -> None:
        if self._on_diagnostics:
            self._on_diagnostics()

    def _clear_recent_action(self) -> None:
        if self._on_clear_recent:
            self._on_clear_recent()

    def _clear_search_action(self) -> None:
        if self._search:
            self._search.setText("")
        if self._on_clear_search:
            self._on_clear_search()

    def _float_palette_action(self) -> None:
        if self._on_float_palette:
            self._on_float_palette()

    def _reset_layout_action(self) -> None:
        if self._on_reset_layout:
            self._on_reset_layout()

    def _refresh_inventory_action(self) -> None:
        if self._on_refresh_inventory:
            self._on_refresh_inventory()

    def _toggle_expanded(self) -> None:
        self._set_expanded(not self._expanded)

    def _set_expanded(self, expanded: bool) -> None:
        if self._expanded == bool(expanded):
            return
        self._expanded = bool(expanded)
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
        max_height = int(ui_scale.scale_px(900))
        self.setMinimumHeight(min_height)
        if self._pinned:
            self.setMaximumHeight(16777215)
        else:
            self.setMaximumHeight(max_height)
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



# endregion NAV-40 LensPaletteWidget
