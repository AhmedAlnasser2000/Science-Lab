from __future__ import annotations

# =============================================================================
# NAV INDEX (search these tags)
# [NAV-00] Imports/constants
# [NAV-10] Host context/policy wiring
# [NAV-20] LabHost ctor + layout
# [NAV-30] Guide panel + tier gating
# [NAV-40] Export/actions (policy gated)
# [NAV-50] Plugin mount/lifecycle
# [NAV-90] Helpers
# [NAV-99] End
# =============================================================================

# === [NAV-00] Imports/constants ===============================================
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt6 import QtCore, QtWidgets

try:
    from runtime_bus import topics as BUS_TOPICS
except Exception:  # pragma: no cover
    BUS_TOPICS = None

from .context import LabContext
from .prefs_store import get_lab_prefs, save_lab_prefs

RUN_DIR_REQUEST_TOPIC = (
    BUS_TOPICS.CORE_STORAGE_ALLOCATE_RUN_DIR_REQUEST if BUS_TOPICS else "core.storage.allocate_run_dir.request"
)
WORKSPACE_GET_REQUEST_TOPIC = (
    BUS_TOPICS.CORE_WORKSPACE_GET_ACTIVE_REQUEST if BUS_TOPICS else "core.workspace.get_active.request"
)
POLICY_REQUEST_TOPIC = getattr(BUS_TOPICS, "CORE_POLICY_GET_REQUEST", "core.policy.get.request") if BUS_TOPICS else "core.policy.get.request"
LAB_TELEMETRY_TOPIC = BUS_TOPICS.LAB_TELEMETRY if BUS_TOPICS else "lab.telemetry"

DEFAULT_POLICY = {
    "max_concurrent_sims": 1,
    "low_end_mode": False,
    "fps_cap": 60,
    "runs_keep_last_n": 10,
    "exports_enabled": False,
    "reduced_motion_enforced": False,
    "telemetry_enabled": False,
}


