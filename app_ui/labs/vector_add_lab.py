from __future__ import annotations

import math
import random
from typing import Callable, Dict

from PyQt6 import QtCore, QtWidgets

from .base import LabPlugin


class VectorAddLabPlugin(LabPlugin):
    id = "vector_add"
    title = "Vector Addition Lab"

    def create_widget(
        self,
        on_exit: Callable[[], None],
        get_profile: Callable[[], str],
    ) -> "VectorAddLabWidget":
        return VectorAddLabWidget(on_exit, get_profile)


class VectorAddLabWidget(QtWidgets.QWidget):
    def __init__(self, on_exit: Callable[[], None], get_profile: Callable[[], str]):
        super().__init__()
        self.on_exit = on_exit
        self.get_profile = get_profile
        self.profile = get_profile()
        self.reduced_motion = False

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._tick)

        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Vector Addition")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        back_btn = QtWidgets.QPushButton("Back")
        back_btn.clicked.connect(self._handle_back)
        header.addWidget(back_btn)
        layout.addLayout(header)

        grid = QtWidgets.QGridLayout()
        self.a_mag = QtWidgets.QDoubleSpinBox()
        self.a_mag.setRange(0.0, 20.0)
        self.a_mag.setValue(5.0)
        self.a_ang = QtWidgets.QDoubleSpinBox()
        self.a_ang.setRange(-180.0, 180.0)
        self.a_ang.setValue(0.0)
        grid.addWidget(QtWidgets.QLabel("A magnitude"), 0, 0)
        grid.addWidget(self.a_mag, 0, 1)
        grid.addWidget(QtWidgets.QLabel("A angle (deg)"), 0, 2)
        grid.addWidget(self.a_ang, 0, 3)

        self.b_mag = QtWidgets.QDoubleSpinBox()
        self.b_mag.setRange(0.0, 20.0)
        self.b_mag.setValue(5.0)
        self.b_ang = QtWidgets.QDoubleSpinBox()
        self.b_ang.setRange(-180.0, 180.0)
        self.b_ang.setValue(90.0)
        grid.addWidget(QtWidgets.QLabel("B magnitude"), 1, 0)
        grid.addWidget(self.b_mag, 1, 1)
        grid.addWidget(QtWidgets.QLabel("B angle (deg)"), 1, 2)
        grid.addWidget(self.b_ang, 1, 3)
        layout.addLayout(grid)

        buttons = QtWidgets.QHBoxLayout()
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._toggle_run)
        self.step_btn = QtWidgets.QPushButton("Step")
        self.step_btn.clicked.connect(self._step_once)
        buttons.addWidget(self.run_btn)
        buttons.addWidget(self.step_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.result_label = QtWidgets.QLabel("Resultant: pending")
        layout.addWidget(self.result_label)

    def load_part(self, part_id: str, manifest: Dict, detail: Dict) -> None:
        manifest = manifest or {}
        detail = detail or {}
        behavior = manifest.get("behavior") or {}
        if not isinstance(behavior, dict):
            behavior = {}
        params = behavior.get("parameters") or {}
        if not isinstance(params, dict):
            params = {}
        self.a_mag.setValue(float(params.get("a_mag", 5.0)))
        self.a_ang.setValue(float(params.get("a_ang", 0.0)))
        self.b_mag.setValue(float(params.get("b_mag", 5.0)))
        self.b_ang.setValue(float(params.get("b_ang", 90.0)))
        self._step_once()

    def set_profile(self, profile: str) -> None:
        self.profile = profile

    def stop_simulation(self) -> None:
        self.timer.stop()
        self.run_btn.setText("Run")

    def set_reduced_motion(self, value: bool) -> None:
        self.reduced_motion = bool(value)
        self.timer.setInterval(1200 if self.reduced_motion else 500)

    def _handle_back(self) -> None:
        self.stop_simulation()
        self.on_exit()

    def _toggle_run(self) -> None:
        if self.timer.isActive():
            self.stop_simulation()
        else:
            self.timer.start()
            self.run_btn.setText("Pause")

    def _tick(self) -> None:
        if not self.reduced_motion:
            # Small jitter for variety
            for spin in (self.a_ang, self.b_ang):
                spin.setValue(spin.value() + random.uniform(-1.0, 1.0))
        self._step_once()

    def _step_once(self) -> None:
        ax, ay = self._components(self.a_mag.value(), self.a_ang.value())
        bx, by = self._components(self.b_mag.value(), self.b_ang.value())
        rx, ry = ax + bx, ay + by
        mag = math.hypot(rx, ry)
        ang = math.degrees(math.atan2(ry, rx)) if mag > 0 else 0.0
        self.result_label.setText(f"Resultant: {mag:.2f} @ {ang:.1f}° (Rx={rx:.2f}, Ry={ry:.2f})")

    def _components(self, magnitude: float, angle_deg: float) -> tuple[float, float]:
        rad = math.radians(angle_deg)
        return magnitude * math.cos(rad), magnitude * math.sin(rad)
