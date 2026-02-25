from __future__ import annotations

import hashlib
import os
from pathlib import Path

from PyQt6 import QtWidgets, sip

from app_ui.codesee.runtime import session_schema, session_store
from app_ui.codesee.runtime.events import CodeSeeEvent, EVENT_APP_ERROR
from app_ui.codesee.screen import CodeSeeScreen, LENS_ATLAS, SOURCE_DEMO
from app_ui.codesee.storage import session_store as bookmark_store


_APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _make_screen() -> CodeSeeScreen:
    return CodeSeeScreen(
        on_back=lambda: None,
        workspace_info_provider=lambda: {"id": "default"},
        allow_detach=False,
    )


def _write_meta(workspace_id: str, session_id: str) -> Path:
    root = session_store.ensure_session_layout(workspace_id, session_id)
    session_store.write_json(
        session_store.meta_path(root),
        {
            "schema_version": session_schema.SCHEMA_VERSION,
            "session_id": session_id,
            "workspace_id": workspace_id,
            "started_at_utc": "2026-02-24T10:00:00Z",
            "started_at_local": "2026-02-24 13:00:00",
            "started_at_ms_epoch": 1000,
            "tz_offset_minutes": 180,
            "status": session_schema.SESSION_STATUS_COMPLETE,
            "counts": session_schema.default_counts(),
        },
    )
    return root


