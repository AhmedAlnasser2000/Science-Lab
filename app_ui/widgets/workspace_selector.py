from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PyQt6 import QtCore, QtWidgets


class WorkspaceSelector(QtWidgets.QWidget):
    """
    Lightweight workspace picker that stays in the top-level UI.

    It defers workspace listing and activation to provided callables so it
    remains decoupled from core_center and the runtime bus.
    """

    workspace_activated = QtCore.pyqtSignal(str)

    def __init__(
        self,
        *,
        list_workspaces: Callable[[], List[Dict[str, object]]],
        activate_workspace: Callable[[str], bool],
        get_active_workspace_id: Callable[[], Optional[str]],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._list_workspaces = list_workspaces
        self._activate_workspace = activate_workspace
        self._get_active_workspace_id = get_active_workspace_id
        self._workspaces: List[Dict[str, object]] = []
        self._updating = False

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.label = QtWidgets.QLabel("Workspace:")
        self.combo = QtWidgets.QComboBox()
        self.combo.setMinimumWidth(160)
        self.combo.currentIndexChanged.connect(self._on_combo_changed)

        refresh_btn = QtWidgets.QToolButton()
        refresh_btn.setText("Refresh")
        refresh_btn.setToolTip("Refresh workspace list")
        refresh_btn.clicked.connect(lambda: self.refresh())

        layout.addWidget(self.label)
        layout.addWidget(self.combo)
        layout.addWidget(refresh_btn)

        self.refresh()

    def refresh(self, active_id: Optional[str] = None) -> None:
        """Reload available workspaces and select the active one."""
        active = active_id or self._get_active_workspace_id() or ""
        try:
            workspaces = self._list_workspaces() or []
        except Exception:
            workspaces = []
        self._workspaces = [ws for ws in workspaces if isinstance(ws, dict)]

        self._updating = True
        try:
            self.combo.clear()
            for ws in self._workspaces:
                ws_id = str(ws.get("id") or "").strip()
                if not ws_id:
                    continue
                name = ws.get("name") or ws_id
                label = f"{name} ({ws_id})" if name != ws_id else ws_id
                self.combo.addItem(label, ws_id)
            if active:
                idx = self.combo.findData(active)
                if idx >= 0:
                    self.combo.setCurrentIndex(idx)
        finally:
            self._updating = False

    def set_active_workspace_id(self, workspace_id: str) -> None:
        """Programmatically select the active workspace without firing activation."""
        self._updating = True
        try:
            idx = self.combo.findData(workspace_id)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
        finally:
            self._updating = False

    def _on_combo_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        workspace_id = self.combo.itemData(index)
        if not isinstance(workspace_id, str) or not workspace_id:
            return
        success = False
        try:
            success = self._activate_workspace(workspace_id)
        except Exception:
            success = False
        if success:
            self.workspace_activated.emit(workspace_id)
        else:
            # Revert selection to the known active workspace.
            self.set_active_workspace_id(self._get_active_workspace_id() or "")


