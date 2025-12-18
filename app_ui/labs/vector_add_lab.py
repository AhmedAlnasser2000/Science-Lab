from __future__ import annotations

import json
import math
import random
import time
import traceback
from typing import Callable, Dict

from pathlib import Path

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
from .renderkit import AssetResolver, AssetCache, RenderCanvas, primitives


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
        self.resolver = AssetResolver()
        self.cache = AssetCache()
        self._step_n = 0

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._on_step)

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

        self.canvas = RenderCanvas(self.resolver, self.cache)
        layout.addWidget(self.canvas)

        buttons = QtWidgets.QHBoxLayout()
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._on_run)
        self.step_btn = QtWidgets.QPushButton("Step")
        self.step_btn.clicked.connect(self._on_step)
        buttons.addWidget(self.run_btn)
        buttons.addWidget(self.step_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.result_label = QtWidgets.QLabel("Resultant: pending")
        layout.addWidget(self.result_label)

        for spin in (self.a_mag, self.a_ang, self.b_mag, self.b_ang):
            spin.valueChanged.connect(self._on_step)
        initial = self._step_once()
        self._set_result_text(initial, prefix="Resultant")

    def load_part(self, part_id: str, manifest: Dict, detail: Dict) -> None:
        manifest = manifest or {}
        detail = detail or {}
        behavior = manifest.get("behavior") or {}
        if not isinstance(behavior, dict):
            behavior = {}
        params = behavior.get("parameters") or {}
        if not isinstance(params, dict):
            params = {}
        try:
            self.resolver = AssetResolver.from_detail(detail, Path("content_store/physics_v1"))
            self.canvas.resolver = self.resolver
        except Exception:
            pass
        self.a_mag.setValue(float(params.get("a_mag", 5.0)))
        self.a_ang.setValue(float(params.get("a_ang", 0.0)))
        self.b_mag.setValue(float(params.get("b_mag", 5.0)))
        self.b_ang.setValue(float(params.get("b_ang", 90.0)))
        result = self._step_once()
        self._set_result_text(result, prefix="Resultant")

    def set_profile(self, profile: str) -> None:
        self.profile = profile
        result = self._step_once()
        self._set_result_text(result, prefix="Resultant")

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
        _agent_log(
            {
                "sessionId": "debug-session",
                "runId": "pre-fix",
                "hypothesisId": "H3",
                "location": "vector_add_lab:_toggle_run",
                "message": "run toggled",
                "data": {"active": self.timer.isActive(), "reduced_motion": self.reduced_motion},
            }
        )

    def _on_run(self) -> None:
        try:
            if not self.timer.isActive():
                self._step_n += 1
                result = self._step_once()
                self._set_result_text(result, prefix=f"Running step {self._step_n}")
                self.canvas.update()
            self._toggle_run()
        except Exception as exc:
            traceback.print_exc()
            self.result_label.setText(f"Error: {exc}")

    def _on_step(self) -> None:
        try:
            if not self.reduced_motion:
                for spin in (self.a_ang, self.b_ang):
                    spin.setValue(spin.value() + random.uniform(-1.0, 1.0))
            self._step_n += 1
            result = self._step_once()
            self._set_result_text(result, prefix=f"Step {self._step_n}")
            self.canvas.update()
        except Exception as exc:
            traceback.print_exc()
            self.result_label.setText(f"Error: {exc}")

    def _step_once(self) -> Dict[str, float]:
        ax, ay = self._components(self.a_mag.value(), self.a_ang.value())
        bx, by = self._components(self.b_mag.value(), self.b_ang.value())
        rx, ry = ax + bx, ay + by
        mag = math.hypot(rx, ry)
        ang = math.degrees(math.atan2(ry, rx)) if mag > 0 else 0.0
        self._update_canvas(ax, ay, bx, by, rx, ry)
        _agent_log(
            {
                "sessionId": "debug-session",
                "runId": "pre-fix",
                "hypothesisId": "H4",
                "location": "vector_add_lab:_step_once",
                "message": "step executed",
                "data": {"a": (ax, ay), "b": (bx, by), "r": (rx, ry), "mag": mag, "ang": ang},
            }
        )
        return {"mag": mag, "ang": ang, "rx": rx, "ry": ry}

    def _set_result_text(self, result: Dict[str, float], *, prefix: str) -> None:
        mag = result.get("mag", 0.0)
        ang = result.get("ang", 0.0)
        rx = result.get("rx", 0.0)
        ry = result.get("ry", 0.0)
        self.result_label.setText(f"{prefix}: {mag:.2f} @ {ang:.1f}° (Rx={rx:.2f}, Ry={ry:.2f})")

    def _components(self, magnitude: float, angle_deg: float) -> tuple[float, float]:
        rad = math.radians(angle_deg)
        return magnitude * math.cos(rad), magnitude * math.sin(rad)

    def _update_canvas(self, ax: float, ay: float, bx: float, by: float, rx: float, ry: float) -> None:
        max_extent = max(
            6.0,
            abs(ax),
            abs(ay),
            abs(bx),
            abs(by),
            abs(rx),
            abs(ry),
        )
        span = max_extent * 1.4
        world = {"xmin": -span, "xmax": span, "ymin": -span, "ymax": span}
        self.canvas.set_world_bounds(world["xmin"], world["xmax"], world["ymin"], world["ymax"])

        vectors = [
            {"start": (0.0, 0.0), "end": (ax, ay), "label": "A", "role": QtGui.QPalette.ColorRole.Link},
            {"start": (0.0, 0.0), "end": (bx, by), "label": "B", "role": QtGui.QPalette.ColorRole.Text},
            {"start": (0.0, 0.0), "end": (rx, ry), "label": "R", "role": QtGui.QPalette.ColorRole.Highlight},
        ]

        def layer_grid(p: QtGui.QPainter, ctx):
            primitives.draw_grid(p, ctx)
            primitives.draw_axes(p, ctx)

        def layer_vectors(p: QtGui.QPainter, ctx):
            for vec in vectors:
                primitives.draw_arrow_sprite(
                    p,
                    ctx,
                    vec["start"],
                    vec["end"],
                    label=vec["label"],
                    color_role=vec["role"],
                )

        self.canvas.set_layers([layer_grid, layer_vectors])
