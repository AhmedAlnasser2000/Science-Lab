from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Dict

import json
from PyQt6 import QtCore, QtGui, QtWidgets

from .base import LabPlugin


CONFIG_PATH = Path("data/roaming/ui_config.json")


def _get_reduced_motion() -> bool:
    if not CONFIG_PATH.exists():
        return False
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return bool(data.get("reduced_motion", False))
    except Exception:
        return False


class ProjectileLabPlugin(LabPlugin):
    id = "projectile"
    title = "Projectile Motion"

    def create_widget(
        self,
        on_exit: Callable[[], None],
        get_profile: Callable[[], str],
    ) -> "ProjectileLabWidget":
        return ProjectileLabWidget(on_exit, get_profile)


class ProjectileLabWidget(QtWidgets.QWidget):
    def __init__(self, on_exit: Callable[[], None], get_profile: Callable[[], str]):
        super().__init__()
        self.on_exit = on_exit
        self.get_profile = get_profile
        self.profile = get_profile()
        self.reduced_motion = _get_reduced_motion()

        self.base_dt = 0.016 if not self.reduced_motion else 0.033
        self.g = 9.81
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(int(self.base_dt * 1000))
        self.timer.timeout.connect(self._tick)

        self.initial_speed = 15.0
        self.initial_angle = 45.0

        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.t = 0.0
        self.trace: list[QtCore.QPointF] = []

        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        self.title_label = QtWidgets.QLabel("Projectile Motion Lab")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.backend_label = QtWidgets.QLabel("")
        back_btn = QtWidgets.QPushButton("Back")
        back_btn.clicked.connect(self._handle_back)
        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.backend_label)
        header.addWidget(back_btn)
        layout.addLayout(header)

        controls = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("Start")
        self.start_button.clicked.connect(self._toggle_timer)
        self.reset_button = QtWidgets.QPushButton("Reset")
        self.reset_button.clicked.connect(self._reset_simulation)
        controls.addWidget(self.start_button)
        controls.addWidget(self.reset_button)

        controls.addWidget(QtWidgets.QLabel("Speed (m/s)"))
        self.speed_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.speed_slider.setRange(5, 40)
        self.speed_slider.setValue(int(self.initial_speed))
        self.speed_slider.valueChanged.connect(self._update_speed_label)
        controls.addWidget(self.speed_slider)
        self.speed_label = QtWidgets.QLabel(f"{self.initial_speed:.0f}")
        controls.addWidget(self.speed_label)

        controls.addWidget(QtWidgets.QLabel("Angle (deg)"))
        self.angle_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.angle_slider.setRange(10, 80)
        self.angle_slider.setValue(int(self.initial_angle))
        self.angle_slider.valueChanged.connect(self._update_angle_label)
        controls.addWidget(self.angle_slider)
        self.angle_label = QtWidgets.QLabel(f"{self.initial_angle:.0f}")
        controls.addWidget(self.angle_label)

        controls.addStretch()
        layout.addLayout(controls)

        self.gravity_box = QtWidgets.QWidget()
        self.gravity_controls = QtWidgets.QHBoxLayout(self.gravity_box)
        self.gravity_controls.setContentsMargins(0, 0, 0, 0)
        self.gravity_controls.addWidget(QtWidgets.QLabel("Gravity (m/s²)"))
        self.gravity_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.gravity_slider.setRange(5, 20)
        self.gravity_slider.setValue(int(self.g))
        self.gravity_slider.valueChanged.connect(self._update_gravity_label)
        self.gravity_controls.addWidget(self.gravity_slider)
        self.gravity_label = QtWidgets.QLabel(f"{self.g:.0f}")
        self.gravity_controls.addWidget(self.gravity_label)
        self.gravity_controls.addStretch()
        layout.addWidget(self.gravity_box)

        info_layout = QtWidgets.QHBoxLayout()
        self.t_label = QtWidgets.QLabel("t: 0.00 s")
        self.x_label = QtWidgets.QLabel("x: 0.00 m")
        self.y_label = QtWidgets.QLabel("y: 0.00 m")
        self.vx_label = QtWidgets.QLabel("vx: 0.00 m/s")
        self.vy_label = QtWidgets.QLabel("vy: 0.00 m/s")
        info_layout.addWidget(self.t_label)
        info_layout.addWidget(self.x_label)
        info_layout.addWidget(self.y_label)
        info_layout.addWidget(self.vx_label)
        info_layout.addWidget(self.vy_label)
        layout.addLayout(info_layout)

        self.canvas = ProjectileCanvas()
        layout.addWidget(self.canvas, stretch=1)

        self.debug_label = QtWidgets.QLabel("")
        layout.addWidget(self.debug_label)

        self._update_profile_controls()
        self._reset_simulation()

    def load_part(self, part_id: str, manifest: Dict, detail: Dict) -> None:
        behavior = manifest.get("behavior") or {}
        params = behavior.get("parameters") or {}
        self.initial_speed = float(params.get("initial_speed_m_s", self.initial_speed))
        self.initial_angle = float(params.get("launch_angle_deg", self.initial_angle))
        self.g = float(params.get("gravity_m_s2", self.g))
        self.speed_slider.setValue(int(self.initial_speed))
        self.angle_slider.setValue(int(self.initial_angle))
        self.gravity_slider.setValue(int(self.g))
        self.title_label.setText(f"Projectile Motion — {part_id}")
        self._reset_simulation()

    def set_profile(self, profile: str) -> None:
        self.profile = profile
        self._update_profile_controls()

    def stop_simulation(self) -> None:
        self.timer.stop()
        self.start_button.setText("Start")

    def _update_profile_controls(self):
        is_learner = self.profile == "Learner"
        reduced = self.reduced_motion
        self.gravity_box.setVisible(self.profile != "Learner")
        self.backend_label.setVisible(self.profile == "Explorer")
        self.debug_label.setVisible(self.profile == "Explorer")
        self.canvas.show_trace = not reduced
        self.timer.setInterval(int((0.033 if reduced else 0.016) * 1000))
        self._update_debug_label()

    def _update_debug_label(self):
        if self.profile == "Explorer":
            self.debug_label.setText(
                f"Debug: dt={self.timer.interval() / 1000:.3f}s | backend=python | reduced_motion={self.reduced_motion}"
            )
        else:
            self.debug_label.clear()

    def _handle_back(self):
        self.stop_simulation()
        self.on_exit()

    def _toggle_timer(self):
        if self.timer.isActive():
            self.timer.stop()
            self.start_button.setText("Start")
        else:
            self.timer.start()
            self.start_button.setText("Pause")

    def _reset_simulation(self):
        self.stop_simulation()
        speed = self.speed_slider.value()
        angle = math.radians(self.angle_slider.value())
        self.g = float(self.gravity_slider.value())
        self.x = 0.0
        self.y = 0.0
        self.vx = speed * math.cos(angle)
        self.vy = speed * math.sin(angle)
        self.t = 0.0
        self.trace.clear()
        self._update_state()
        self.canvas.set_scene(
            max_distance=30.0,
            max_height=max(10.0, (speed ** 2) * (math.sin(2 * angle)) / max(self.g, 0.1) + 2),
        )
        self.canvas.set_position(self.x, self.y, self.trace)

    def _update_speed_label(self):
        self.speed_label.setText(f"{self.speed_slider.value():.0f}")

    def _update_angle_label(self):
        self.angle_label.setText(f"{self.angle_slider.value():.0f}")

    def _update_gravity_label(self):
        self.gravity_label.setText(f"{self.gravity_slider.value():.0f}")

    def _tick(self):
        dt = self.timer.interval() / 1000.0
        self.t += dt
        self.x += self.vx * dt
        self.vy -= self.g * dt
        self.y += self.vy * dt
        if self.y < 0.0:
            self.y = 0.0
            self.vy = 0.0
            self.timer.stop()
            self.start_button.setText("Start")
        if not self.reduced_motion:
            self.trace.append(QtCore.QPointF(self.x, self.y))
        self.canvas.set_position(self.x, self.y, self.trace)
        self._update_state()

    def _update_state(self):
        self.t_label.setText(f"t: {self.t:.2f} s")
        self.x_label.setText(f"x: {self.x:.2f} m")
        self.y_label.setText(f"y: {self.y:.2f} m")
        self.vx_label.setText(f"vx: {self.vx:.2f} m/s")
        self.vy_label.setText(f"vy: {self.vy:.2f} m/s")


