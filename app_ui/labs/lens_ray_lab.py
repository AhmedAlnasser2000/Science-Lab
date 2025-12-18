from __future__ import annotations

import math
from typing import Callable, Dict

from PyQt6 import QtCore, QtWidgets

from .base import LabPlugin


class LensRayLabPlugin(LabPlugin):
    id = "lens_ray"
    title = "Lens Ray Lab"

    def create_widget(
        self,
        on_exit: Callable[[], None],
        get_profile: Callable[[], str],
    ) -> "LensRayLabWidget":
        return LensRayLabWidget(on_exit, get_profile)


class LensRayLabWidget(QtWidgets.QWidget):
    def __init__(self, on_exit: Callable[[], None], get_profile: Callable[[], str]):
        super().__init__()
        self.on_exit = on_exit
        self.get_profile = get_profile
        self.profile = get_profile()
        self.reduced_motion = False

        self.focal_length = 10.0
        self.object_distance = 25.0
        self.input_angle_deg = 5.0

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(700)
        self.timer.timeout.connect(self._step)

        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Lens Ray Simulation")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        back_btn = QtWidgets.QPushButton("Back")
        back_btn.clicked.connect(self._handle_back)
        header.addWidget(back_btn)
        layout.addLayout(header)

        grid = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel("Focal length (cm)"), 0, 0)
        self.focal_spin = QtWidgets.QDoubleSpinBox()
        self.focal_spin.setRange(-50.0, 50.0)
        self.focal_spin.setSingleStep(1.0)
        self.focal_spin.setValue(self.focal_length)
        self.focal_spin.valueChanged.connect(self._update_params)
        grid.addWidget(self.focal_spin, 0, 1)

        grid.addWidget(QtWidgets.QLabel("Object distance (cm)"), 1, 0)
        self.object_spin = QtWidgets.QDoubleSpinBox()
        self.object_spin.setRange(1.0, 200.0)
        self.object_spin.setValue(self.object_distance)
        self.object_spin.valueChanged.connect(self._update_params)
        grid.addWidget(self.object_spin, 1, 1)

        grid.addWidget(QtWidgets.QLabel("Ray angle (deg)"), 2, 0)
        self.angle_spin = QtWidgets.QDoubleSpinBox()
        self.angle_spin.setRange(-45.0, 45.0)
        self.angle_spin.setSingleStep(1.0)
        self.angle_spin.setValue(self.input_angle_deg)
        self.angle_spin.valueChanged.connect(self._update_params)
        grid.addWidget(self.angle_spin, 2, 1)
        layout.addLayout(grid)

        buttons = QtWidgets.QHBoxLayout()
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._toggle_run)
        self.step_btn = QtWidgets.QPushButton("Step")
        self.step_btn.clicked.connect(self._step)
        buttons.addWidget(self.run_btn)
        buttons.addWidget(self.step_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.status_label)

    def load_part(self, part_id: str, manifest: Dict, detail: Dict) -> None:
        manifest = manifest or {}
        detail = detail or {}
        behavior = manifest.get("behavior") or {}
        if not isinstance(behavior, dict):
            behavior = {}
        params = behavior.get("parameters") or {}
        if not isinstance(params, dict):
            params = {}
        self.focal_length = float(params.get("focal_length_cm", self.focal_length))
        self.object_distance = float(params.get("object_distance_cm", self.object_distance))
        self.input_angle_deg = float(params.get("input_angle_deg", self.input_angle_deg))
        self._sync_controls()
        self._update_status("Loaded lens parameters.")

    def set_profile(self, profile: str) -> None:
        self.profile = profile

    def stop_simulation(self) -> None:
        self.timer.stop()
        self.run_btn.setText("Run")

    def set_reduced_motion(self, value: bool) -> None:
        self.reduced_motion = bool(value)
        self.timer.setInterval(1400 if self.reduced_motion else 700)

    def _handle_back(self) -> None:
        self.stop_simulation()
        self.on_exit()

    def _sync_controls(self) -> None:
        self.focal_spin.setValue(self.focal_length)
        self.object_spin.setValue(self.object_distance)
        self.angle_spin.setValue(self.input_angle_deg)

    def _update_params(self) -> None:
        self.focal_length = self.focal_spin.value()
        self.object_distance = self.object_spin.value()
        self.input_angle_deg = self.angle_spin.value()

    def _toggle_run(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            self.run_btn.setText("Run")
        else:
            self.timer.start()
            self.run_btn.setText("Pause")

    def _step(self) -> None:
        self._update_params()
        angle_rad = math.radians(self.input_angle_deg)
        # Thin lens approximation for image distance
        try:
            inv_image = (1.0 / self.focal_length) - (1.0 / self.object_distance)
            image_distance = math.inf if inv_image == 0 else 1.0 / inv_image
        except ZeroDivisionError:
            image_distance = math.inf
        hit_height = math.tan(angle_rad) * (self.object_distance if math.isfinite(image_distance) else 0)
        desc = "Diverging" if self.focal_length < 0 else "Converging"
        self._update_status(
            f"{desc} lens | image at {image_distance:.1f} cm | ray height {hit_height:.2f} cm"
        )

    def _update_status(self, text: str) -> None:
        self.status_label.setText(text)
