from __future__ import annotations

from typing import Callable, Optional

from PyQt6 import QtCore, QtWidgets

from ..item_ref import ItemRef


class CodeSeeInspectorPanel(QtWidgets.QWidget):
    def __init__(
        self,
        *,
        on_back: Callable[[], None],
        on_forward: Callable[[], None],
        on_lock_toggled: Callable[[bool], None],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._current_item_id = ""
        self._on_back = on_back
        self._on_forward = on_forward
        self._on_lock_toggled = on_lock_toggled

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
        self._relations = QtWidgets.QPlainTextEdit()
        self._relations.setReadOnly(True)
        self._relations.setPlainText("Relations view is coming in V5.5d4.")
        tabs.addTab(self._relations, "Relations")
        self._activity = QtWidgets.QPlainTextEdit()
        self._activity.setReadOnly(True)
        self._activity.setPlainText("Activity view is coming in V5.5d5.")
        tabs.addTab(self._activity, "Activity")
        root.addWidget(tabs, stretch=1)

    def set_navigation_state(self, *, can_back: bool, can_forward: bool) -> None:
        self._back_btn.setEnabled(bool(can_back))
        self._forward_btn.setEnabled(bool(can_forward))

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

    def _copy_current_id(self) -> None:
        if not self._current_item_id:
            return
        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._current_item_id)