class ProjectileCanvas(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 300)
        self.max_distance = 30.0
        self.max_height = 10.0
        self.x = 0.0
        self.y = 0.0
        self.trace = []
        self.show_trace = True

    def set_scene(self, max_distance: float, max_height: float):
        self.max_distance = max(5.0, max_distance)
        self.max_height = max(5.0, max_height)

    def set_position(self, x: float, y: float, trace):
        self.x = x
        self.y = y
        self.trace = list(trace)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#031128"))
        ground_y = self.height() - 40
        painter.setPen(QtGui.QPen(QtGui.QColor("#1f3d6d"), 2))
        painter.drawLine(40, ground_y, self.width() - 20, ground_y)

        def map_point(px, py):
            usable_width = max(self.width() - 80, 1)
            usable_height = max(ground_y - 40, 1)
            nx = min(max(px / self.max_distance, 0.0), 1.0)
            ny = min(max(py / self.max_height, 0.0), 1.0)
            return QtCore.QPointF(40 + nx * usable_width, ground_y - ny * usable_height)

        if self.show_trace and self.trace:
            painter.setPen(QtGui.QPen(QtGui.QColor("#4bc0c8"), 2))
            poly = QtGui.QPolygonF([map_point(p.x(), p.y()) for p in self.trace])
            painter.drawPolyline(poly)

        ball = map_point(self.x, self.y)
        ball_rect = QtCore.QRectF(ball.x() - 8, ball.y() - 8, 16, 16)
        painter.setBrush(QtGui.QColor("#f5b400"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#ffe599"), 2))
        painter.drawEllipse(ball_rect)
