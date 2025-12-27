from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from . import view_config
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
        self._on_close = on_close
        self._workspace_info_provider = workspace_info_provider
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
        geometry = self.saveGeometry()
        encoded = bytes(geometry.toBase64()).decode("ascii")
        view_config.save_window_geometry(self._workspace_id(), encoded)

    def _restore_geometry(self) -> None:
        encoded = view_config.load_window_geometry(self._workspace_id())
        if not encoded:
            return
        try:
            data = QtCore.QByteArray.fromBase64(encoded.encode("ascii"))
            if data:
                self.restoreGeometry(data)
        except Exception:
            return

    def _workspace_id(self) -> str:
        info = self._workspace_info_provider() or {}
        if isinstance(info, dict):
            workspace_id = info.get("id") or info.get("workspace_id")
            if workspace_id:
                return str(workspace_id)
        return "default"
