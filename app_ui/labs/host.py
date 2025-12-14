from __future__ import annotations

from PyQt6 import QtCore, QtWidgets


class LabHost(QtWidgets.QWidget):
    """Wraps a lab widget with a markdown-based guide viewer."""

    def __init__(self, lab_widget: QtWidgets.QWidget, guide_markdown_text: str, reduced_motion: bool):
        super().__init__()
        self.lab_widget = lab_widget
        self.reduced_motion = reduced_motion
        self.guide_visible = True

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        if reduced_motion:
            self.splitter.setOpaqueResize(False)
        main_layout.addWidget(self.splitter)

        self.guide_panel = QtWidgets.QWidget()
        guide_layout = QtWidgets.QVBoxLayout(self.guide_panel)
        guide_layout.setContentsMargins(8, 8, 8, 8)
        guide_header = QtWidgets.QHBoxLayout()
        guide_title = QtWidgets.QLabel("Lab Guide")
        guide_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        guide_header.addWidget(guide_title)
        guide_header.addStretch()
        self.toggle_btn = QtWidgets.QPushButton("Hide Guide")
        self.toggle_btn.clicked.connect(self._toggle_guide)
        guide_header.addWidget(self.toggle_btn)
        guide_layout.addLayout(guide_header)

        self.guide_view = QtWidgets.QTextBrowser()
        self.guide_view.setOpenExternalLinks(True)
        self._set_guide_text(guide_markdown_text)
        guide_layout.addWidget(self.guide_view, stretch=1)

        self.lab_container = QtWidgets.QWidget()
        lab_layout = QtWidgets.QVBoxLayout(self.lab_container)
        lab_layout.setContentsMargins(0, 0, 0, 0)
        lab_layout.addWidget(self.lab_widget)

        self.splitter.addWidget(self.guide_panel)
        self.splitter.addWidget(self.lab_container)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)

    def update_guide(self, markdown_text: str) -> None:
        self._set_guide_text(markdown_text)

    def _toggle_guide(self) -> None:
        self.guide_visible = not self.guide_visible
        self.guide_panel.setVisible(self.guide_visible)
        self.toggle_btn.setText("Hide Guide" if self.guide_visible else "Show Guide")
        if not self.guide_visible:
            self.splitter.setSizes([0, 1])
        else:
            self.splitter.setSizes([max(200, self.width() // 3), self.width() * 2 // 3])

    def _set_guide_text(self, markdown_text: str) -> None:
        text = markdown_text.strip() if markdown_text else ""
        if not text:
            self.guide_view.setPlainText("Guide not available for this lab yet.")
            return
        try:
            self.guide_view.setMarkdown(text)
        except AttributeError:
            self.guide_view.setPlainText(text)
