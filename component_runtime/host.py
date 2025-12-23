from __future__ import annotations

from typing import Optional

from PyQt6 import QtCore, QtWidgets

from .context import ComponentContext
from .types import Component


class ComponentHost(QtWidgets.QWidget):
    """Mounts a component widget and shields the app from component errors."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._component: Optional[Component] = None
        self._component_widget: Optional[QtWidgets.QWidget] = None
        self._context: Optional[ComponentContext] = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._error_label = QtWidgets.QLabel("")
        self._error_label.setStyleSheet("color: #b00;")
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        self._container = QtWidgets.QWidget()
        self._container_layout = QtWidgets.QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._container, stretch=1)

    def mount(self, component: Component, context: ComponentContext) -> None:
        self.unmount()
        self._context = context
        try:
            widget = component.create_widget(context)
            if not isinstance(widget, QtWidgets.QWidget):
                raise TypeError("Component widget must extend QWidget")
        except Exception as exc:
            self._show_error(f"Failed to open component: {exc}")
            return
        self._component = component
        self._component_widget = widget
        self._container_layout.addWidget(widget)
        self._error_label.setVisible(False)

    def unmount(self) -> None:
        if self._component is not None:
            if hasattr(self._component, "dispose"):
                try:
                    self._component.dispose()
                except Exception:
                    pass
            self._component = None
        if self._component_widget is not None:
            self._container_layout.removeWidget(self._component_widget)
            self._component_widget.deleteLater()
            self._component_widget = None
        self._error_label.setVisible(False)

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def closeEvent(self, event) -> None:
        self.unmount()
        super().closeEvent(event)
