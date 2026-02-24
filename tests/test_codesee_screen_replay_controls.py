from __future__ import annotations

import os
from pathlib import Path

from PyQt6 import QtWidgets, sip

from app_ui.codesee.runtime import session_schema, session_store
from app_ui.codesee.runtime.events import CodeSeeEvent, EVENT_APP_ERROR
from app_ui.codesee.screen import CodeSeeScreen


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


def test_replay_api_surface_enters_and_exits_mode(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    root = _write_meta("default", "replay-s1")
    _write_linear_records(root, count=4)

    screen = _make_screen()
    try:
        screen._refresh_replay_sessions()
        assert screen.enter_replay_mode("replay-s1") is True
        assert screen._replay_mode_active is True

        seek_result = screen.set_replay_seq(999)
        assert seek_result.resolved_seq == 4
        assert screen.set_replay_speed(2.0) == 2.0
        assert "Replay" in screen.replay_status_label.text()

        screen.exit_replay_mode()
        assert screen._replay_mode_active is False
        assert screen.replay_status_label.text() == "Replay: off"
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

        initial_seq = screen._replay_controller.snapshot.current_seq
        screen._on_replay_jump_forward()
        jumped_seq = screen._replay_controller.snapshot.current_seq
        assert jumped_seq >= initial_seq

        target_seq = screen.replay_seq_slider.maximum()
        screen.replay_seq_slider.setValue(target_seq)
        assert screen._replay_controller.snapshot.current_seq == target_seq
    finally:
        if not sip.isdeleted(screen):
            screen.cleanup()
