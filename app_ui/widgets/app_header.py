from __future__ import annotations

from typing import Optional

from PyQt6 import QtWidgets

from app_ui import ui_scale

from .workspace_selector import WorkspaceSelector


class AppHeader(QtWidgets.QWidget):
    """Shared header with Back + title + workspace selector."""

    def __init__(
        self,
        *,
        title: str,
        on_back: Optional[callable],
        workspace_selector: Optional[WorkspaceSelector] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._actions_layout = None

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ui_scale.density_spacing(8))
        self._layout = layout

        if on_back:
            back_btn = QtWidgets.QPushButton("Back")
            back_btn.clicked.connect(on_back)
            layout.addWidget(back_btn)

        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)
        layout.addStretch()

        self._actions_layout = QtWidgets.QHBoxLayout()
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(ui_scale.density_spacing(6))
        layout.addLayout(self._actions_layout)

        if workspace_selector:
            self._actions_layout.addWidget(workspace_selector)

        ui_scale.register_listener(self._on_ui_scale_changed)

    def _on_ui_scale_changed(self, cfg: ui_scale.UiScaleConfig) -> None:
        if self._layout:
            self._layout.setSpacing(ui_scale.density_spacing(8))
        if self._actions_layout:
            self._actions_layout.setSpacing(ui_scale.density_spacing(6))

    def add_action_widget(self, widget: QtWidgets.QWidget) -> None:
        """Append a custom action widget before the workspace selector."""
        if not self._actions_layout:
            return
        # Insert before the workspace selector if present (last widget).
        count = self._actions_layout.count()
        insert_pos = max(0, count - 1)
        self._actions_layout.insertWidget(insert_pos, widget)