def _write_linear_records(root: Path, *, count: int) -> None:
    lines = []
    for idx in range(int(count)):
        seq = idx + 1
        ts_ms = 1000 + (idx * 1000)
        second = seq % 60
        lines.append(
            (
                f'{{"seq":{seq},"type":"event","ts_ms_epoch":{ts_ms},'
                f'"ts_utc":"2026-02-24T10:00:{second:02d}Z","tz_offset_minutes":180,'
                f'"ts_local":"2026-02-24 13:00:{second:02d}",'
                f'"kind":"event.{seq}","severity":"info","message":"event-{seq}"}}'
            )
        )
    session_store.records_path(root).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_replay_state_session(workspace_id: str, session_id: str) -> Path:
    root = _write_meta(workspace_id, session_id)
    session_store.write_json(
        session_store.keyframe_path(root, 1),
        {
            "schema_version": session_schema.SCHEMA_VERSION,
            "keyframe_seq": 1,
            "snapshot": {
                "monitor_state": {
                    "system:app_ui": {
                        "state": "RUNNING",
                        "active": True,
                        "stuck": False,
                        "fatal": False,
                    }
                },
                "trace_state": {
                    "active_trace_id": "trace-replay",
                    "edges": [["system:runtime_bus", "system:app_ui"]],
                    "nodes": ["system:runtime_bus", "system:app_ui"],
                    "edge_count": 1,
                    "node_count": 2,
                },
            },
        },
    )
    session_store.records_path(root).write_text(
        "\n".join(
            [
                '{"seq":1,"type":"event","ts_ms_epoch":1000,"ts_utc":"2026-02-24T10:00:01Z","tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:01","kind":"event.1","severity":"info","message":"e1"}',
                '{"seq":2,"type":"keyframe_ref","ts_ms_epoch":2000,"ts_utc":"2026-02-24T10:00:02Z","tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:02","keyframe_seq":1,"filename":"000001.json"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_replay_api_surface_enters_and_exits_mode(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    root = _write_meta("default", "replay-s1")
    _write_linear_records(root, count=4)

    screen = _make_screen()
    try:
        screen._refresh_replay_sessions()
        assert screen.enter_replay_mode("replay-s1") is True
        assert screen._replay_mode_active is True
        assert "Exit Replay first" in screen.recording_start_btn.toolTip()
        assert "Play/pause replay timeline" in screen.replay_play_toggle.toolTip()

        seek_result = screen.set_replay_seq(999)
        assert seek_result.resolved_seq == 4
        assert screen.set_replay_speed(2.0) == 2.0
        assert "Replay" in screen.replay_status_label.text()
        assert "Recording controls locked" in screen.replay_status_label.text()

        screen.exit_replay_mode()
        assert screen._replay_mode_active is False
        assert "Replay: off" in screen.replay_status_label.text()
    finally:
        if not sip.isdeleted(screen):
            screen.cleanup()


def test_replay_mode_buffers_live_events_without_mutating_live_overlay(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    root = _write_meta("default", "replay-s2")
    _write_linear_records(root, count=3)

    screen = _make_screen()
    try:
        assert screen.enter_replay_mode("replay-s2") is True
        before_monitor = screen._monitor.snapshot_states()
        before_events = dict(screen._events_by_node)

        event = CodeSeeEvent(
            ts="2026-02-24 13:00:05",
            kind=EVENT_APP_ERROR,
            severity="error",
            message="boom",
            node_ids=["system:app_ui"],
            source="runtime",
        )
        screen._on_runtime_event(event)

        assert screen._replay_buffered_live_count == 1
        assert screen._events_by_node == before_events
        assert screen._monitor.snapshot_states() == before_monitor
        assert "Live paused (1)" in screen.replay_status_label.text()
    finally:
        if not sip.isdeleted(screen):
            screen.cleanup()


def test_replay_controls_support_speed_jump_and_slider(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    root = _write_meta("default", "replay-s3")
    _write_linear_records(root, count=12)

    screen = _make_screen()
    try:
        assert screen.enter_replay_mode("replay-s3") is True

        speed_index = screen.replay_speed_combo.findData(4.0)
        assert speed_index >= 0
        screen.replay_speed_combo.setCurrentIndex(speed_index)
        assert screen._replay_controller is not None
        assert screen._replay_controller.snapshot.speed_multiplier == 4.0
        screen.replay_jump_seconds_spin.setValue(2)
        assert screen.replay_jump_back_btn.text() == "-2s"
        assert screen.replay_jump_forward_btn.text() == "+2s"

        initial_seq = screen._replay_controller.snapshot.current_seq
        screen._on_replay_jump_forward()
        jumped_seq = screen._replay_controller.snapshot.current_seq
        assert jumped_seq == min(initial_seq + 2, screen.replay_seq_slider.maximum())

        screen._on_replay_jump_back()
        assert screen._replay_controller.snapshot.current_seq == initial_seq

        target_seq = screen.replay_seq_slider.maximum()
        screen.replay_seq_slider.setValue(target_seq)
        assert screen._replay_controller.snapshot.current_seq == target_seq
    finally:
        if not sip.isdeleted(screen):
            screen.cleanup()


def test_replay_trail_focus_uses_replay_monitor_trace_state(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    _write_replay_state_session("default", "replay-trail")

    screen = _make_screen()
    try:
        assert screen.enter_replay_mode("replay-trail") is True
        screen._source = SOURCE_DEMO
        screen._lens = LENS_ATLAS
        screen._trail_focus_enabled = True
        screen.set_replay_seq(2)
        screen._apply_trail_focus_overlay(now=123.0)

        assert "module.ui" in screen.scene._trail_focus_nodes
        assert "module.runtime_bus" in screen.scene._trail_focus_nodes
        assert screen.scene._trail_node_opacity.get("module.ui", 0.0) >= 0.85
    finally:
        if not sip.isdeleted(screen):
            screen.cleanup()


def test_recording_controls_start_pause_stop(tmp_path: Path) -> None:
    os.chdir(tmp_path)

    screen = _make_screen()
    try:
        assert screen.replay_enter_btn.text() == "Review Session"
        first_session = screen._current_recording_session_id()
        assert first_session
        assert screen._session_recording_paused is False

        screen.recording_pause_btn.setChecked(True)
        assert screen._session_recording_paused is True
        assert "paused" in screen.replay_status_label.text().lower()

        screen.recording_pause_btn.setChecked(False)
        assert screen._session_recording_paused is False

        screen._on_recording_stop_clicked()
        assert screen._current_recording_session_id() is None
        assert "Recording stopped" in screen.replay_status_label.text()

        screen._on_recording_start_clicked()
        second_session = screen._current_recording_session_id()
        assert second_session
        assert second_session != first_session
        assert "Recording active" in screen.replay_status_label.text()
    finally:
        if not sip.isdeleted(screen):
            screen.cleanup()


def test_replay_delete_session_button_removes_selected(tmp_path: Path, monkeypatch) -> None:
    os.chdir(tmp_path)
    root = _write_meta("default", "delete-me")
    _write_linear_records(root, count=2)

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *args, **kwargs: QtWidgets.QMessageBox.StandardButton.Yes,
    )

    screen = _make_screen()
    try:
        screen._refresh_replay_sessions()
        idx = screen.replay_session_combo.findData("delete-me")
        assert idx >= 0
        screen.replay_session_combo.setCurrentIndex(idx)
        screen._on_delete_replay_session_clicked()
        assert session_store.session_dir("default", "delete-me").exists() is False
    finally:
        if not sip.isdeleted(screen):
            screen.cleanup()


def test_replay_bookmark_crud_and_jump(tmp_path: Path, monkeypatch) -> None:
    os.chdir(tmp_path)
    root = _write_meta("default", "bookmark-ui")
    _write_linear_records(root, count=8)

    prompts = [("Alpha", True), ("Alpha-updated", True)]
    monkeypatch.setattr(
        QtWidgets.QInputDialog,
        "getText",
        lambda *args, **kwargs: prompts.pop(0),
    )

    screen = _make_screen()
    try:
        assert screen.enter_replay_mode("bookmark-ui") is True
        screen.set_replay_seq(4)
        screen._on_replay_add_bookmark_clicked()
        assert len(screen._replay_bookmarks) == 1
        saved = bookmark_store.read_bookmarks(root)
        assert len(saved["bookmarks"]) == 1
        assert saved["bookmarks"][0]["label"] == "Alpha"
        assert saved["bookmarks"][0]["seq"] == 4

        screen.set_replay_seq(8)
        screen.replay_bookmark_combo.setCurrentIndex(0)
        screen._on_replay_jump_bookmark_clicked()
        assert screen._replay_controller is not None
        assert screen._replay_controller.snapshot.current_seq == 4

        screen.set_replay_seq(6)
        screen._on_replay_update_bookmark_clicked()
        updated = bookmark_store.read_bookmarks(root)
        assert len(updated["bookmarks"]) == 1
        assert updated["bookmarks"][0]["label"] == "Alpha-updated"
        assert updated["bookmarks"][0]["seq"] == 6

        screen._on_replay_delete_bookmark_clicked()
        after_delete = bookmark_store.read_bookmarks(root)
        assert after_delete["bookmarks"] == []
    finally:
        if not sip.isdeleted(screen):
            screen.cleanup()


def test_replay_actions_only_mutate_bookmarks_sidecar(tmp_path: Path, monkeypatch) -> None:
    os.chdir(tmp_path)
    root = _write_replay_state_session("default", "mutation-boundary")
    meta_path = session_store.meta_path(root)
    records_path = session_store.records_path(root)
    keyframe = session_store.keyframe_path(root, 1)

    before_meta = _sha256(meta_path)
    before_records = _sha256(records_path)
    before_keyframe = _sha256(keyframe)

    prompts = [("Boundary Mark", True), ("Boundary Mark Updated", True)]
    monkeypatch.setattr(
        QtWidgets.QInputDialog,
        "getText",
        lambda *args, **kwargs: prompts.pop(0),
    )

    screen = _make_screen()
    try:
        assert screen.enter_replay_mode("mutation-boundary") is True
        screen.set_replay_seq(2)
        screen._on_replay_play_toggled(True)
        screen._on_replay_tick()
        screen._on_replay_play_toggled(False)
        screen._on_replay_jump_forward()
        screen._on_replay_jump_back()
        screen._on_replay_add_bookmark_clicked()
        screen._on_replay_update_bookmark_clicked()
        screen._on_replay_delete_bookmark_clicked()
    finally:
        if not sip.isdeleted(screen):
            screen.cleanup()

    assert _sha256(meta_path) == before_meta
    assert _sha256(records_path) == before_records
    assert _sha256(keyframe) == before_keyframe
    bookmarks = bookmark_store.read_bookmarks(root)
    assert isinstance(bookmarks.get("bookmarks"), list)