# === [NAV-10] Host context/policy wiring =====================================
class LabHost(QtWidgets.QWidget):
    """Wraps a lab widget with a markdown-based guide viewer and run context provisioning."""

    # === [NAV-20] LabHost ctor + layout ======================================
    def __init__(
        self,
        lab_id: str,
        lab_widget: QtWidgets.QWidget,
        guide_markdown_text: str,
        reduced_motion: bool,
        *,
        bus=None,
        profile: str = "Learner",
        plugin=None,
    ):
        super().__init__()
        self.lab_id = lab_id
        self.lab_widget = lab_widget
        self.bus = bus
        self.reduced_motion = reduced_motion
        self.profile = profile
        self.plugin = plugin
        self.guide_visible = True
        self.workspace_info = self._init_workspace_info()
        self.policy = self._init_policy()
        self.run_context = self._init_run_context()
        self.run_context.setdefault("policy", self.policy)
        self.run_context.setdefault("profile", self.profile)
        self.run_context.setdefault("workspace_id", self.workspace_info.get("id"))
        self.run_context.setdefault("workspace_root", self.workspace_info.get("paths", {}).get("root"))
        self.user_prefs = get_lab_prefs(self.lab_id)
        self.lab_context = LabContext(
            lab_id=self.lab_id,
            profile=self.profile,
            reduced_motion=self.reduced_motion,
            run_id=self.run_context.get("run_id"),
            run_dir=self.run_context.get("run_dir"),
            policy=dict(self.policy),
            user_prefs=self.user_prefs,
            workspace_id=self.workspace_info.get("id"),
            workspace_root=self.workspace_info.get("paths", {}).get("root"),
        )
        print(f"[lab_host] policy resolved for {self.lab_id}: {self.policy}")
        self._apply_run_context()
        self._apply_lab_context()
        self.telemetry_timer = QtCore.QTimer(self)
        self.telemetry_timer.timeout.connect(self._emit_telemetry)
        self.telemetry_start: Optional[float] = None
        self.export_actions: List[Dict[str, Any]] = []

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        controls = QtWidgets.QHBoxLayout()
        self.export_btn = QtWidgets.QPushButton("Export")
        self.export_btn.clicked.connect(self._show_export_menu)
        self.export_btn.setVisible(False)
        controls.addWidget(self.export_btn)
        self.export_status = QtWidgets.QLabel("")
        self.export_status.setStyleSheet("color: #4a4a4a; font-size: 12px;")
        self.export_status.setVisible(False)
        controls.addWidget(self.export_status)
        self.grid_toggle = QtWidgets.QCheckBox("Grid")
        self.grid_toggle.setChecked(self.user_prefs.show_grid)
        self.grid_toggle.toggled.connect(self._on_prefs_changed)
        controls.addWidget(self.grid_toggle)
        self.axes_toggle = QtWidgets.QCheckBox("Axes")
        self.axes_toggle.setChecked(self.user_prefs.show_axes)
        self.axes_toggle.toggled.connect(self._on_prefs_changed)
        controls.addWidget(self.axes_toggle)
        controls.addStretch()
        main_layout.addLayout(controls)

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
        self.export_actions = self._resolve_export_actions()
        self._update_export_controls()
        self._configure_telemetry()

    # === [NAV-30] Guide panel + tier gating ==================================
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

    # === [NAV-40] Export/actions (policy gated) ===============================
    def _resolve_export_actions(self) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        if not self.policy.get("exports_enabled"):
            return actions
        if self.plugin and hasattr(self.plugin, "get_export_actions"):
            try:
                plugin_actions = self.plugin.get_export_actions(dict(self.run_context)) or []
                for entry in plugin_actions:
                    label = entry.get("label") or entry.get("id")
                    handler = entry.get("run")
                    if isinstance(handler, str):
                        callback = getattr(self.plugin, handler, None)
                    else:
                        callback = handler
                    if callable(callback) and isinstance(label, str):
                        actions.append({"id": entry.get("id") or label, "label": label, "handler": callback})
            except Exception:
                pass
        if not actions:
            actions.append(
                {
                    "id": "export_run_metadata",
                    "label": "Export run metadata",
                    "handler": self._export_run_metadata,
                }
            )
        return actions

    def _update_export_controls(self) -> None:
        visible = bool(self.export_actions)
        self.export_btn.setVisible(visible)
        if not visible:
            self.export_status.setVisible(False)

    def _show_export_menu(self) -> None:
        if not self.export_actions:
            return
        menu = QtWidgets.QMenu(self)
        for action in self.export_actions:
            act = menu.addAction(action["label"])
            act.triggered.connect(lambda _checked=False, meta=action: self._invoke_export_action(meta))
        menu.exec(self.export_btn.mapToGlobal(self.export_btn.rect().center()))

    def _invoke_export_action(self, action: Dict[str, Any]) -> None:
        handler = action.get("handler")
        if isinstance(handler, str) and self.plugin:
            handler = getattr(self.plugin, handler, None)
        if not callable(handler):
            self._set_export_status(f"{action.get('label', 'Export')} unavailable", ok=False)
            return
        try:
            handler(dict(self.run_context))
            self._set_export_status(f"{action.get('label', 'Export')} completed", ok=True)
        except Exception as exc:
            self._set_export_status(f"{action.get('label', 'Export')} failed: {exc}", ok=False)

    def _set_export_status(self, text: str, ok: bool) -> None:
        color = "#2e7d32" if ok else "#b71c1c"
        self.export_status.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.export_status.setText(text)
        self.export_status.setVisible(True)

    def _on_prefs_changed(self) -> None:
        self.lab_context.user_prefs.show_grid = self.grid_toggle.isChecked()
        self.lab_context.user_prefs.show_axes = self.axes_toggle.isChecked()
        save_lab_prefs(self.lab_id, self.lab_context.user_prefs)
        self._apply_lab_context()
        try:
            self.lab_widget.update()
        except Exception:
            pass

    # === [NAV-50] Plugin mount/lifecycle =====================================
    def _export_run_metadata(self, context: dict) -> None:
        run_dir = Path(context.get("run_dir") or "")
        if not run_dir:
            raise RuntimeError("run directory unavailable")
        run_dir.mkdir(parents=True, exist_ok=True)
        snapshot = dict(context)
        snapshot.pop("policy", None)
        target = run_dir / f"export_snapshot_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
        target.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    def get_run_context(self) -> dict:
        return dict(self.run_context)

    def _apply_run_context(self) -> None:
        context = dict(self.run_context)
        if hasattr(self.lab_widget, "set_run_context"):
            try:
                self.lab_widget.set_run_context(context)
            except Exception:
                pass

    def _apply_lab_context(self) -> None:
        if hasattr(self.lab_widget, "set_context"):
            try:
                self.lab_widget.set_context(self.lab_context)
                return
            except Exception:
                pass
        if hasattr(self.lab_widget, "set_lab_context"):
            try:
                self.lab_widget.set_lab_context(self.lab_context)
                return
            except Exception:
                pass
        try:
            setattr(self.lab_widget, "lab_context", self.lab_context)
        except Exception:
            pass

    # === [NAV-90] Helpers =====================================================
    def _init_policy(self) -> dict:
        policy = dict(DEFAULT_POLICY)
        if self.bus and POLICY_REQUEST_TOPIC:
            try:
                response = self.bus.request(
                    POLICY_REQUEST_TOPIC,
                    {},
                    source="app_ui",
                    timeout_ms=1000,
                )
            except Exception:
                response = {"ok": False}
            if response.get("ok") and isinstance(response.get("policy"), dict):
                policy.update(response["policy"])
                return policy
        return policy

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

    def _init_workspace_info(self) -> Dict[str, object]:
        info = self._request_workspace_info()
        if info:
            return info
        return self._local_workspace_info("default")

    def _request_workspace_info(self) -> Optional[Dict[str, object]]:
        if not (self.bus and WORKSPACE_GET_REQUEST_TOPIC):
            return None
        try:
            response = self.bus.request(
                WORKSPACE_GET_REQUEST_TOPIC,
                {},
                source="app_ui",
                timeout_ms=1000,
            )
        except Exception:
            response = {"ok": False}
        if response.get("ok"):
            workspace = response.get("workspace")
            if isinstance(workspace, dict):
                return workspace
            if "id" in response and "paths" in response:
                return {"id": response.get("id"), "paths": response.get("paths")}
        return None

    def _local_workspace_info(self, workspace_id: str) -> Dict[str, object]:
        safe_id = self._sanitize_workspace_id(workspace_id)
        root = Path("data") / "workspaces" / safe_id
        paths = {
            "root": root,
            "runs": root / "runs",
            "runs_local": root / "runs_local",
            "cache": root / "cache",
            "store": root / "store",
            "prefs": root / "prefs",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return {"id": safe_id, "paths": {name: str(path.resolve()) for name, path in paths.items()}}

    def _sanitize_workspace_id(self, value: str) -> str:
        clean = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
        return clean or "default"

    def _create_local_run_dir(self) -> dict:
        run_id = str(uuid.uuid4())
        paths = self.workspace_info.get("paths") if isinstance(self.workspace_info, dict) else {}
        base_root = None
        if isinstance(paths, dict):
            base_root = paths.get("runs_local")
        base = Path(base_root) if base_root else Path("data") / "workspaces" / "default" / "runs_local"
        base = base / self.lab_id
        run_dir = base / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "lab_id": self.lab_id,
            "run_id": run_id,
            "timestamp": QtCore.QDateTime.currentDateTimeUtc().toString(QtCore.Qt.DateFormat.ISODate),
            "source": "app_local",
            "workspace_id": self.workspace_info.get("id"),
        }
        try:
            (run_dir / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except OSError:
            pass
        try:
            (run_dir / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except OSError:
            pass
        keep_raw = self.policy.get("runs_keep_last_n", DEFAULT_POLICY["runs_keep_last_n"])
        try:
            keep_value = int(keep_raw)
        except (TypeError, ValueError):
            keep_value = DEFAULT_POLICY["runs_keep_last_n"]
        self._enforce_local_retention(base, keep_value)
        return {"lab_id": self.lab_id, "run_id": run_id, "run_dir": str(run_dir.resolve()), "source": "local"}

    def _enforce_local_retention(self, lab_root: Path, keep_last_n: int) -> None:
        keep = max(1, keep_last_n)
        if not lab_root.exists():
            return
        entries = []
        for child in lab_root.iterdir():
            if not child.is_dir():
                continue
            ts = self._run_dir_timestamp(child)
            entries.append((ts, child))
        entries.sort(key=lambda item: item[0], reverse=True)
        for _, path in entries[keep:]:
            self._safe_remove_dir(path)

    def _run_dir_timestamp(self, path: Path) -> float:
        meta_path = path / "run.json"
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                stamp = data.get("timestamp")
                if isinstance(stamp, str):
                    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _safe_remove_dir(self, path: Path) -> None:
        for child in path.iterdir():
            try:
                if child.is_symlink():
                    child.unlink()
                    continue
                if child.is_dir():
                    self._safe_remove_dir(child)
                elif child.exists():
                    child.unlink()
            except Exception:
                continue
        try:
            path.rmdir()
        except Exception:
            pass

    def _configure_telemetry(self) -> None:
        self.telemetry_timer.stop()
        self.telemetry_start = None
        if not (
            self.bus
            and self.policy.get("telemetry_enabled")
            and self.profile == "Explorer"
            and self.plugin
        ):
            return
        interval = 500
        if self.policy.get("low_end_mode") or self.reduced_motion:
            interval = 2000
        self.telemetry_start = time.monotonic()
        self.telemetry_timer.start(interval)

    def _emit_telemetry(self) -> None:
        if not (self.bus and self.plugin):
            return
        try:
            snapshot = self.plugin.get_telemetry_snapshot(dict(self.run_context))
        except Exception:
            snapshot = None
        if not snapshot:
            return
        if self.telemetry_start is None:
            self.telemetry_start = time.monotonic()
        elapsed = time.monotonic() - self.telemetry_start
        payload = {
            "lab_id": self.lab_id,
            "run_id": self.run_context.get("run_id"),
            "t": elapsed,
            "snapshot": snapshot,
        }
        try:
            self.bus.publish(LAB_TELEMETRY_TOPIC, payload, source="app_ui")
        except Exception:
            self.telemetry_timer.stop()


# === [NAV-99] End =============================================================
