from __future__ import annotations

from typing import Dict, Optional

from PyQt6 import QtWidgets

from .. import view_config


def _facet_labels() -> Dict[str, str]:
    return {
        "deps": "Dependencies",
        "packs": "Packs",
        "entry_points": "Entry points",
        "logs": "Logs",
        "activity": "Activity",
        "spans": "Spans",
        "runs": "Runs",
        "errors": "Errors",
        "signals": "Signals",
    }


def open_facet_settings(
    parent: QtWidgets.QWidget,
    settings: view_config.FacetSettings,
) -> Optional[view_config.FacetSettings]:
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Facet Settings")
    root = QtWidgets.QVBoxLayout(dialog)
    form = QtWidgets.QFormLayout()

    density_combo = QtWidgets.QComboBox()
    density_combo.addItem("Off", "off")
    density_combo.addItem("Minimal", "minimal")
    density_combo.addItem("Standard", "standard")
    density_combo.addItem("Expanded", "expanded")
    density_combo.addItem("Debug", "debug")
    density_value = str(getattr(settings, "density", "minimal") or "minimal").strip().lower()
    density_index = density_combo.findData(density_value)
    if density_index >= 0:
        density_combo.setCurrentIndex(density_index)
    form.addRow("Density", density_combo)

    scope_combo = QtWidgets.QComboBox()
    scope_combo.addItem("Selected node only", "selected")
    scope_combo.addItem("Current Peek graph", "peek_graph")
    scope_value = str(getattr(settings, "facet_scope", "selected") or "selected").strip().lower()
    scope_index = scope_combo.findData(scope_value)
    if scope_index >= 0:
        scope_combo.setCurrentIndex(scope_index)
    form.addRow("Facet scope", scope_combo)

    show_normal = QtWidgets.QCheckBox("Show in normal view")
    show_normal.setChecked(bool(getattr(settings, "show_in_normal_view", True)))
    form.addRow(show_normal)

    show_peek = QtWidgets.QCheckBox("Show in peek view")
    show_peek.setChecked(bool(getattr(settings, "show_in_peek_view", True)))
    form.addRow(show_peek)

    root.addLayout(form)

    facets_group = QtWidgets.QGroupBox("Facet nodes")
    facets_layout = QtWidgets.QVBoxLayout(facets_group)
    facet_checks: Dict[str, QtWidgets.QCheckBox] = {}
    enabled_map = getattr(settings, "enabled", {}) if isinstance(getattr(settings, "enabled", {}), dict) else {}
    for key in view_config.FACET_KEYS:
        check = QtWidgets.QCheckBox(_facet_labels().get(key, key.replace("_", " ").title()))
        check.setChecked(bool(enabled_map.get(key, False)))
        facets_layout.addWidget(check)
        facet_checks[key] = check
    root.addWidget(facets_group)

    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.StandardButton.Ok
        | QtWidgets.QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    root.addWidget(buttons)

    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None

    return view_config.FacetSettings(
        density=str(density_combo.currentData() or "minimal"),
        enabled={key: bool(check.isChecked()) for key, check in facet_checks.items()},
        facet_scope=str(scope_combo.currentData() or "selected"),
        show_in_normal_view=bool(show_normal.isChecked()),
        show_in_peek_view=bool(show_peek.isChecked()),
    )
