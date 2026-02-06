# =============================================================================
# NAV INDEX (search these tags)
# [NAV-00] Imports / constants
# [NAV-10] Public API
# [NAV-99] end
# =============================================================================

# === [NAV-00] Imports / constants ============================================
from __future__ import annotations

from typing import Callable, List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from .. import diagnostics


# === [NAV-10] Public API ======================================================
class CodeSeeDiagnosticsDialog(QtWidgets.QDialog):
    def __init__(
        self,
        snapshot_provider: Callable[[], dict],
        log_provider: Callable[[], List[str]],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("CodeSee Diagnostics")
        self.setMinimumWidth(520)
        self._snapshot_provider = snapshot_provider
        self._log_provider = log_provider

        layout = QtWidgets.QVBoxLayout(self)
        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs)

        self._status_text = QtWidgets.QPlainTextEdit()
        self._status_text.setReadOnly(True)
        status_tab = QtWidgets.QWidget()
        status_layout = QtWidgets.QVBoxLayout(status_tab)
        status_layout.addWidget(self._status_text)
        tabs.addTab(status_tab, "Status")

        self._logs_text = QtWidgets.QPlainTextEdit()
        self._logs_text.setReadOnly(True)
        logs_tab = QtWidgets.QWidget()
        logs_layout = QtWidgets.QVBoxLayout(logs_tab)
        logs_layout.addWidget(self._logs_text)
        tabs.addTab(logs_tab, "Logs")

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch()
        self._refresh_btn = QtWidgets.QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh)
        button_row.addWidget(self._refresh_btn)
        self._copy_btn = QtWidgets.QPushButton("Copy")
        self._copy_btn.clicked.connect(self._copy_to_clipboard)
        button_row.addWidget(self._copy_btn)
        layout.addLayout(button_row)

        self.refresh()

    def refresh(self) -> None:
        snapshot = self._snapshot_provider()
        logs = self._log_provider()
        self._status_text.setPlainText(diagnostics.format_codesee_diagnostics_status(snapshot))
        self._logs_text.setPlainText("\n".join(logs) if logs else "No logs yet.")

    def _copy_to_clipboard(self) -> None:
        snapshot = self._snapshot_provider()
        logs = self._log_provider()
        content = diagnostics.format_codesee_diagnostics(snapshot, logs)
        QtWidgets.QApplication.clipboard().setText(content)


# === [NAV-99] end =============================================================
