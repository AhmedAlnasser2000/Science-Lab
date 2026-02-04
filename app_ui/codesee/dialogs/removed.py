# =============================================================================
# NAV INDEX (search these tags)
# [NAV-00] Imports / constants
# [NAV-20] CodeSeeRemovedDialog
# [NAV-30] Formatting helpers
# =============================================================================

# === [NAV-00] Imports / constants ============================================
# region NAV-00 Imports / constants
from __future__ import annotations

from typing import Optional

from PyQt6 import QtWidgets

from ..diff import DiffResult

# endregion NAV-00 Imports / constants

# === [NAV-20] CodeSeeRemovedDialog ==========================================
# region NAV-20 CodeSeeRemovedDialog
class CodeSeeRemovedDialog(QtWidgets.QDialog):
    def __init__(self, diff_result: DiffResult, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Removed Items")
        self.setMinimumWidth(420)

        layout = QtWidgets.QVBoxLayout(self)
        nodes_label = QtWidgets.QLabel("Removed Nodes")
        nodes_label.setStyleSheet("color: #444;")
        layout.addWidget(nodes_label)
        nodes_text = QtWidgets.QPlainTextEdit()
        nodes_text.setReadOnly(True)
        nodes_text.setPlainText(_format_removed_nodes(diff_result))
        layout.addWidget(nodes_text)

        edges_label = QtWidgets.QLabel("Removed Edges")
        edges_label.setStyleSheet("color: #444;")
        layout.addWidget(edges_label)
        edges_text = QtWidgets.QPlainTextEdit()
        edges_text.setReadOnly(True)
        edges_text.setPlainText(_format_removed_edges(diff_result))
        layout.addWidget(edges_text)

        close_row = QtWidgets.QHBoxLayout()
        close_row.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)


# endregion NAV-20 CodeSeeRemovedDialog

# === [NAV-30] Formatting helpers ==============================================
# region NAV-30 Formatting helpers
def _format_removed_nodes(diff_result: DiffResult) -> str:
    if not diff_result.nodes_removed:
        return "No removed nodes."
    return "\n".join(sorted(diff_result.nodes_removed))


def _format_removed_edges(diff_result: DiffResult) -> str:
    if not diff_result.edges_removed:
        return "No removed edges."
    lines = []
    for src, dst, kind in sorted(diff_result.edges_removed):
        lines.append(f"{kind}: {src} -> {dst}")
    return "\n".join(lines)



# endregion NAV-30 Formatting helpers
