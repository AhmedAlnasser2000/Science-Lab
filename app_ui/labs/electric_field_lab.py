from __future__ import annotations

import math
from typing import Callable, Dict

from PyQt6 import QtCore, QtGui, QtWidgets

from .base import LabPlugin
from ._viz_canvas import VizCanvas


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

        self.k_const = 8.99e9
        self.charge_c = 1.0
        self.distance_m = 1.0
        self.field_value = 0.0

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._step)
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
        self.run_btn.clicked.connect(self._toggle_run)
        self.step_btn = QtWidgets.QPushButton("Step")
        self.step_btn.clicked.connect(self._step)
        buttons.addWidget(self.run_btn)
        buttons.addWidget(self.step_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.status_label = QtWidgets.QLabel("Field: 0.00 N/C")
        self.status_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.status_label)

        self.canvas = VizCanvas()
        self.canvas.setMinimumHeight(320)
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

    def _toggle_run(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            self.run_btn.setText("Run")
        else:
            self.timer.start()
            self.run_btn.setText("Pause")

    def _step(self) -> None:
        # In reduced motion, keep gentle updates.
        jitter = 0.0 if self.reduced_motion else 0.05
        self.distance_m = max(0.1, self.distance_m + jitter)
        self._update_field()

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
            "kind": "field",
            "world": world,
            "vectors": vectors,
            "show_values": show_values,
            "samples": samples,
        }
        self.canvas.set_scene_data(scene)
