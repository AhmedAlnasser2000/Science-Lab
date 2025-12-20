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
from .renderkit import AssetResolver, AssetCache, RenderCanvas
from .context import LabContext, LabUserPrefs
from .shared import primitives as shared_primitives
from .shared.math2d import Vec2
from .shared.viewport import ViewTransform


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
        self.lab_context: LabContext | None = None
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

    def set_lab_context(self, context: LabContext) -> None:
        self.lab_context = context
        self.reduced_motion = bool(context.reduced_motion)
        self.canvas.update()

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
        a_vec = self._components(self.a_mag.value(), self.a_ang.value())
        b_vec = self._components(self.b_mag.value(), self.b_ang.value())
        r_vec = a_vec + b_vec
        mag = r_vec.length()
        ang = math.degrees(math.atan2(r_vec.y, r_vec.x)) if mag > 0 else 0.0
        self._update_canvas(a_vec, b_vec, r_vec)
        _agent_log(
            {
                "sessionId": "debug-session",
                "runId": "pre-fix",
                "hypothesisId": "H4",
                "location": "vector_add_lab:_step_once",
                "message": "step executed",
                "data": {
                    "a": (a_vec.x, a_vec.y),
                    "b": (b_vec.x, b_vec.y),
                    "r": (r_vec.x, r_vec.y),
                    "mag": mag,
                    "ang": ang,
                },
            }
        )
        return {"mag": mag, "ang": ang, "rx": r_vec.x, "ry": r_vec.y}

    def _set_result_text(self, result: Dict[str, float], *, prefix: str) -> None:
        mag = result.get("mag", 0.0)
        ang = result.get("ang", 0.0)
        rx = result.get("rx", 0.0)
        ry = result.get("ry", 0.0)
        self.result_label.setText(f"{prefix}: {mag:.2f} @ {ang:.1f}° (Rx={rx:.2f}, Ry={ry:.2f})")

    def _components(self, magnitude: float, angle_deg: float) -> Vec2:
        rad = math.radians(angle_deg)
        return Vec2(magnitude * math.cos(rad), magnitude * math.sin(rad))

    def _get_prefs(self) -> LabUserPrefs:
        ctx = self.lab_context
        if ctx and ctx.user_prefs:
            return ctx.user_prefs
        return LabUserPrefs()

    def _update_canvas(self, a_vec: Vec2, b_vec: Vec2, r_vec: Vec2) -> None:
        max_extent = max(
            6.0,
            abs(a_vec.x),
            abs(a_vec.y),
            abs(b_vec.x),
            abs(b_vec.y),
            abs(r_vec.x),
            abs(r_vec.y),
        )
        span = max_extent * 1.4
        world = {"xmin": -span, "xmax": span, "ymin": -span, "ymax": span}
        self.canvas.set_world_bounds(world["xmin"], world["xmax"], world["ymin"], world["ymax"])

        def _build_view(p: QtGui.QPainter) -> ViewTransform:
            rect_px = QtCore.QRectF(p.viewport())
            view = ViewTransform(padding_px=28)
            view.set_world_bounds(world["xmin"], world["xmax"], world["ymin"], world["ymax"])
            view.fit(int(rect_px.width()), int(rect_px.height()))
            return view

        vectors = [
            {"start": Vec2(0.0, 0.0), "end": a_vec, "label": "A", "color": QtGui.QColor("#7fa8ff")},
            {"start": Vec2(0.0, 0.0), "end": b_vec, "label": "B", "color": QtGui.QColor("#c1c7d0")},
            {"start": Vec2(0.0, 0.0), "end": r_vec, "label": "R", "color": QtGui.QColor("#9ad2ff")},
        ]

        def layer_grid(p: QtGui.QPainter, ctx):
            rect_px = QtCore.QRectF(p.viewport())
            prefs = self._get_prefs()
            view = _build_view(p)
            origin = view.world_to_screen(QtCore.QPointF(0.0, 0.0))
            step_world = max(1.0, span / 8.0)
            step_px = abs(view.world_to_screen(QtCore.QPointF(step_world, 0.0)).x() - origin.x())
            if prefs.show_grid:
                shared_primitives.draw_grid(p, rect_px, step_px=step_px)
            if prefs.show_axes:
                axis_len = min(rect_px.width(), rect_px.height()) / 2.0
                shared_primitives.draw_axes(p, origin, axis_len_px=axis_len)

        def layer_vectors(p: QtGui.QPainter, ctx):
            view = _build_view(p)
            for vec in vectors:
                start = view.world_to_screen(QtCore.QPointF(vec["start"].x, vec["start"].y))
                end = view.world_to_screen(QtCore.QPointF(vec["end"].x, vec["end"].y))
                shared_primitives.draw_vector(
                    p,
                    start,
                    Vec2(end.x() - start.x(), end.y() - start.y()),
                )
                p.save()
                p.setPen(QtGui.QPen(vec["color"], 1))
                p.drawText(end + QtCore.QPointF(8, -6), vec["label"])
                p.restore()

        self.canvas.set_layers([layer_grid, layer_vectors])
