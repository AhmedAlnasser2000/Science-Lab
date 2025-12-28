from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app_ui.window_state import restore_geometry as restore_window_geometry
from app_ui.window_state import save_geometry as save_window_geometry
from .runtime.hub import CodeSeeRuntimeHub
from .screen import CodeSeeScreen


class CodeSeeWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        *,
        workspace_info_provider: Callable[[], Dict[str, Any]],
        bus=None,
        content_adapter=None,
        runtime_hub: Optional[CodeSeeRuntimeHub] = None,
        workspace_selector_factory: Optional[Callable[[], QtWidgets.QWidget]] = None,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Code See")
        self.resize(1100, 720)
        self.setMinimumSize(900, 600)
        self._on_close = on_close
        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._persist_geometry)
        self.screen = CodeSeeScreen(
            on_back=self.close,
            workspace_info_provider=workspace_info_provider,
            bus=bus,
            content_adapter=content_adapter,
            workspace_selector_factory=workspace_selector_factory,
            runtime_hub=runtime_hub,
            allow_detach=False,
        )
        self.screen.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.setCentralWidget(self.screen)
        central = self.centralWidget()
        if central:
            central.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
        self._restore_geometry()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[name-defined]
        self._persist_geometry()
        if self._on_close:
            try:
                self._on_close()
            except Exception:
                pass
        super().closeEvent(event)

    def moveEvent(self, event: QtGui.QMoveEvent) -> None:  # type: ignore[name-defined]
        self._schedule_persist()
        super().moveEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[name-defined]
        self._schedule_persist()
        super().resizeEvent(event)

    def _schedule_persist(self) -> None:
        self._save_timer.start(350)

    def _persist_geometry(self) -> None:
        save_window_geometry(self, "codesee")

    def _restore_geometry(self) -> None:
        restore_window_geometry(self, "codesee")
