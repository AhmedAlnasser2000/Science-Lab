import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app_ui.widgets.app_header import AppHeader
from app_ui.widgets.workspace_selector import WorkspaceSelector
from diagnostics.fs_ops import safe_copytree, safe_rmtree

try:
    from runtime_bus import topics as BUS_TOPICS
except Exception:  # pragma: no cover - defensive
    BUS_TOPICS = None

try:
    from component_runtime import packs as component_packs
    from component_runtime import registry as component_registry
except Exception:  # pragma: no cover - defensive
    component_packs = None
    component_registry = None

BUS_JOB_COMPLETED = BUS_TOPICS.JOB_COMPLETED if BUS_TOPICS else "job.completed"
BUS_JOB_PROGRESS = BUS_TOPICS.JOB_PROGRESS if BUS_TOPICS else "job.progress"
BUS_INVENTORY_REQUEST = (
    BUS_TOPICS.CORE_INVENTORY_GET_REQUEST if BUS_TOPICS else "core.inventory.get.request"
)
BUS_JOBS_GET_REQUEST = BUS_TOPICS.CORE_JOBS_GET_REQUEST if BUS_TOPICS else "core.jobs.get.request"
BUS_COMPONENT_PACK_INSTALL_REQUEST = (
    BUS_TOPICS.CORE_COMPONENT_PACK_INSTALL_REQUEST
    if BUS_TOPICS
    else "core.component_pack.install.request"
)
BUS_COMPONENT_PACK_UNINSTALL_REQUEST = (
    BUS_TOPICS.CORE_COMPONENT_PACK_UNINSTALL_REQUEST
    if BUS_TOPICS
    else "core.component_pack.uninstall.request"
)


class _BusDispatchBridge(QtCore.QObject):
    envelope_dispatched = QtCore.pyqtSignal(object, object)

    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self.envelope_dispatched.connect(
            self._invoke_handler,
            QtCore.Qt.ConnectionType.QueuedConnection,
        )

    @QtCore.pyqtSlot(object, object)
    def _invoke_handler(self, handler: Callable[[Any], None], envelope: Any) -> None:
        try:
            handler(envelope)
        except Exception:  # pragma: no cover - defensive
            pass


def _format_pack_label(pack: Dict[str, Any]) -> str:
    pack_id = pack.get("pack_id") or "unknown"
    name = pack.get("display_name") or pack_id
    version = pack.get("version") or "?"
    return f"{name} ({pack_id}) v{version}"


def _selected_pack_id(list_widget: QtWidgets.QListWidget) -> Optional[str]:
    item = list_widget.currentItem()
    if not item:
        return None
    value = item.data(QtCore.Qt.ItemDataRole.UserRole)
    return value if isinstance(value, str) else None


