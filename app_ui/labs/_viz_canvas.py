from __future__ import annotations

import math
from typing import Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from .shared.viewport import ViewTransform, nice_step

class VizCanvas(QtWidgets.QWidget):
    """Lightweight QPainter canvas for the lab visualizations."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.scene_data: Dict = {}
        self.padding = 28
        self._view = ViewTransform(padding_px=self.padding)
        self._world: Dict = {}
        self.setMinimumHeight(320)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

    def set_scene_data(self, scene: Optional[Dict]) -> None:
        """Store scene description and request a repaint."""
        self.scene_data = scene or {}
        self.update()

    # ---- Utilities -----------------------------------------------------
    def world_to_screen(self, x: float, y: float) -> QtCore.QPointF:
        if not self._view:
            return QtCore.QPointF(self.width() * 0.5, self.height() * 0.5)
        return self._view.world_to_screen(QtCore.QPointF(x, y))

    def draw_arrow(
        self,
        painter: QtGui.QPainter,
        start: QtCore.QPointF,
        end: QtCore.QPointF,
        color: QtGui.QColor,
        width: float = 2.0,
        label: Optional[str] = None,
    ) -> None:
        painter.save()
        painter.setPen(QtGui.QPen(color, width))
        painter.drawLine(start, end)

        vec = end - start
        length = math.hypot(vec.x(), vec.y())
        if length > 1e-3:
            head_len = min(14.0, 0.18 * length + 6.0)
            head_width = head_len * 0.6
            direction = QtCore.QPointF(vec.x() / length, vec.y() / length)
            back = end - direction * head_len
            left = QtCore.QPointF(-direction.y() * head_width, direction.x() * head_width)
            right = -left
            head = QtGui.QPolygonF([end, back + left, back + right])
            painter.setBrush(color)
            painter.drawPolygon(head)

        if label:
            offset = QtCore.QPointF(8.0, -8.0)
            label_pos = end + offset
            self.draw_text_box(painter, label, label_pos)
        painter.restore()

    def draw_text_box(
        self,
        painter: QtGui.QPainter,
        text: str,
        pos: QtCore.QPointF,
        padding: int = 4,
        bg: QtGui.QColor = QtGui.QColor(12, 14, 22, 200),
    ) -> None:
        painter.save()
        metrics = painter.fontMetrics()
        rect = metrics.boundingRect(text)
        rect.adjust(-padding, -padding, padding, padding)
        rect.moveTo(int(pos.x()), int(pos.y()))
        painter.setBrush(bg)
        painter.setPen(QtGui.QColor(230, 234, 246))
        painter.drawRoundedRect(rect, 4, 4)
        painter.drawText(
            rect,
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        painter.restore()

    # ---- Drawing helpers ----------------------------------------------
    def _prep_transform(self) -> Dict:
        world = self.scene_data.get("world") or {
            "xmin": -10.0,
            "xmax": 10.0,
            "ymin": -10.0,
            "ymax": 10.0,
        }
        self._view.padding_px = self.padding
        self._view.set_world_bounds(
            world["xmin"],
            world["xmax"],
            world["ymin"],
            world["ymax"],
        )
        self._view.fit(self.width(), self.height())
        self._world = world
        return {"world": world}

    def _draw_grid_and_axes(self, painter: QtGui.QPainter, world: Dict) -> None:
        painter.save()
        grid_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 22))
        grid_pen.setWidthF(1.0)
        painter.setPen(grid_pen)
        step = nice_step(max(world["xmax"] - world["xmin"], world["ymax"] - world["ymin"]))

        x = math.ceil(world["xmin"] / step) * step
        while x <= world["xmax"]:
            p1 = self.world_to_screen(x, world["ymin"])
            p2 = self.world_to_screen(x, world["ymax"])
            painter.drawLine(p1, p2)
            x += step

        y = math.ceil(world["ymin"] / step) * step
        while y <= world["ymax"]:
            p1 = self.world_to_screen(world["xmin"], y)
            p2 = self.world_to_screen(world["xmax"], y)
            painter.drawLine(p1, p2)
            y += step

        axis_pen = QtGui.QPen(QtGui.QColor(120, 132, 168), 2)
        painter.setPen(axis_pen)
        painter.drawLine(
            self.world_to_screen(world["xmin"], 0),
            self.world_to_screen(world["xmax"], 0),
        )
        painter.drawLine(
            self.world_to_screen(0, world["ymin"]),
            self.world_to_screen(0, world["ymax"]),
        )
        painter.restore()

    # ---- Scene drawers -------------------------------------------------
    def _draw_vector_scene(self, painter: QtGui.QPainter) -> None:
        vectors = self.scene_data.get("vectors") or []
        for vec in vectors:
            start = vec.get("start", (0, 0))
            end = vec.get("end", (0, 0))
            color = vec.get("color") or QtGui.QColor("#5dc2f3")
            label = vec.get("label")
            self.draw_arrow(
                painter,
                self.world_to_screen(*start),
                self.world_to_screen(*end),
                color,
                width=vec.get("width", 2.0),
                label=label,
            )

    def _draw_lens_scene(self, painter: QtGui.QPainter) -> None:
        boundary = self.scene_data.get("boundary") or {"y": 0.0}
        normal = self.scene_data.get("normal") or {"x": 0.0}
        painter.save()
        painter.setPen(QtGui.QPen(QtGui.QColor("#6f7ba5"), 2))
        painter.drawLine(
            self.world_to_screen(self.scene_data["world"]["xmin"], boundary["y"]),
            self.world_to_screen(self.scene_data["world"]["xmax"], boundary["y"]),
        )
        painter.setPen(QtGui.QPen(QtGui.QColor("#9099c4"), 1, QtCore.Qt.PenStyle.DashLine))
        painter.drawLine(
            self.world_to_screen(normal["x"], self.scene_data["world"]["ymin"]),
            self.world_to_screen(normal["x"], self.scene_data["world"]["ymax"]),
        )
        painter.restore()

        incident = self.scene_data.get("incident")
        if incident:
            self.draw_arrow(
                painter,
                self.world_to_screen(*incident.get("start", (0, 0))),
                self.world_to_screen(*incident.get("end", (0, 0))),
                QtGui.QColor("#6be6ff"),
                width=2.5,
                label=incident.get("label"),
            )

        if self.scene_data.get("refracted"):
            refracted = self.scene_data["refracted"]
            self.draw_arrow(
                painter,
                self.world_to_screen(*refracted.get("start", (0, 0))),
                self.world_to_screen(*refracted.get("end", (0, 0))),
                QtGui.QColor("#9cf28a"),
                width=2.4,
                label=refracted.get("label"),
            )
        if self.scene_data.get("reflected"):
            reflected = self.scene_data["reflected"]
            self.draw_arrow(
                painter,
                self.world_to_screen(*reflected.get("start", (0, 0))),
                self.world_to_screen(*reflected.get("end", (0, 0))),
                QtGui.QColor("#ffb347"),
                width=2.4,
                label=reflected.get("label"),
            )

        overlays = self.scene_data.get("overlays") or {}
        profile = str(overlays.get("profile") or "").lower()
        show_extra = profile in ("educator", "explorer")
        base_pos = self.world_to_screen(
            0.6 * self.scene_data["world"]["xmax"],
            0.75 * self.scene_data["world"]["ymax"],
        )
        theta_i = overlays.get("theta_i")
        theta_t = overlays.get("theta_t")
        tir = overlays.get("tir")
        if theta_i is not None:
            self.draw_text_box(painter, f"θi = {theta_i:.1f}°", base_pos)
        if tir:
            self.draw_text_box(painter, "TIR", base_pos + QtCore.QPointF(0, 26))
        elif theta_t is not None:
            self.draw_text_box(painter, f"θt = {theta_t:.1f}°", base_pos + QtCore.QPointF(0, 26))
        if show_extra:
            n1 = overlays.get("n1")
            n2 = overlays.get("n2")
            if n1:
                self.draw_text_box(
                    painter,
                    f"n1 = {n1:.2f}",
                    base_pos + QtCore.QPointF(-120, 0),
                )
            if n2:
                self.draw_text_box(
                    painter,
                    f"n2 = {n2:.2f}",
                    base_pos + QtCore.QPointF(-120, 26),
                )

    def _draw_field_scene(self, painter: QtGui.QPainter) -> None:
        vectors = self.scene_data.get("vectors") or []
        show_values = self.scene_data.get("show_values", False)
        for vec in vectors:
            start = self.world_to_screen(*vec["start"])
            end = self.world_to_screen(*vec["end"])
            color = vec.get("color") or QtGui.QColor("#7de3ff")
            self.draw_arrow(painter, start, end, color, width=1.8)
            if show_values and vec.get("label"):
                self.draw_text_box(painter, vec["label"], end + QtCore.QPointF(4, -4))

        if self.scene_data.get("samples"):
            for sample in self.scene_data["samples"]:
                pos = self.world_to_screen(*sample["pos"])
                self.draw_text_box(painter, sample["text"], pos + QtCore.QPointF(6, -6))

    # ---- QWidget -------------------------------------------------------
    def paintEvent(self, _: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor("#0d1021"))

        self._prep_transform()
        world = self._world
        self._draw_grid_and_axes(painter, world)

        kind = self.scene_data.get("kind") or self.scene_data.get("type")
        if kind == "lens":
            self._draw_lens_scene(painter)
        elif kind == "field":
            self._draw_field_scene(painter)
        else:
            self._draw_vector_scene(painter)
