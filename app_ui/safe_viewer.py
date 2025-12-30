from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6 import QtCore, QtWidgets

from app_ui.codesee import crash_io
from app_ui import versioning
from app_ui.codesee.screen import CodeSeeScreen
from app_ui.widgets.workspace_selector import WorkspaceSelector


def _workspaces_root() -> Path:
    return Path("data") / "workspaces"


def _workspace_config_path(root: Path) -> Path:
    return root / "prefs" / "workspace_config.json"


def _read_workspace_name(root: Path) -> Optional[str]:
    path = _workspace_config_path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    name = data.get("name") or data.get("workspace_name")
    return str(name).strip() if name else None


def discover_workspaces() -> List[Dict[str, Any]]:
    root = _workspaces_root()
    workspaces: List[Dict[str, Any]] = []
    if root.exists():
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            ws_id = entry.name
            name = _read_workspace_name(entry) or ws_id
            workspaces.append(
                {
                    "id": ws_id,
                    "name": name,
                    "root": str(entry),
                }
            )
    if not workspaces:
        workspaces.append(
            {
                "id": "default",
                "name": "default",
                "root": str(root / "default"),
            }
        )
    return workspaces


class CodeSeeViewerWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        *,
        workspace_info_provider,
        workspace_selector_factory,
        on_close,
        crash_view: bool = False,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Code See (Safe Viewer)")
        self.resize(1100, 720)
        self.setMinimumSize(900, 600)
        self._on_close = on_close
        self.screen = CodeSeeScreen(
            on_back=self.close,
            workspace_info_provider=workspace_info_provider,
            workspace_selector_factory=workspace_selector_factory,
            runtime_hub=None,
            allow_detach=False,
            safe_mode=True,
            crash_view=crash_view,
        )
        self.setCentralWidget(self.screen)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._on_close:
            try:
                self._on_close()
            except Exception:
                pass
        super().closeEvent(event)


class SafeViewerWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        build = versioning.get_build_info()
        self.setWindowTitle(
            f"PhysicsLab Safe Viewer - {build.get('app_version', 'unknown')} ({build.get('build_id', 'unknown')})"
        )
        self.resize(640, 360)
        self._active_workspace_id = "default"
        self._workspace_map: Dict[str, Dict[str, Any]] = {}
        self._codesee_window: Optional[CodeSeeViewerWindow] = None

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("Safe Viewer Mode")
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        layout.addWidget(title)

        summary = QtWidgets.QLabel(
            "Open Code See snapshots without full app initialization."
        )
        summary.setStyleSheet("color: #555;")
        layout.addWidget(summary)
        build_info = QtWidgets.QLabel(
            f"Build: {build.get('app_version', 'unknown')} ({build.get('build_id', 'unknown')})"
        )
        build_info.setStyleSheet("color: #666;")
        layout.addWidget(build_info)

        selector = WorkspaceSelector(
            list_workspaces=self._list_workspaces,
            activate_workspace=self._activate_workspace,
            get_active_workspace_id=self._get_active_workspace_id,
        )
        selector.workspace_activated.connect(self._on_workspace_activated)
        layout.addWidget(selector)

        self._workspace_path = QtWidgets.QLabel("")
        self._workspace_path.setStyleSheet("color: #666;")
        layout.addWidget(self._workspace_path)

        crash_row = QtWidgets.QHBoxLayout()
        self.crash_label = QtWidgets.QLabel("No recent crash detected.")
        self.crash_label.setStyleSheet("color: #555;")
        crash_row.addWidget(self.crash_label, stretch=1)
        self.crash_btn = QtWidgets.QPushButton("Open Crash View")
        self.crash_btn.setEnabled(False)
        self.crash_btn.clicked.connect(self._open_crash_view)
        crash_row.addWidget(self.crash_btn)
        self.clear_crash_btn = QtWidgets.QPushButton("Clear Crash")
        self.clear_crash_btn.setEnabled(False)
        self.clear_crash_btn.clicked.connect(self._clear_crash_record)
        crash_row.addWidget(self.clear_crash_btn)
        layout.addLayout(crash_row)

        button_row = QtWidgets.QHBoxLayout()
        self.open_btn = QtWidgets.QPushButton("Open Code See")
        self.open_btn.clicked.connect(self._open_codesee)
        button_row.addWidget(self.open_btn)
        button_row.addStretch()
        layout.addLayout(button_row)

        layout.addStretch()
        self.setCentralWidget(central)
        self._refresh_workspace_path()
        self._refresh_crash_state()

    def _list_workspaces(self) -> List[Dict[str, Any]]:
        workspaces = discover_workspaces()
        self._workspace_map = {
            str(ws.get("id")): ws for ws in workspaces if ws.get("id")
        }
        if self._active_workspace_id not in self._workspace_map and workspaces:
            self._active_workspace_id = str(workspaces[0].get("id"))
        return workspaces

    def _activate_workspace(self, workspace_id: str) -> bool:
        workspace_id = str(workspace_id or "").strip()
        if not workspace_id:
            return False
        self._active_workspace_id = workspace_id
        self._refresh_workspace_path()
        return True

    def _get_active_workspace_id(self) -> str:
        return self._active_workspace_id

    def _workspace_info(self) -> Dict[str, Any]:
        info = dict(self._workspace_map.get(self._active_workspace_id) or {})
        if info.get("id") is None:
            info["id"] = self._active_workspace_id
        return info

    def _workspace_selector_factory(self) -> WorkspaceSelector:
        return WorkspaceSelector(
            list_workspaces=self._list_workspaces,
            activate_workspace=self._activate_workspace,
            get_active_workspace_id=self._get_active_workspace_id,
        )

    def _refresh_workspace_path(self) -> None:
        info = self._workspace_info()
        root = info.get("root") or str(_workspaces_root() / self._active_workspace_id)
        self._workspace_path.setText(f"Workspace path: {root}")

    def _on_workspace_activated(self, _workspace_id: str) -> None:
        self._refresh_workspace_path()
        self._refresh_crash_state()
        if self._codesee_window:
            self._codesee_window.screen.on_workspace_changed()

    def _open_codesee(self) -> None:
        if self._codesee_window:
            self._codesee_window.raise_()
            self._codesee_window.activateWindow()
            return
        window = CodeSeeViewerWindow(
            workspace_info_provider=self._workspace_info,
            workspace_selector_factory=self._workspace_selector_factory,
            on_close=self._on_codesee_closed,
            crash_view=False,
        )
        self._codesee_window = window
        window.show()

    def _open_crash_view(self) -> None:
        if self._codesee_window:
            self._codesee_window.screen.set_crash_view(True)
            self._codesee_window.raise_()
            self._codesee_window.activateWindow()
            return
        window = CodeSeeViewerWindow(
            workspace_info_provider=self._workspace_info,
            workspace_selector_factory=self._workspace_selector_factory,
            on_close=self._on_codesee_closed,
            crash_view=True,
        )
        self._codesee_window = window
        window.show()

    def _on_codesee_closed(self) -> None:
        self._codesee_window = None

    def _refresh_crash_state(self) -> None:
        record = crash_io.read_latest_crash(self._active_workspace_id)
        if record:
            exc_type = record.get("exception_type") or "Crash"
            stamp = _format_crash_timestamp(record.get("ts"))
            self.crash_label.setText(f"Last crash: {exc_type} at {stamp}")
            self.crash_btn.setEnabled(True)
            self.clear_crash_btn.setEnabled(True)
        else:
            self.crash_label.setText("No recent crash detected.")
            self.crash_btn.setEnabled(False)
            self.clear_crash_btn.setEnabled(False)

    def _clear_crash_record(self) -> None:
        crash_io.clear_latest_crash(self._active_workspace_id)
        self._refresh_crash_state()
        if self._codesee_window:
            self._codesee_window.screen.set_crash_view(True)


def _format_crash_timestamp(ts: object) -> str:
    if isinstance(ts, (int, float)):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    return "unknown"
