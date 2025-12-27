from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets


class GraphView(QtWidgets.QGraphicsView):
    def __init__(self, scene: QtWidgets.QGraphicsScene, parent=None) -> None:
        super().__init__(scene, parent)
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
