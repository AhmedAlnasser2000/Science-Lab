from __future__ import annotations

from typing import Callable, Optional

from PyQt6 import QtCore, QtGui, QtWidgets


class GraphView(QtWidgets.QGraphicsView):
    def __init__(
        self,
        scene: QtWidgets.QGraphicsScene,
        parent=None,
        *,
        on_set_facet_density: Optional[Callable[[str], None]] = None,
        on_set_facet_scope: Optional[Callable[[str], None]] = None,
        on_open_facet_settings: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(scene, parent)
        self._on_set_facet_density = on_set_facet_density
        self._on_set_facet_scope = on_set_facet_scope
        self._on_open_facet_settings = on_open_facet_settings
        self.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing
            | QtGui.QPainter.RenderHint.TextAntialiasing
        )
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self._panning = False
        self._pan_start = QtCore.QPoint()
        self._zoom = 1.0
        self._zoom_min = 0.25
        self._zoom_max = 2.5

    # Pan uses middle-mouse drag to avoid colliding with selection or node dragging.
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        angle = event.angleDelta().y()
        if angle == 0:
            return
        factor = 1.2 if angle > 0 else 1 / 1.2
        next_zoom = self._zoom * factor
        if self._zoom_min <= next_zoom <= self._zoom_max:
            self._zoom = next_zoom
            self.scale(factor, factor)
        event.accept()

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        hit = self.itemAt(event.pos())
        if hit is not None:
            super().contextMenuEvent(event)
            return

        menu = QtWidgets.QMenu(self)
        facets_menu = menu.addMenu("Facets")

        density_options = [
            ("Off", "off"),
            ("Minimal", "minimal"),
            ("Standard", "standard"),
            ("Expanded", "expanded"),
            ("Debug", "debug"),
        ]
        for label, density in density_options:
            action = facets_menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, value=density: self._emit_set_facet_density(value)
            )
        scope_menu = facets_menu.addMenu("Facet scope")
        scope_options = [
            ("Selected only", "selected"),
            ("Peek graph", "peek_graph"),
        ]
        for label, scope in scope_options:
            action = scope_menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, value=scope: self._emit_set_facet_scope(value)
            )
        facets_menu.addSeparator()
        configure = facets_menu.addAction("Configure...")
        configure.triggered.connect(self._emit_open_facet_settings)
        menu.exec(event.globalPos())
        event.accept()

    def _emit_set_facet_density(self, density: str) -> None:
        if self._on_set_facet_density:
            self._on_set_facet_density(density)

    def _emit_set_facet_scope(self, scope: str) -> None:
        if self._on_set_facet_scope:
            self._on_set_facet_scope(scope)

    def _emit_open_facet_settings(self) -> None:
        if self._on_open_facet_settings:
            self._on_open_facet_settings()
