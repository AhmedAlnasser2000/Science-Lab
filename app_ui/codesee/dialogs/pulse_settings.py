from __future__ import annotations

from typing import Dict, Optional

from PyQt6 import QtWidgets

from .. import view_config


def _pulse_topic_labels() -> Dict[str, str]:
    return {
        "app.activity": "App activity",
        "app.error": "App error",
        "app.crash": "App crash",
        "job.update": "Job update",
        "span.start": "Span start",
        "span.update": "Span update",
        "span.end": "Span end",
        "bus.request": "Bus request",
        "bus.reply": "Bus reply",
        "expect.check": "Expectation check",
        "codesee.test_pulse": "Test pulse",
    }


def open_pulse_settings(
    parent: QtWidgets.QWidget,
    settings: view_config.PulseSettings,
) -> Optional[view_config.PulseSettings]:
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Pulse Settings")
    layout = QtWidgets.QVBoxLayout(dialog)
    form = QtWidgets.QFormLayout()

    speed = QtWidgets.QSpinBox()
    speed.setRange(100, 5000)
    speed.setValue(int(settings.travel_speed_px_per_s))
    form.addRow("Travel speed (px/s)", speed)

    travel_duration = QtWidgets.QSpinBox()
    travel_duration.setRange(0, 5000)
    travel_duration.setValue(int(settings.travel_duration_ms))
    form.addRow("Travel duration (ms, 0=auto)", travel_duration)

    duration = QtWidgets.QSpinBox()
    duration.setRange(150, 2000)
    duration.setValue(int(settings.pulse_duration_ms))
    form.addRow("Pulse duration (ms)", duration)

    linger = QtWidgets.QSpinBox()
    linger.setRange(0, 2000)
    linger.setValue(int(settings.arrive_linger_ms))
    form.addRow("Node sticky (ms)", linger)

    fade = QtWidgets.QSpinBox()
    fade.setRange(100, 3000)
    fade.setValue(int(settings.fade_ms))
    form.addRow("Fade (ms)", fade)

    curve = QtWidgets.QComboBox()
    curve.addItem("Linear", "linear")
    curve.addItem("Ease Out", "ease")
    curve_index = curve.findData(settings.fade_curve)
    if curve_index >= 0:
        curve.setCurrentIndex(curve_index)
    form.addRow("Fade curve", curve)

    radius = QtWidgets.QSpinBox()
    radius.setRange(4, 24)
    radius.setValue(int(settings.pulse_radius_px))
    form.addRow("Pulse radius (px)", radius)

    alpha = QtWidgets.QDoubleSpinBox()
    alpha.setRange(0.1, 1.0)
    alpha.setSingleStep(0.05)
    alpha.setDecimals(2)
    alpha.setValue(float(settings.pulse_alpha))
    form.addRow("Pulse alpha", alpha)

    min_alpha = QtWidgets.QDoubleSpinBox()
    min_alpha.setRange(0.0, 0.8)
    min_alpha.setSingleStep(0.05)
    min_alpha.setDecimals(2)
    min_alpha.setValue(float(settings.pulse_min_alpha))
    form.addRow("Min intensity", min_alpha)

    intensity = QtWidgets.QDoubleSpinBox()
    intensity.setRange(0.2, 2.0)
    intensity.setSingleStep(0.1)
    intensity.setDecimals(2)
    intensity.setValue(float(settings.intensity_multiplier))
    form.addRow("Intensity multiplier", intensity)

    trail_length = QtWidgets.QSpinBox()
    trail_length.setRange(1, 8)
    trail_length.setValue(int(getattr(settings, "trail_length", 3)))
    form.addRow("Trail length (dots)", trail_length)

    trail_spacing = QtWidgets.QSpinBox()
    trail_spacing.setRange(30, 400)
    trail_spacing.setValue(int(getattr(settings, "trail_spacing_ms", 70)))
    form.addRow("Trail spacing (ms)", trail_spacing)

    tint_active = QtWidgets.QCheckBox("Tint node while active span runs")
    tint_active.setChecked(bool(settings.tint_active_spans))
    form.addRow(tint_active)

    max_signals = QtWidgets.QSpinBox()
    max_signals.setRange(1, 20)
    max_signals.setValue(int(settings.max_concurrent_signals))
    form.addRow("Max concurrent", max_signals)

    topic_group = QtWidgets.QGroupBox("Pulse topics")
    topic_layout = QtWidgets.QVBoxLayout(topic_group)
    topic_checks: Dict[str, QtWidgets.QCheckBox] = {}
    for key, label in _pulse_topic_labels().items():
        checkbox = QtWidgets.QCheckBox(label)
        enabled = bool(getattr(settings, "topic_enabled", {}).get(key, True))
        checkbox.setChecked(enabled)
        topic_layout.addWidget(checkbox)
        topic_checks[key] = checkbox
    layout.addWidget(topic_group)

    layout.addLayout(form)
    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.StandardButton.Ok
        | QtWidgets.QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    return view_config.PulseSettings(
        travel_speed_px_per_s=int(speed.value()),
        travel_duration_ms=int(travel_duration.value()),
        arrive_linger_ms=int(linger.value()),
        fade_ms=int(fade.value()),
        pulse_duration_ms=int(duration.value()),
        pulse_radius_px=int(radius.value()),
        pulse_alpha=float(alpha.value()),
        pulse_min_alpha=float(min_alpha.value()),
        intensity_multiplier=float(intensity.value()),
        fade_curve=str(curve.currentData() or "linear"),
        trail_length=int(trail_length.value()),
        trail_spacing_ms=int(trail_spacing.value()),
        max_concurrent_signals=int(max_signals.value()),
        tint_active_spans=bool(tint_active.isChecked()),
        topic_enabled={key: bool(check.isChecked()) for key, check in topic_checks.items()},
    )

