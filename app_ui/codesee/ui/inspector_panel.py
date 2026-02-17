from __future__ import annotations

from typing import Callable, Optional

from PyQt6 import QtCore, QtWidgets

from ..item_ref import ItemRef
from ..relations import (
    CATEGORY_CONTAINED_BY,
    CATEGORY_CONTAINS,
    CATEGORY_DEPENDENTS,
    CATEGORY_DEPENDS_ON,
    CATEGORY_EXPORTS,
    RelationPage,
    RelationRow,
)

RelationProvider = Callable[[str, int, int, str], RelationPage]


class PagedRelationSection(QtWidgets.QGroupBox):
    def __init__(
        self,
        *,
        title: str,
        category: str,
        on_relation_selected: Callable[[ItemRef], None],
        on_relation_inspect: Callable[[ItemRef], None],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(title, parent)
        self._category = category
        self._on_relation_selected = on_relation_selected
        self._on_relation_inspect = on_relation_inspect
        self._provider: Optional[RelationProvider] = None
        self._page_size = 50
        self._loaded_count = 0
        self._total_count = 0
        self._filter_text = ""

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self._filter = QtWidgets.QLineEdit()
        self._filter.setPlaceholderText("Filter by name or id")
        root.addWidget(self._filter)

        self._table = QtWidgets.QTreeWidget()
        self._table.setRootIsDecorated(False)
        self._table.setUniformRowHeights(True)
        self._table.setAlternatingRowColors(False)
        self._table.setHeaderLabels(["Name", "Kind", "Detail"])
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self._table.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        root.addWidget(self._table)

        self._message = QtWidgets.QLabel("")
        self._message.setStyleSheet("color: #777;")
        self._message.setWordWrap(True)
        self._message.setVisible(False)
        root.addWidget(self._message)

        footer = QtWidgets.QHBoxLayout()
        self._count_label = QtWidgets.QLabel("Showing 0 of 0")
        self._count_label.setStyleSheet("color: #666;")
        footer.addWidget(self._count_label, stretch=1)
        self._load_more_btn = QtWidgets.QToolButton()
        self._load_more_btn.setText("Load more")
        self._load_more_btn.clicked.connect(self._load_more)
        footer.addWidget(self._load_more_btn)
        self._inspect_btn = QtWidgets.QToolButton()
        self._inspect_btn.setText("Inspect")
        self._inspect_btn.clicked.connect(self._inspect_selected)
        footer.addWidget(self._inspect_btn)
        root.addLayout(footer)

        self._filter_timer = QtCore.QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(200)
        self._filter_timer.timeout.connect(self._apply_filter_debounced)

        self._filter.textChanged.connect(self._on_filter_changed)
        self._table.itemSelectionChanged.connect(self._sync_controls_from_selection)
        self._table.itemClicked.connect(self._on_item_clicked)

        self.clear_rows("No relations found.")

    def set_provider(self, provider: RelationProvider, *, page_size: int = 50) -> None:
        self._provider = provider
        self._page_size = max(1, int(page_size))
        blocker = QtCore.QSignalBlocker(self._filter)
        self._filter.setText("")
        del blocker
        self._filter_text = ""
        self._reload(reset_table=True)

    def set_filter_text(self, text: str) -> None:
        clean = (text or "").strip()
        blocker = QtCore.QSignalBlocker(self._filter)
        self._filter.setText(clean)
        del blocker
        if self._provider is None:
            return
        self._filter_text = clean
        self._reload(reset_table=True)

    def clear_rows(self, message: str) -> None:
        self._provider = None
        self._table.clear()
        self._loaded_count = 0
        self._total_count = 0
        self._set_message(message)
        self._count_label.setText("Showing 0 of 0")
        self._load_more_btn.setEnabled(False)
        self._inspect_btn.setEnabled(False)

    def _on_filter_changed(self, _text: str) -> None:
        if self._provider is None:
            return
        self._filter_timer.start()

    def _apply_filter_debounced(self) -> None:
        if self._provider is None:
            return
        self._filter_text = self._filter.text().strip()
        self._reload(reset_table=True)

    def _reload(self, *, reset_table: bool) -> None:
        if self._provider is None:
            self.clear_rows("No relations found.")
            return
        page = self._provider(self._category, 0, self._page_size, self._filter_text)
        if reset_table:
            self._table.clear()
        self._append_rows(page.rows)
        self._loaded_count = len(page.rows)
        self._total_count = max(0, int(page.total))
        self._refresh_footer()
        self._set_message("No relations found." if self._total_count == 0 else "")

    def _load_more(self) -> None:
        if self._provider is None:
            return
        if self._loaded_count >= self._total_count:
            return
        page = self._provider(self._category, self._loaded_count, self._page_size, self._filter_text)
        self._append_rows(page.rows)
        self._loaded_count += len(page.rows)
        self._total_count = max(self._total_count, int(page.total))
        self._refresh_footer()

    def _append_rows(self, rows: list[RelationRow]) -> None:
        for row in rows:
            item = QtWidgets.QTreeWidgetItem([row.label, row.kind_badge, row.detail])
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, row)
            if row.item_ref is None:
                for col in range(3):
                    item.setForeground(col, QtCore.Qt.GlobalColor.darkGray)
            self._table.addTopLevelItem(item)

    def _on_item_clicked(self, item: QtWidgets.QTreeWidgetItem, _column: int) -> None:
        row = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(row, RelationRow) and row.item_ref is not None:
            self._on_relation_selected(row.item_ref)
        self._sync_controls_from_selection()

    def _inspect_selected(self) -> None:
        row = self._selected_relation_row()
        if row is None or row.item_ref is None:
            return
        self._on_relation_inspect(row.item_ref)

    def _selected_relation_row(self) -> Optional[RelationRow]:
        selected = self._table.selectedItems()
        if not selected:
            return None
        row = selected[0].data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(row, RelationRow):
            return row
        return None

    def _sync_controls_from_selection(self) -> None:
        row = self._selected_relation_row()
        self._inspect_btn.setEnabled(row is not None and row.item_ref is not None)

    def _refresh_footer(self) -> None:
        self._count_label.setText(f"Showing {self._loaded_count} of {self._total_count}")
        can_load_more = self._provider is not None and self._loaded_count < self._total_count
        self._load_more_btn.setEnabled(can_load_more)
        self._sync_controls_from_selection()

    def _set_message(self, text: str) -> None:
        clean = text.strip()
        self._message.setText(clean)
        self._message.setVisible(bool(clean))


