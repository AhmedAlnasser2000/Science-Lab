from __future__ import annotations

import json
import math
import time
import traceback
from pathlib import Path
from typing import Callable, Dict

from PyQt6 import QtCore, QtGui, QtWidgets

DEBUG_LOG_PATH = Path(r"c:\Users\ahmed\Downloads\PhysicsLab\.cursor\debug.log")


def _agent_log(payload: Dict[str, object]) -> None:
    # region agent log
    try:
        data = dict(payload)
        data.setdefault("timestamp", int(time.time() * 1000))
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as _log_file:
            _log_file.write(json.dumps(data) + "\n")
    except Exception:
        pass
    # endregion

from .base import LabPlugin
from .renderkit import AssetResolver, AssetCache, RenderCanvas
from .shared import primitives as shared_primitives
from .shared.math2d import Vec2


class ElectricFieldLabPlugin(LabPlugin):
    id = "electric_field"
    title = "Electric Field Lab"

    def create_widget(
        self,
        on_exit: Callable[[], None],
        get_profile: Callable[[], str],
    ) -> "ElectricFieldLabWidget":
        return ElectricFieldLabWidget(on_exit, get_profile)


class ElectricFieldLabWidget(QtWidgets.QWidget):
    def __init__(self, on_exit: Callable[[], None], get_profile: Callable[[], str]):
        super().__init__()
        self.on_exit = on_exit
        self.get_profile = get_profile
        self.profile = get_profile()
        self.reduced_motion = False
        self.resolver = AssetResolver()
        self.cache = AssetCache()

        self.k_const = 8.99e9
        self.charge_c = 1.0
        self.distance_m = 1.0
        self.field_value = 0.0
        self._step_n = 0

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._on_step)
        self.timer.setInterval(600)

        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Electric Field Simulation")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        back_btn = QtWidgets.QPushButton("Back")
        back_btn.clicked.connect(self._handle_back)
        header.addWidget(back_btn)
        layout.addLayout(header)

        controls = QtWidgets.QHBoxLayout()
        self.charge_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.charge_slider.setRange(-10, 10)
        self.charge_slider.setValue(1)
        self.charge_slider.valueChanged.connect(self._update_charge_label)
        self.charge_label = QtWidgets.QLabel("Charge: 1 C")
        controls.addWidget(self.charge_label)
        controls.addWidget(self.charge_slider)

        self.distance_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.distance_slider.setRange(1, 20)
        self.distance_slider.setValue(10)
        self.distance_slider.valueChanged.connect(self._update_distance_label)
        self.distance_label = QtWidgets.QLabel("Distance: 1.0 m")
        controls.addWidget(self.distance_label)
        controls.addWidget(self.distance_slider)
        layout.addLayout(controls)

        buttons = QtWidgets.QHBoxLayout()
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._on_run)
        self.step_btn = QtWidgets.QPushButton("Step")
        self.step_btn.clicked.connect(self._on_step)
        buttons.addWidget(self.run_btn)
        buttons.addWidget(self.step_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.status_label = QtWidgets.QLabel("Field: 0.00 N/C")
        self.status_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.status_label)

        self.canvas = RenderCanvas(self.resolver, self.cache)
        layout.addWidget(self.canvas)

        self._update_field()

    def load_part(self, part_id: str, manifest: Dict, detail: Dict) -> None:
        manifest = manifest or {}
        detail = detail or {}
        behavior = manifest.get("behavior") or {}
        if not isinstance(behavior, dict):
            behavior = {}
        params = behavior.get("parameters") or {}
        if not isinstance(params, dict):
            params = {}
        self.charge_c = float(params.get("charge_c", 1.0))
        self.distance_m = float(params.get("distance_m", 1.0))
        try:
            self.resolver = AssetResolver.from_detail(detail, Path("content_store/physics_v1"))
            self.canvas.resolver = self.resolver
        except Exception:
            pass
        self._sync_sliders()
        self._update_labels()
        self._update_field()

    def set_profile(self, profile: str) -> None:
        self.profile = profile
        self._update_canvas()

    def stop_simulation(self) -> None:
        self.timer.stop()
        self.run_btn.setText("Run")

    def set_reduced_motion(self, value: bool) -> None:
        self.reduced_motion = bool(value)
        self.timer.setInterval(1200 if self.reduced_motion else 600)

    def _handle_back(self) -> None:
        self.stop_simulation()
        self.on_exit()

    def _sync_sliders(self) -> None:
        self.charge_slider.setValue(int(self.charge_c))
        self.distance_slider.setValue(max(1, int(self.distance_m * 10)))

    def _update_labels(self) -> None:
        self.charge_label.setText(f"Charge: {self.charge_c:.1f} C")
        self.distance_label.setText(f"Distance: {self.distance_m:.1f} m")

    def _update_charge_label(self, value: int) -> None:
        self.charge_c = float(value)
        self._update_field()

    def _update_distance_label(self, value: int) -> None:
        self.distance_m = max(0.1, value / 10.0)
        self._update_field()

    def _on_run(self) -> None:
        try:
            if not self.timer.isActive():
                self._step_n += 1
                self._step()
                self.status_label.setText(f"Running... step {self._step_n} | Field: {self.field_value:,.2f} N/C")
                self.canvas.update()
            self._toggle_run()
        except Exception as exc:
            traceback.print_exc()
            self.status_label.setText(f"Error: {exc}")

    def _on_step(self) -> None:
        try:
            self._step_n += 1
            self._step()
            self.status_label.setText(f"Step {self._step_n}: Field {self.field_value:,.2f} N/C")
            self.canvas.update()
        except Exception as exc:
            traceback.print_exc()
            self.status_label.setText(f"Error: {exc}")

    def _toggle_run(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            self.run_btn.setText("Run")
        else:
            self.timer.start()
            self.run_btn.setText("Pause")
        _agent_log(
            {
                "sessionId": "debug-session",
                "runId": "pre-fix",
                "hypothesisId": "H3",
                "location": "electric_field_lab:_toggle_run",
                "message": "run toggled",
                "data": {"active": self.timer.isActive(), "reduced_motion": self.reduced_motion},
            }
        )

    def _step(self) -> None:
        # In reduced motion, keep gentle updates.
        jitter = 0.0 if self.reduced_motion else 0.05
        self.distance_m = max(0.1, self.distance_m + jitter)
        self._update_field()
        _agent_log(
            {
                "sessionId": "debug-session",
                "runId": "pre-fix",
                "hypothesisId": "H4",
                "location": "electric_field_lab:_step",
                "message": "step executed",
                "data": {"distance_m": self.distance_m, "field_value": self.field_value, "jitter": jitter},
            }
        )

    def _update_field(self) -> None:
        self._update_labels()
        r = max(0.1, self.distance_m)
        e_field = self.k_const * self.charge_c / (r * r)
        # Clamp to keep display sane
        if e_field > 1e7:
            e_field = 1e7
        if e_field < -1e7:
            e_field = -1e7
        self.field_value = e_field
        self.status_label.setText(f"Field: {e_field:,.2f} N/C at r={r:.2f} m")
        self._update_canvas()

    def _field_vectors(self) -> list[dict]:
        vectors = []
        spacing = 2.0
        coords = [c * spacing for c in range(-3, 4)]
        for x in coords:
            for y in coords:
                if abs(x) < 0.2 and abs(y) < 0.2:
                    continue
                r2 = x * x + y * y
                r = math.sqrt(r2)
                if r < 1e-3:
                    continue
                base = abs(self.charge_c) / max(0.4, r2)
                length = min(2.4, 0.9 * base + 0.35)
                dir_x = x / r
                dir_y = y / r
                sign = 1.0 if self.charge_c >= 0 else -1.0
                end = (x + sign * dir_x * length, y + sign * dir_y * length)
                color = QtGui.QColor("#7de3ff") if self.charge_c >= 0 else QtGui.QColor("#ffb4a4")
                label = None
                vectors.append({"start": (x, y), "end": end, "color": color, "label": label})
        return vectors

    def _update_canvas(self) -> None:
        world = {"xmin": -8.0, "xmax": 8.0, "ymin": -8.0, "ymax": 8.0}
        show_values = self.profile.lower() in ("educator", "explorer")
        vectors = self._field_vectors()
        samples = []
        if show_values:
            sample_pts = [(-6.0, 0.0), (0.0, 6.0), (6.0, -2.0)]
            for px, py in sample_pts:
                r2 = px * px + py * py
                if r2 < 1e-3:
                    continue
                e_mag = self.k_const * self.charge_c / max(0.1, r2)
                samples.append({"pos": (px, py), "text": f"{e_mag/1e3:.1f}k N/C"})
        scene = {
            "world": world,
            "vectors": vectors,
            "show_values": show_values,
            "samples": samples,
        }
        self.canvas.set_world_bounds(world["xmin"], world["xmax"], world["ymin"], world["ymax"])

        def layer_grid(p: QtGui.QPainter, ctx):
            rect_px = QtCore.QRectF(p.viewport())
            origin = ctx.world_to_screen(QtCore.QPointF(0.0, 0.0))
            step_world = 2.0
            step_px = abs(ctx.world_to_screen(QtCore.QPointF(step_world, 0.0)).x() - origin.x())
            shared_primitives.draw_grid(p, rect_px, step_px=step_px)
            axis_len = min(rect_px.width(), rect_px.height()) / 2.0
            shared_primitives.draw_axes(p, origin, axis_len_px=axis_len)

        def layer_charge(p: QtGui.QPainter, ctx):
            center = ctx.world_to_screen(QtCore.QPointF(0.0, 0.0))
            unit_px = abs(ctx.world_to_screen(QtCore.QPointF(1.0, 0.0)).x() - center.x())
            radius = max(8.0, unit_px * 0.9)
            rect = QtCore.QRectF(
                center.x() - radius,
                center.y() - radius,
                radius * 2,
                radius * 2,
            )
            p.save()
            p.setPen(QtGui.QPen(QtGui.QColor("#9ad2ff"), 2))
            p.setBrush(QtGui.QColor(255, 255, 255, 18))
            p.drawEllipse(rect)
            p.setPen(QtGui.QPen(QtGui.QColor("#9ad2ff"), 2))
            p.drawLine(
                QtCore.QPointF(center.x() - radius * 0.5, center.y()),
                QtCore.QPointF(center.x() + radius * 0.5, center.y()),
            )
            if self.charge_c >= 0:
                p.drawLine(
                    QtCore.QPointF(center.x(), center.y() - radius * 0.5),
                    QtCore.QPointF(center.x(), center.y() + radius * 0.5),
                )
            p.restore()

        def layer_vectors(p: QtGui.QPainter, ctx):
            for vec in vectors:
                start = ctx.world_to_screen(QtCore.QPointF(*vec["start"]))
                end = ctx.world_to_screen(QtCore.QPointF(*vec["end"]))
                shared_primitives.draw_vector(
                    p,
                    start,
                    Vec2(end.x() - start.x(), end.y() - start.y()),
                )

        def layer_samples(p: QtGui.QPainter, ctx):
            if not show_values:
                return
            p.save()
            p.setPen(ctx.palette.color(QtGui.QPalette.ColorRole.Text))
            for sample in samples:
                pos = ctx.world_to_screen(QtCore.QPointF(*sample["pos"]))
                p.drawText(pos + QtCore.QPointF(6, -6), sample["text"])
            p.restore()

        self.canvas.set_layers([layer_grid, layer_charge, layer_vectors, layer_samples])
