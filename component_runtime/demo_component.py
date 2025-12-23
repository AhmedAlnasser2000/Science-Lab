from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from .context import ComponentContext
from .registry import register_component
from .types import ComponentKind


class DemoComponent:
    component_id = "demo.hello"
    display_name = "Demo Component"
    kind = ComponentKind.PANEL

    def create_widget(self, ctx: ComponentContext) -> QtWidgets.QWidget:
        root = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(root)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        title = QtWidgets.QLabel("Component Runtime Demo")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        details = [
            f"Profile: {ctx.profile}",
            f"Reduced motion: {ctx.reduced_motion}",
            f"Policy keys: {', '.join(sorted(ctx.policy.keys()))}",
            f"Runs root: {ctx.storage.runs}",
        ]
        for line in details:
            label = QtWidgets.QLabel(line)
            label.setStyleSheet("color: #444;")
            layout.addWidget(label)

        layout.addStretch()
        return root

    def dispose(self) -> None:
        return


def _create_demo() -> DemoComponent:
    return DemoComponent()


register_component(_create_demo)