def _run_pack_job(action: str, pack_id: str) -> Dict[str, Any]:
    repo_root = Path("component_repo/component_v1/packs")
    store_root = Path("component_store/component_v1/packs")
    repo_pack = repo_root / pack_id
    store_pack = store_root / pack_id

    log_path = r"c:\Users\ahmed\Downloads\PhysicsLab\.cursor\debug.log"

    def _agent_log(message: str, data: Dict[str, Any], hypothesis_id: str) -> None:
        # region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as _fh:
                _fh.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "baseline",
                            "hypothesisId": hypothesis_id,
                            "location": "app_ui/screens/component_management.py:_run_pack_job",
                            "message": message,
                            "data": data,
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        # endregion

    _agent_log(
        "pack_job_start",
        {
            "action": action,
            "pack_id": pack_id,
            "repo_pack": str(repo_pack),
            "store_pack": str(store_pack),
            "repo_exists": repo_pack.exists(),
            "store_exists": store_pack.exists(),
        },
        hypothesis_id="H1",
    )

    repo_root.mkdir(parents=True, exist_ok=True)
    store_root.mkdir(parents=True, exist_ok=True)

    try:
        if action == "install":
            if not repo_pack.exists():
                _agent_log(
                    "pack_job_missing_repo",
                    {"action": action, "pack_id": pack_id, "repo_pack": str(repo_pack)},
                    hypothesis_id="H1",
                )
                return {"ok": False, "message": f"Pack '{pack_id}' not found in repo."}
            if store_pack.exists():
                safe_rmtree(store_pack)
            safe_copytree(repo_pack, store_pack)
            result = {"ok": True, "message": f"Installed {pack_id}."}
            _agent_log(
                "pack_job_complete",
                {"action": action, "pack_id": pack_id, "ok": True, "store_pack": str(store_pack)},
                hypothesis_id="H1",
            )
            return result
        if action == "uninstall":
            if not store_pack.exists():
                _agent_log(
                    "pack_job_missing_store",
                    {"action": action, "pack_id": pack_id, "store_pack": str(store_pack)},
                    hypothesis_id="H1",
                )
                return {"ok": False, "message": f"Pack '{pack_id}' not installed."}
            safe_rmtree(store_pack)
            result = {"ok": True, "message": f"Uninstalled {pack_id}."}
            _agent_log(
                "pack_job_complete",
                {"action": action, "pack_id": pack_id, "ok": True, "store_pack": str(store_pack)},
                hypothesis_id="H1",
            )
            return result
        return {"ok": False, "message": "Unknown action."}
    except Exception as exc:
        result = {
            "ok": False,
            "message": (
                f"{action} failed: pack={pack_id} src={repo_pack} "
                f"dst={store_pack} err={exc!r}"
            ),
        }
        _agent_log(
            "pack_job_error",
            {"action": action, "pack_id": pack_id, "error": str(exc)},
            hypothesis_id="H1",
        )
        return result


