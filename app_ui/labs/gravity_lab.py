from __future__ import annotations

from typing import Callable, Dict, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from .. import config as ui_config
from .. import kernel_bridge
from .base import LabPlugin


class GravityLabPlugin(LabPlugin):
    id = "gravity"
    title = "Gravity Lab"

    def create_widget(
        self,
        on_exit: Callable[[], None],
        get_profile: Callable[[], str],
    ) -> "GravityLabWidget":
        return GravityLabWidget(on_exit, get_profile)


class GravityLabWidget(QtWidgets.QWidget):
    def __init__(self, on_exit: Callable[[], None], get_profile: Callable[[], str]):
        super().__init__()
        self.on_exit = on_exit
        self.get_profile = get_profile
        self.backend = None
        self.backend_name = "python-fallback"
        self.base_dt = 0.016
        self.reduced_motion = ui_config.get_reduced_motion()
        self.g = 9.81
        self.initial_height = 10.0
        self.initial_vy = 0.0
        self.part_id = ""
        self.profile = get_profile()

        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        self.title_label = QtWidgets.QLabel("Gravity Simulation")
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

        self.dt_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.dt_slider.setRange(5, 40)
        self.dt_slider.setValue(16)
        self.dt_slider.valueChanged.connect(self._update_dt_label)
        self.dt_label = QtWidgets.QLabel("dt: 0.016s")
        controls.addWidget(self.dt_slider)
        controls.addWidget(self.dt_label)
        controls.addStretch()
        layout.addLayout(controls)

        info_layout = QtWidgets.QHBoxLayout()
        self.t_label = QtWidgets.QLabel("t: 0.00 s")
        self.y_label = QtWidgets.QLabel("y: 0.00 m")
        self.v_label = QtWidgets.QLabel("vy: 0.00 m/s")
        info_layout.addWidget(self.t_label)
        info_layout.addWidget(self.y_label)
        info_layout.addWidget(self.v_label)
        layout.addLayout(info_layout)

        self.canvas = SimulationCanvas()
        layout.addWidget(self.canvas, stretch=1)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.set_reduced_motion(self.reduced_motion)

    def load_part(self, part_id: str, manifest: Dict, detail: Dict) -> None:
        self.stop_simulation()
        behavior = manifest.get("behavior") or {}
        params = behavior.get("parameters") or {}
        self.initial_height = float(params.get("initial_height_m", 10.0))
        self.initial_vy = float(params.get("initial_vy_m_s", 0.0))
        self.g = float(params.get("gravity_m_s2", 9.81))
        self.part_id = part_id
        self.title_label.setText(f"Gravity Simulation — {part_id}")
        self.canvas.set_limits(max(self.initial_height * 1.2, 5.0))
        self._init_backend()
        self._reset_simulation()
        self.set_profile(self.get_profile())

    def set_profile(self, profile: str) -> None:
        self.profile = profile
        is_learner = profile == "Learner"
        self.dt_slider.setVisible(not is_learner)
        self.dt_label.setVisible(not is_learner)
        self.backend_label.setVisible(profile == "Explorer")

    def set_reduced_motion(self, value: bool) -> None:
        self.reduced_motion = bool(value)
        self.base_dt = 0.033 if self.reduced_motion else 0.016
        self.timer.setInterval(self._timer_interval_ms())
        self._update_dt_label()

    def stop_simulation(self) -> None:
        self.timer.stop()
        self.start_button.setText("Start")

    def _update_dt_label(self) -> None:
        self.dt_label.setText(f"dt: {self._current_dt():.3f}s")

    def _handle_back(self) -> None:
        self.stop_simulation()
        if self.backend:
            self.backend.close()
            self.backend = None
        self.on_exit()

    def _toggle_timer(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            self.start_button.setText("Start")
        else:
            self.timer.start()
            self.start_button.setText("Pause")

    def _reset_simulation(self) -> None:
        if self.backend:
            self.backend.reset(self.initial_height, self.initial_vy)
            t, y, vy = self.backend.get_state()
            self._update_state(t, y, vy)
        self.canvas.set_height(self.initial_height)

    def _init_backend(self) -> None:
        if self.backend:
            self.backend.close()
        try:
            self.backend = KernelGravityBackend(self.initial_height, self.initial_vy)
            self.backend_name = "kernel"
            self.backend_label.setToolTip("Rust kernel backend active.")
        except kernel_bridge.KernelNotAvailable as exc:
            kernel_bridge.log_kernel_fallback_once(exc)
            self.backend = PythonGravityBackend(self.g, self.initial_height, self.initial_vy)
            self.backend_name = "python-fallback"
            self.backend_label.setToolTip("Rust kernel not available; using Python fallback.")
        except Exception as exc:
            print(f"Simulation fallback: {exc}")
            self.backend = PythonGravityBackend(self.g, self.initial_height, self.initial_vy)
            self.backend_name = "python-fallback"
            self.backend_label.setToolTip("Kernel init failed; using Python fallback.")
        self.backend_label.setText(f"Backend: {self.backend_name}")

    def _current_dt(self) -> float:
        if self.profile == "Learner":
            return self.base_dt
        return max(0.001, self.dt_slider.value() / 1000.0)

    def _timer_interval_ms(self) -> int:
        return 33 if self.reduced_motion else 16

    def _tick(self) -> None:
        if not self.backend:
            return
        dt = self._current_dt()
        try:
            self.backend.step(dt)
            t, y, vy = self.backend.get_state()
        except Exception as exc:
            self.timer.stop()
            QtWidgets.QMessageBox.warning(self, "Simulation", f"Simulation error: {exc}")
            return
        y_display = max(0.0, y)
        if y <= 0.0 and vy < 0:
            vy = 0.0
        self._update_state(t, y_display, vy)
        self.canvas.set_height(y_display)

    def _update_state(self, t: float, y: float, vy: float) -> None:
        self.t_label.setText(f"t: {t:.2f} s")
        self.y_label.setText(f"y: {y:.2f} m")
        self.v_label.setText(f"vy: {vy:.2f} m/s")


class KernelGravityBackend:
    def __init__(self, y0: float, vy0: float):
        self.session = kernel_bridge.create_gravity_session(y0, vy0)

    def reset(self, y0: float, vy0: float):
        self.session.reset(y0, vy0)

    def step(self, dt: float):
        self.session.step(dt)

    def get_state(self) -> Tuple[float, float, float]:
        return self.session.get_state()

    def close(self):
        self.session.close()


class PythonGravityBackend:
    def __init__(self, g: float, y0: float, vy0: float):
        self.g = g
        self.reset(y0, vy0)

    def reset(self, y0: float, vy0: float):
        self.t = 0.0
        self.y = y0
        self.vy = vy0

    def step(self, dt: float):
        self.vy -= self.g * dt
        self.y += self.vy * dt
        self.t += dt

    def get_state(self) -> Tuple[float, float, float]:
        return self.t, self.y, self.vy

    def close(self):
        pass


class SimulationCanvas(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 300)
        self.max_height = 10.0
        self.current_height = 10.0

    def set_limits(self, max_height: float):
        self.max_height = max(1.0, max_height)

    def set_height(self, height: float):
        self.current_height = max(0.0, height)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#0d1a2d"))

        ground_y = self.height() - 40
        painter.setPen(QtGui.QPen(QtGui.QColor("#3a4f85"), 2))
        painter.drawLine(40, ground_y, self.width() - 40, ground_y)

        usable_height = max(ground_y - 40, 1)
        normalized = min(self.current_height / self.max_height, 1.0)
        ball_y = ground_y - normalized * usable_height
        ball_rect = QtCore.QRectF(0, 0, 30, 30)
        ball_rect.moveCenter(QtCore.QPointF(self.width() / 2, ball_y))
        painter.setBrush(QtGui.QColor("#5a74d3"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#94a9ff"), 2))
        painter.drawEllipse(ball_rect)