class CodeSeeInspectorPanel(QtWidgets.QWidget):
    def __init__(
        self,
        *,
        on_back: Callable[[], None],
        on_forward: Callable[[], None],
        on_lock_toggled: Callable[[bool], None],
        on_relation_selected: Callable[[ItemRef], None],
        on_relation_inspect: Callable[[ItemRef], None],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._current_item_id = ""
        self._can_back = False
        self._on_back = on_back
        self._on_forward = on_forward
        self._on_lock_toggled = on_lock_toggled
        self._on_relation_selected = on_relation_selected
        self._on_relation_inspect = on_relation_inspect
        self._relations_provider: Optional[RelationProvider] = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        self._title = QtWidgets.QLabel("Inspector")
        self._title.setStyleSheet("font-weight: 600;")
        self._kind = QtWidgets.QLabel("none")
        self._kind.setStyleSheet("color: #666;")
        header.addWidget(self._title, stretch=1)
        header.addWidget(self._kind)
        root.addLayout(header)

        actions = QtWidgets.QHBoxLayout()
        self._copy_btn = QtWidgets.QToolButton()
        self._copy_btn.setText("Copy ID")
        self._copy_btn.clicked.connect(self._copy_current_id)
        actions.addWidget(self._copy_btn)
        self._lock_btn = QtWidgets.QToolButton()
        self._lock_btn.setText("Pin")
        self._lock_btn.setCheckable(True)
        self._lock_btn.toggled.connect(lambda checked: self._on_lock_toggled(bool(checked)))
        actions.addWidget(self._lock_btn)
        self._back_btn = QtWidgets.QToolButton()
        self._back_btn.setText("Back")
        self._back_btn.clicked.connect(self._on_back)
        actions.addWidget(self._back_btn)
        self._forward_btn = QtWidgets.QToolButton()
        self._forward_btn.setText("Forward")
        self._forward_btn.clicked.connect(self._on_forward)
        actions.addWidget(self._forward_btn)
        actions.addStretch()
        root.addLayout(actions)

        self._status = QtWidgets.QLabel("Select a node to inspect.")
        self._status.setStyleSheet("color: #777;")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        tabs = QtWidgets.QTabWidget()
        self._tabs = tabs
        self._overview = QtWidgets.QPlainTextEdit()
        self._overview.setReadOnly(True)
        tabs.addTab(self._overview, "Overview")
        self._properties = QtWidgets.QTableWidget(0, 2)
        self._properties.setHorizontalHeaderLabels(["Property", "Value"])
        self._properties.verticalHeader().setVisible(False)
        self._properties.horizontalHeader().setStretchLastSection(True)
        self._properties.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self._properties.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        tabs.addTab(self._properties, "Properties")

        self._relations_tab = QtWidgets.QWidget()
        relations_root = QtWidgets.QVBoxLayout(self._relations_tab)
        relations_root.setContentsMargins(4, 4, 4, 4)
        relations_root.setSpacing(6)

        self._relations_notice = QtWidgets.QLabel("")
        self._relations_notice.setStyleSheet("color: #666;")
        self._relations_notice.setWordWrap(True)
        self._relations_notice.setVisible(False)
        relations_root.addWidget(self._relations_notice)

        self._relations_back_btn = QtWidgets.QPushButton("Go back")
        self._relations_back_btn.clicked.connect(self._on_back)
        self._relations_back_btn.setVisible(False)
        relations_root.addWidget(self._relations_back_btn, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        self._relations_scroll = QtWidgets.QScrollArea()
        self._relations_scroll.setWidgetResizable(True)
        self._relations_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._relations_sections_host = QtWidgets.QWidget()
        self._relations_sections_layout = QtWidgets.QVBoxLayout(self._relations_sections_host)
        self._relations_sections_layout.setContentsMargins(0, 0, 0, 0)
        self._relations_sections_layout.setSpacing(8)

        self._relation_sections: dict[str, PagedRelationSection] = {}
        sections = [
            (CATEGORY_CONTAINS, "Contains"),
            (CATEGORY_CONTAINED_BY, "Contained by"),
            (CATEGORY_DEPENDS_ON, "Depends on / Uses"),
            (CATEGORY_DEPENDENTS, "Used by / Dependents"),
            (CATEGORY_EXPORTS, "Exports / Entry points"),
        ]
        for category, title in sections:
            section = PagedRelationSection(
                title=title,
                category=category,
                on_relation_selected=self._on_relation_selected,
                on_relation_inspect=self._on_relation_inspect,
                parent=self._relations_sections_host,
            )
            self._relation_sections[category] = section
            self._relations_sections_layout.addWidget(section)
        self._relations_sections_layout.addStretch(1)
        self._relations_scroll.setWidget(self._relations_sections_host)
        relations_root.addWidget(self._relations_scroll)
        tabs.addTab(self._relations_tab, "Relations")

        self._activity_tab = QtWidgets.QWidget()
        activity_root = QtWidgets.QVBoxLayout(self._activity_tab)
        activity_root.setContentsMargins(4, 4, 4, 4)
        activity_root.setSpacing(6)

        self._activity_header = QtWidgets.QLabel("Activity")
        self._activity_header.setStyleSheet("font-weight: 600; color: #ddd;")
        activity_root.addWidget(self._activity_header)

        self._activity_filter = QtWidgets.QLineEdit()
        self._activity_filter.setPlaceholderText("Filter activity")
        activity_root.addWidget(self._activity_filter)

        self._activity_table = QtWidgets.QTreeWidget()
        self._activity_table.setRootIsDecorated(False)
        self._activity_table.setUniformRowHeights(True)
        self._activity_table.setAlternatingRowColors(False)
        self._activity_table.setHeaderLabels(["When", "Type", "Source", "Detail"])
        self._activity_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self._activity_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self._activity_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        activity_header = self._activity_table.header()
        activity_header.setStretchLastSection(True)
        activity_header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        activity_header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        activity_header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        activity_header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        activity_root.addWidget(self._activity_table)

        self._activity_empty = QtWidgets.QLabel("No activity yet.")
        self._activity_empty.setStyleSheet("color: #777;")
        self._activity_empty.setWordWrap(True)
        activity_root.addWidget(self._activity_empty)

        self._activity_items: list[dict[str, str]] = []
        self._activity_filter_timer = QtCore.QTimer(self)
        self._activity_filter_timer.setSingleShot(True)
        self._activity_filter_timer.setInterval(200)
        self._activity_filter_timer.timeout.connect(self._apply_activity_filter)
        self._activity_filter.textChanged.connect(lambda _text: self._activity_filter_timer.start())

        tabs.addTab(self._activity_tab, "Activity")
        root.addWidget(tabs, stretch=1)
        self.set_relations_empty("Select a node to inspect.")
        self.show_activity(mode="empty", title="Activity", items=[], activate=False)

    def set_navigation_state(self, *, can_back: bool, can_forward: bool) -> None:
        self._can_back = bool(can_back)
        self._back_btn.setEnabled(bool(can_back))
        self._forward_btn.setEnabled(bool(can_forward))
        self._relations_back_btn.setEnabled(bool(can_back))

    def set_locked(self, locked: bool) -> None:
        blocker = QtCore.QSignalBlocker(self._lock_btn)
        self._lock_btn.setChecked(bool(locked))
        del blocker

    def set_empty(self, message: str) -> None:
        self._current_item_id = ""
        self._title.setText("Inspector")
        self._kind.setText("none")
        self._status.setText(message)
        self._overview.setPlainText("")
        self._properties.setRowCount(0)
        self._copy_btn.setEnabled(False)
        self.set_relations_empty(message)
        self.show_activity(mode="empty", title="Activity", items=[{"detail": message}], activate=False)

    def set_stale(self, item_ref: ItemRef) -> None:
        self._current_item_id = str(item_ref.id)
        self._title.setText(item_ref.id)
        self._kind.setText(item_ref.kind)
        self._status.setText("Item not found (stale).")
        self._overview.setPlainText(
            f"ID: {item_ref.id}\nKind: {item_ref.kind}\n\n"
            "This item is no longer present in the active graph."
        )
        self._properties.setRowCount(0)
        self._copy_btn.setEnabled(True)
        self.set_relations_stale(item_ref, can_go_back=self._can_back)
        self.show_activity(
            mode="stale",
            title="Activity",
            items=[{"detail": "Item not found (stale). Go back or select another item."}],
            activate=False,
        )

    def set_content(
        self,
        *,
        item_ref: ItemRef,
        name: str,
        kind: str,
        summary: str,
        properties: dict[str, str],
        stale: bool = False,
    ) -> None:
        self._current_item_id = str(item_ref.id)
        self._title.setText(name)
        self._kind.setText(kind)
        self._status.setText("Item not found (stale)." if stale else "Inspector synced with current selection.")
        self._overview.setPlainText(
            "\n".join(
                [
                    f"Name: {name}",
                    f"Kind: {kind}",
                    f"ID: {item_ref.id}",
                    f"Namespace: {item_ref.namespace or 'n/a'}",
                    "",
                    summary,
                ]
            )
        )
        self._properties.setRowCount(len(properties))
        for row, (key, value) in enumerate(properties.items()):
            self._properties.setItem(row, 0, QtWidgets.QTableWidgetItem(str(key)))
            self._properties.setItem(row, 1, QtWidgets.QTableWidgetItem(str(value)))
        self._copy_btn.setEnabled(True)
        self._set_relations_notice("", show=False)
        self._relations_back_btn.setVisible(False)
        self._set_sections_visible(True)

    def _copy_current_id(self) -> None:
        if not self._current_item_id:
            return
        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._current_item_id)

    def set_relations_provider(self, item_ref: ItemRef, provider: RelationProvider) -> None:
        self._relations_provider = provider
        self._set_relations_notice("", show=False)
        self._relations_back_btn.setVisible(False)
        self._set_sections_visible(True)
        for section in self._relation_sections.values():
            section.setVisible(True)
            section.set_provider(provider, page_size=50)

    def set_relations_empty(self, message: str) -> None:
        self._relations_provider = None
        self._set_relations_notice(message, show=True)
        self._relations_back_btn.setVisible(False)
        self._set_sections_visible(False)
        for section in self._relation_sections.values():
            section.clear_rows("No relations found.")

    def set_relations_stale(self, item_ref: ItemRef, *, can_go_back: bool) -> None:
        self._relations_provider = None
        notice = (
            f"Item not found (stale): {item_ref.id}\n"
            "Go back or select another item."
        )
        self._set_relations_notice(notice, show=True)
        self._relations_back_btn.setVisible(bool(can_go_back))
        self._relations_back_btn.setEnabled(bool(can_go_back))
        self._set_sections_visible(False)
        for section in self._relation_sections.values():
            section.clear_rows("No relations found.")

    def _set_sections_visible(self, visible: bool) -> None:
        self._relations_scroll.setVisible(bool(visible))

    def _set_relations_notice(self, message: str, *, show: bool) -> None:
        self._relations_notice.setText(message.strip())
        self._relations_notice.setVisible(bool(show and message.strip()))

    def select_tab(self, name: str) -> None:
        target = (name or "").strip().lower()
        if target == "relations":
            self._tabs.setCurrentWidget(self._relations_tab)
            return
        if target == "activity":
            self._tabs.setCurrentWidget(self._activity_tab)
            return
        self._tabs.setCurrentWidget(self._overview)

    def show_relations(self, mode: str, title: str, filter_text: str = "", *, activate: bool = True) -> None:
        if activate:
            self.select_tab("relations")
        category_map = {
            "deps": CATEGORY_DEPENDS_ON,
            "packs": CATEGORY_CONTAINS,
            "entry_points": CATEGORY_EXPORTS,
        }
        category = category_map.get((mode or "").strip().lower())
        if category:
            for key, section in self._relation_sections.items():
                section.setVisible(key == category)
                if key == category:
                    section.set_filter_text(filter_text)
            if title:
                self._set_relations_notice(title, show=True)
            else:
                self._set_relations_notice("", show=False)
            return
        for section in self._relation_sections.values():
            section.setVisible(True)
            if filter_text:
                section.set_filter_text(filter_text)
        self._set_relations_notice(title or "", show=bool(title))

    def show_activity(
        self,
        mode: str,
        title: str,
        items: list[dict],
        filter_text: str = "",
        *,
        activate: bool = True,
    ) -> None:
        self._activity_header.setText(f"{title or 'Activity'} ({(mode or 'default').strip()})")
        normalized: list[dict[str, str]] = []
        for raw in items or []:
            normalized.append(
                {
                    "when": str(raw.get("when", "") or ""),
                    "type": str(raw.get("type", "") or ""),
                    "source": str(raw.get("source", "") or ""),
                    "detail": str(raw.get("detail", "") or ""),
                }
            )
        self._activity_items = normalized[-120:]
        blocker = QtCore.QSignalBlocker(self._activity_filter)
        self._activity_filter.setText((filter_text or "").strip())
        del blocker
        self._apply_activity_filter()
        if activate:
            self.select_tab("activity")

    def _apply_activity_filter(self) -> None:
        needle = self._activity_filter.text().strip().lower()
        rows = self._activity_items
        if needle:
            filtered: list[dict[str, str]] = []
            for row in self._activity_items:
                hay = " ".join(
                    [
                        str(row.get("when", "")),
                        str(row.get("type", "")),
                        str(row.get("source", "")),
                        str(row.get("detail", "")),
                    ]
                ).lower()
                if needle in hay:
                    filtered.append(row)
            rows = filtered
        self._activity_table.clear()
        for row in rows:
            item = QtWidgets.QTreeWidgetItem(
                [
                    row.get("when", ""),
                    row.get("type", ""),
                    row.get("source", ""),
                    row.get("detail", ""),
                ]
            )
            self._activity_table.addTopLevelItem(item)
        self._activity_empty.setVisible(len(rows) == 0)
        if len(rows) == 0:
            self._activity_empty.setText("No activity found.")
