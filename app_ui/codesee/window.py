from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

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

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[name-defined]
        if self._on_close:
            try:
                self._on_close()
            except Exception:
                pass
        super().closeEvent(event)