class ComponentManagementScreen(QtWidgets.QWidget):
    def __init__(
        self,
        on_back,
        bus=None,
        *,
        workspace_selector_factory: Optional[Callable[[], "WorkspaceSelector"]] = None,
        on_packs_changed: Optional[Callable[[], None]] = None,
    ):
        super().__init__()
        self.on_back = on_back
        self.bus = bus
        self._job_thread: Optional[QtCore.QThread] = None
        self._bus_dispatch_bridge = _BusDispatchBridge(self)
        self._bus_subscriptions: list[str] = []
        self.pending_job_id: Optional[str] = None
        self.pending_pack_id: Optional[str] = None
        self.pending_action: Optional[str] = None
        self._job_poll_timer: Optional[QtCore.QTimer] = None
        self._job_poll_deadline: float = 0.0
        self._installed_pack_ids: set[str] = set()
        self.on_packs_changed = on_packs_changed
        self._bus_available = bool(self.bus)

        layout = QtWidgets.QVBoxLayout(self)
        selector = workspace_selector_factory() if workspace_selector_factory else None
        header = AppHeader(
            title="Pack Management",
            on_back=self.on_back,
            workspace_selector=selector,
        )
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        header.add_action_widget(refresh_btn)
        layout.addWidget(header)

        self.banner = QtWidgets.QLabel("")
        self.banner.setVisible(False)
        self.banner.setStyleSheet("color: #b71c1c; font-weight: bold;")
        layout.addWidget(self.banner)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(splitter, stretch=1)

        repo_panel = QtWidgets.QWidget()
        repo_layout = QtWidgets.QVBoxLayout(repo_panel)
        repo_layout.addWidget(QtWidgets.QLabel("Available Packs (Repo)"))
        self.repo_list = QtWidgets.QListWidget()
        repo_layout.addWidget(self.repo_list, stretch=1)
        repo_btn_row = QtWidgets.QHBoxLayout()
        self.install_btn = QtWidgets.QPushButton("Install Pack")
        self.install_btn.clicked.connect(self._install_selected)
        repo_btn_row.addWidget(self.install_btn)
        repo_layout.addLayout(repo_btn_row)
        splitter.addWidget(repo_panel)

        store_panel = QtWidgets.QWidget()
        store_layout = QtWidgets.QVBoxLayout(store_panel)
        store_layout.addWidget(QtWidgets.QLabel("Installed Packs (Store)"))
        self.store_list = QtWidgets.QListWidget()
        store_layout.addWidget(self.store_list, stretch=1)
        store_btn_row = QtWidgets.QHBoxLayout()
        self.uninstall_btn = QtWidgets.QPushButton("Uninstall Pack")
        self.uninstall_btn.clicked.connect(self._uninstall_selected)
        store_btn_row.addWidget(self.uninstall_btn)
        store_layout.addLayout(store_btn_row)
        splitter.addWidget(store_panel)

        self.progress_panel = QtWidgets.QFrame()
        self.progress_panel.setVisible(False)
        self.progress_panel.setStyleSheet("QFrame { border: 1px solid #ddd; border-radius: 4px; padding: 6px; }")
        pp_layout = QtWidgets.QHBoxLayout(self.progress_panel)
        text_box = QtWidgets.QVBoxLayout()
        self.progress_title = QtWidgets.QLabel("")
        self.progress_details = QtWidgets.QLabel("")
        self.progress_details.setWordWrap(True)
        dismiss_btn = QtWidgets.QPushButton("Dismiss")
        dismiss_btn.clicked.connect(lambda: self.progress_panel.setVisible(False))
        text_box.addWidget(self.progress_title)
        text_box.addWidget(self.progress_details)
        pp_layout.addLayout(text_box, stretch=1)
        pp_layout.addWidget(dismiss_btn)
        layout.addWidget(self.progress_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)

        self._init_bus_subscriptions()
        self.refresh()

    def refresh(self) -> None:
        self.repo_list.clear()
        self.store_list.clear()
        if not self.bus:
            self._bus_available = False
            self._set_banner("Management Core unavailable (runtime bus not connected).")
            self.install_btn.setEnabled(False)
            self.uninstall_btn.setEnabled(False)
            return
        self._bus_available = True
        self._set_banner("")
        repo_packs = component_packs.list_repo_packs() if component_packs else []
        store_packs, inv_ok = self._load_installed_packs()
        if not inv_ok:
            self._set_banner("Management Core inventory unavailable; pack actions disabled.")
            self.install_btn.setEnabled(False)
            self.uninstall_btn.setEnabled(False)
        else:
            self._set_banner("")
        self._installed_pack_ids = {
            p.get("pack_id") or p.get("id") for p in store_packs if p.get("pack_id") or p.get("id")
        }
        for pack in repo_packs:
            label = _format_pack_label(pack)
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, pack.get("pack_id"))
            self.repo_list.addItem(item)
        for pack in store_packs:
            pack_id = pack.get("pack_id") or pack.get("id")
            label = _format_pack_label(
                {
                    "pack_id": pack_id,
                    "display_name": pack.get("display_name") or pack.get("name") or pack_id,
                    "version": pack.get("version"),
                }
            )
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, pack_id)
            self.store_list.addItem(item)
        if inv_ok and not self.pending_job_id:
            self.install_btn.setEnabled(True)
            self.uninstall_btn.setEnabled(True)

    def _install_selected(self) -> None:
        pack_id = _selected_pack_id(self.repo_list)
        if not pack_id:
            self._show_progress("Install", "Select a pack to install.", running=False, ok=False)
            return
        if pack_id in self._installed_pack_ids:
            self._show_progress("Install", f"{pack_id} already installed.", running=False, ok=False)
            return
        self._run_job("install", pack_id)

    def _uninstall_selected(self) -> None:
        pack_id = _selected_pack_id(self.store_list)
        if not pack_id:
            self._show_progress("Uninstall", "Select a pack to uninstall.", running=False, ok=False)
            return
        if pack_id not in self._installed_pack_ids:
            self._show_progress("Uninstall", f"{pack_id} not installed.", running=False, ok=False)
            return
        self._run_job("uninstall", pack_id)

    def _run_job(self, action: str, pack_id: str) -> None:
        if not self.bus:
            self._show_progress("Pack Job", "Runtime bus unavailable.", running=False, ok=False)
            return
        if self.pending_job_id:
            self._show_progress("Pack Job", "Another pack job is running.", running=False, ok=False)
            return
        topic = BUS_COMPONENT_PACK_INSTALL_REQUEST if action == "install" else BUS_COMPONENT_PACK_UNINSTALL_REQUEST
        self._set_job_state(job_id=None, pack_id=pack_id, action=action, running=True)
        self._show_progress(f"{action.title()} {pack_id}", "Starting job...", running=True)
        try:
            response = self.bus.request(
                topic,
                {"pack_id": pack_id},
                source="app_ui",
                timeout_ms=2000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._set_job_state(job_id=None, pack_id=None, action=None, running=False)
            self._show_progress("Pack Job", f"{action.title()} failed: {exc}", running=False, ok=False)
            return
        if not response.get("ok") or not response.get("job_id"):
            self._set_job_state(job_id=None, pack_id=None, action=None, running=False)
            self._show_progress(
                "Pack Job",
                f"{action.title()} failed: {response.get('error') or 'unknown'}",
                running=False,
                ok=False,
            )
            return
        job_id = str(response["job_id"])
        self._set_job_state(job_id=job_id, pack_id=pack_id, action=action, running=True)
        self._show_progress(
            "Pack Job",
            f"{action.title()} {pack_id}: awaiting completion (job {job_id[:8]})",
            running=True,
        )
        self._start_job_poll_timer()

    def _on_job_finished(self, result: Dict[str, Any]) -> None:
        self._job_thread = None
        self.install_btn.setEnabled(True)
        self.uninstall_btn.setEnabled(True)
        ok = bool(result.get("ok"))
        details = result.get("message") or ""
        self._show_progress("Pack Job", details, running=False, ok=ok)
        self._refresh_registry()
        self.refresh()

    def _on_job_error(self, error: str) -> None:
        self._job_thread = None
        self.install_btn.setEnabled(True)
        self.uninstall_btn.setEnabled(True)
        self._show_progress("Pack Job", error, running=False, ok=False)

    def _refresh_registry(self) -> None:
        if component_registry is None or component_packs is None:
            return
        try:
            component_packs.load_installed_packs()
        except Exception:
            pass

    def _show_progress(self, title: str, details: str, running: bool, ok: Optional[bool] = None) -> None:
        color = "#7a7a7a"
        if ok is True:
            color = "#2e7d32"
        elif ok is False:
            color = "#b71c1c"
        if running:
            details = f"{details} (running)"
        self.progress_title.setText(title)
        self.progress_title.setStyleSheet(f"font-weight: bold; color: {color};")
        self.progress_details.setText(details)
        self.progress_panel.setVisible(True)

    def _load_installed_packs(self) -> tuple[list[Dict[str, Any]], bool]:
        if self.bus:
            try:
                response = self.bus.request(
                    BUS_INVENTORY_REQUEST,
                    {},
                    source="app_ui",
                    timeout_ms=1500,
                )
                if response.get("ok"):
                    inventory = response.get("inventory") or {}
                    packs = inventory.get("component_packs") or []
                    return [
                        {
                            "pack_id": pack.get("id") or pack.get("pack_id"),
                            "version": pack.get("version"),
                            "display_name": pack.get("display_name") or pack.get("name"),
                        }
                        for pack in packs
                        if pack.get("id") or pack.get("pack_id")
                    ], True
            except Exception:
                return [], False
            return [], False
        if component_packs is None:
            return [], False
        return component_packs.list_installed_packs(), True

    def _init_bus_subscriptions(self) -> None:
        if not self.bus or self._bus_subscriptions:
            return
        self._subscribe_bus(BUS_JOB_PROGRESS, self._on_job_progress_event, replay_last=False)
        self._subscribe_bus(BUS_JOB_COMPLETED, self._on_job_completed_event, replay_last=True)

    def _subscribe_bus(self, topic: Optional[str], handler: Callable[[Any], None], replay_last: bool = False) -> None:
        if not (self.bus and topic):
            return

        def _wrapped(envelope):
            self._bus_dispatch_bridge.envelope_dispatched.emit(handler, envelope)

        sub_id = self.bus.subscribe(topic, _wrapped, replay_last=replay_last)
        self._bus_subscriptions.append(sub_id)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.bus:
            for sub_id in self._bus_subscriptions:
                self.bus.unsubscribe(sub_id)
            self._bus_subscriptions.clear()
        super().closeEvent(event)

    def _set_job_state(
        self,
        *,
        job_id: Optional[str],
        pack_id: Optional[str],
        action: Optional[str],
        running: bool,
    ) -> None:
        self.pending_job_id = job_id
        self.pending_pack_id = pack_id
        self.pending_action = action if running else None
        self.install_btn.setEnabled(not running)
        self.uninstall_btn.setEnabled(not running)
        if not running:
            self._stop_job_poll_timer()

    def _start_job_poll_timer(self) -> None:
        if not (self.bus and self.pending_job_id):
            return
        self._stop_job_poll_timer()
        timer = QtCore.QTimer(self)
        timer.setInterval(800)
        timer.timeout.connect(self._poll_job_status)
        self._job_poll_deadline = time.monotonic() + 45.0
        self._job_poll_timer = timer
        timer.start()

    def _stop_job_poll_timer(self) -> None:
        if self._job_poll_timer:
            self._job_poll_timer.stop()
            self._job_poll_timer.deleteLater()
            self._job_poll_timer = None
        self._job_poll_deadline = 0.0

    def _poll_job_status(self) -> None:
        if not (self.bus and self.pending_job_id):
            self._stop_job_poll_timer()
            return
        if self._job_poll_deadline and time.monotonic() > self._job_poll_deadline:
            self._stop_job_poll_timer()
            self._show_progress(
                "Pack Job Timeout",
                f"{(self.pending_action or 'Pack').title()} {self.pending_pack_id or 'pack'}: timed out",
                running=False,
                ok=False,
            )
            self._set_job_state(job_id=None, pack_id=None, action=None, running=False)
            return
        try:
            response = self.bus.request(
                BUS_JOBS_GET_REQUEST,
                {"job_id": self.pending_job_id},
                source="app_ui",
                timeout_ms=800,
            )
        except Exception as exc:
            self._stop_job_poll_timer()
            self._show_progress(
                "Pack Job",
                f"Job status failed: {exc}",
                running=False,
                ok=False,
            )
            self._set_job_state(job_id=None, pack_id=None, action=None, running=False)
            return
        if not response.get("ok"):
            self._stop_job_poll_timer()
            self._show_progress(
                "Pack Job",
                f"Job status failed: {response.get('error') or 'unknown'}",
                running=False,
                ok=False,
            )
            self._set_job_state(job_id=None, pack_id=None, action=None, running=False)
            return
        job = response.get("job") or {}
        status = str(job.get("status") or "").upper()
        ok_flag = job.get("ok")
        terminal = status in ("COMPLETED", "FAILED") or ok_flag is not None
        if not terminal:
            return
        payload = {
            "job_id": self.pending_job_id,
            "job_type": job.get("job_type"),
            "ok": ok_flag,
            "error": job.get("error"),
        }
        self._on_job_completed_event(SimpleNamespace(payload=payload))

    def _on_job_progress_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if payload.get("job_id") != self.pending_job_id:
            return
        percent = payload.get("percent")
        stage = payload.get("stage") or "Working"
        percent_text = f"{percent:.1f}%" if isinstance(percent, (int, float)) else ""
        label = self.pending_pack_id or "pack"
        self._show_progress(
            "Pack Progress",
            f"{(self.pending_action or 'pack').title()} {label}: {percent_text} {stage}".strip(),
            running=True,
        )

    def _on_job_completed_event(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", None) or {}
        if payload.get("job_id") != self.pending_job_id:
            return
        ok = bool(payload.get("ok"))
        error = payload.get("error") or "failed"
        label = self.pending_pack_id or "pack"
        action = self.pending_action or "pack"
        summary = "OK" if ok else error
        self._show_progress(
            "Pack Result",
            f"{action.title()} {label}: {summary}",
            running=False,
            ok=ok,
        )
        self._set_job_state(job_id=None, pack_id=None, action=None, running=False)
        self._refresh_registry()
        self.refresh()
        if self.on_packs_changed:
            try:
                self.on_packs_changed()
            except Exception:
                pass

    def _set_banner(self, text: str) -> None:
        if not text:
            self.banner.setVisible(False)
            self.banner.setText("")
        else:
            self.banner.setText(text)
            self.banner.setVisible(True)
