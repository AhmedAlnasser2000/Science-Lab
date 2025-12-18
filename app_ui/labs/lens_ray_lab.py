from __future__ import annotations

import math
from typing import Callable, Dict

from PyQt6 import QtCore, QtGui, QtWidgets

from .base import LabPlugin
from ._viz_canvas import VizCanvas


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
        self.n1 = 1.5
        self.n2 = 1.0

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

        grid.addWidget(QtWidgets.QLabel("n1 (incident)"), 3, 0)
        self.n1_spin = QtWidgets.QDoubleSpinBox()
        self.n1_spin.setRange(1.0, 2.5)
        self.n1_spin.setSingleStep(0.05)
        self.n1_spin.setValue(self.n1)
        self.n1_spin.valueChanged.connect(self._update_params)
        grid.addWidget(self.n1_spin, 3, 1)

        grid.addWidget(QtWidgets.QLabel("n2 (transmit)"), 4, 0)
        self.n2_spin = QtWidgets.QDoubleSpinBox()
        self.n2_spin.setRange(1.0, 2.5)
        self.n2_spin.setSingleStep(0.05)
        self.n2_spin.setValue(self.n2)
        self.n2_spin.valueChanged.connect(self._update_params)
        grid.addWidget(self.n2_spin, 4, 1)
        layout.addLayout(grid)

        self.canvas = VizCanvas()
        self.canvas.setMinimumHeight(320)
        layout.addWidget(self.canvas)

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
        self.n1 = float(params.get("n1", self.n1))
        self.n2 = float(params.get("n2", self.n2))
        self._sync_controls()
        self._update_status("Loaded lens parameters.")
        self._step()

    def set_profile(self, profile: str) -> None:
        self.profile = profile
        self._step()

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
        self.n1_spin.setValue(self.n1)
        self.n2_spin.setValue(self.n2)

    def _update_params(self) -> None:
        self.focal_length = self.focal_spin.value()
        self.object_distance = self.object_spin.value()
        self.input_angle_deg = self.angle_spin.value()
        self.n1 = self.n1_spin.value()
        self.n2 = self.n2_spin.value()
        self._step()

    def _toggle_run(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            self.run_btn.setText("Run")
        else:
            self.timer.start()
            self.run_btn.setText("Pause")

    def _step(self) -> None:
        angle_rad = math.radians(self.input_angle_deg)
        dir_inc = (math.sin(angle_rad), math.cos(angle_rad))
        inc_start = (-dir_inc[0] * 8.0, -dir_inc[1] * 8.0)
        world = {"xmin": -12.0, "xmax": 12.0, "ymin": -8.0, "ymax": 8.0}

        tir = False
        theta_t_deg = None
        refracted_end = None
        if self.n2 <= 0:
            self._update_status("n2 must be > 0")
            return

        sin_t = (self.n1 * math.sin(angle_rad)) / self.n2
        if abs(sin_t) > 1.0:
            tir = True
            dir_out = (dir_inc[0], -dir_inc[1])
            refracted_end = (dir_out[0] * 8.0, dir_out[1] * 8.0)
            self._update_status("Total internal reflection")
        else:
            theta_t_rad = math.asin(sin_t)
            theta_t_deg = math.degrees(theta_t_rad)
            dir_out = (math.sin(theta_t_rad), math.cos(theta_t_rad))
            refracted_end = (dir_out[0] * 9.0, dir_out[1] * 9.0)
            self._update_status(f"θt = {theta_t_deg:.1f}° (Snell)")

        scene = {
            "kind": "lens",
            "world": world,
            "boundary": {"y": 0.0},
            "normal": {"x": 0.0},
            "incident": {"start": inc_start, "end": (0.0, 0.0), "label": "θi"},
            "overlays": {
                "theta_i": abs(self.input_angle_deg),
                "theta_t": theta_t_deg,
                "tir": tir,
                "n1": self.n1,
                "n2": self.n2,
                "profile": self.profile,
            },
        }
        if tir:
            scene["reflected"] = {"start": (0.0, 0.0), "end": refracted_end, "label": "reflect"}
        else:
            scene["refracted"] = {"start": (0.0, 0.0), "end": refracted_end, "label": "θt"}

        self.canvas.set_scene_data(scene)

    def _update_status(self, text: str) -> None:
        self.status_label.setText(text)
