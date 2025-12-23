from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PyQt6 import QtCore, QtWidgets

from .context import ComponentContext
from .types import ComponentKind


class MarkdownPanelComponent:
    def __init__(
        self,
        component_id: str,
        display_name: str,
        kind: ComponentKind,
        pack_root: Path,
        assets: Dict,
        params: Dict,
    ) -> None:
        self.component_id = component_id
        self.display_name = display_name
        self.kind = kind
        self._pack_root = Path(pack_root).resolve()
        self._assets = assets or {}
        self._params = params or {}

    def create_widget(self, ctx: ComponentContext) -> QtWidgets.QWidget:
        root = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(root)
        title = QtWidgets.QLabel(self.display_name)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        viewer = QtWidgets.QTextBrowser()
        viewer.setOpenExternalLinks(True)
        text = self._load_markdown()
        if hasattr(viewer, "setMarkdown"):
            viewer.setMarkdown(text)
        else:
            viewer.setPlainText(text)
        layout.addWidget(viewer, stretch=1)
        return root

    def dispose(self) -> None:
        return

    def _load_markdown(self) -> str:
        rel_path = None
        if isinstance(self._assets, dict):
            rel_path = self._assets.get("markdown")
        if not rel_path and isinstance(self._params, dict):
            rel_path = self._params.get("markdown")
        if not isinstance(rel_path, str):
            return "Markdown asset not specified."
        candidate = (self._pack_root / rel_path).resolve()
        try:
            candidate.relative_to(self._pack_root)
        except ValueError:
            return "Markdown asset path is outside the pack root."
        if not candidate.exists():
            return f"Markdown asset missing: {rel_path}"
        try:
            return candidate.read_text(encoding="utf-8")
        except OSError:
            return "Markdown asset could not be read."
