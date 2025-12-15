from __future__ import annotations

import json
import uuid
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

try:
    from runtime_bus import topics as BUS_TOPICS
except Exception:  # pragma: no cover
    BUS_TOPICS = None

RUN_DIR_REQUEST_TOPIC = (
    BUS_TOPICS.CORE_STORAGE_ALLOCATE_RUN_DIR_REQUEST if BUS_TOPICS else "core.storage.allocate_run_dir.request"
)


class LabHost(QtWidgets.QWidget):
    """Wraps a lab widget with a markdown-based guide viewer and run context provisioning."""

    def __init__(
        self,
        lab_id: str,
        lab_widget: QtWidgets.QWidget,
        guide_markdown_text: str,
        reduced_motion: bool,
        *,
        bus=None,
    ):
        super().__init__()
        self.lab_id = lab_id
        self.lab_widget = lab_widget
        self.bus = bus
        self.reduced_motion = reduced_motion
        self.guide_visible = True
        self.run_context = self._init_run_context()
        self._apply_run_context()

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

    def get_run_context(self) -> dict:
        return dict(self.run_context)

    def _apply_run_context(self) -> None:
        context = dict(self.run_context)
        if hasattr(self.lab_widget, "set_run_context"):
            try:
                self.lab_widget.set_run_context(context)
            except Exception:
                pass

    def _init_run_context(self) -> dict:
        if self.bus and RUN_DIR_REQUEST_TOPIC:
            try:
                response = self.bus.request(
                    RUN_DIR_REQUEST_TOPIC,
                    {"lab_id": self.lab_id},
                    source="app_ui",
                    timeout_ms=1500,
                )
            except Exception:
                response = {"ok": False}
            if response.get("ok"):
                return {
                    "lab_id": self.lab_id,
                    "run_id": response.get("run_id"),
                    "run_dir": response.get("run_dir"),
                    "source": "core_center",
                }
        return self._create_local_run_dir()

    def _create_local_run_dir(self) -> dict:
        run_id = str(uuid.uuid4())
        base = Path("data/store/runs_local") / self.lab_id
        run_dir = base / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "lab_id": self.lab_id,
            "run_id": run_id,
            "timestamp": QtCore.QDateTime.currentDateTimeUtc().toString(QtCore.Qt.DateFormat.ISODate),
            "source": "app_local",
        }
        try:
            (run_dir / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except OSError:
            pass
        return {"lab_id": self.lab_id, "run_id": run_id, "run_dir": str(run_dir.resolve()), "source": "local"}
