from __future__ import annotations

import os
from pathlib import Path

from app_ui.codesee.runtime import session_schema, session_store
from app_ui.codesee.runtime.session_replay import load_replay_session


def _write_meta(workspace_id: str, session_id: str, *, started_ms: int = 1) -> Path:
    root = session_store.ensure_session_layout(workspace_id, session_id)
    session_store.write_json(
        session_store.meta_path(root),
        {
            "schema_version": session_schema.SCHEMA_VERSION,
            "session_id": session_id,
            "workspace_id": workspace_id,
            "started_at_utc": "2026-02-24T10:00:00Z",
            "started_at_local": "2026-02-24 13:00:00",
            "started_at_ms_epoch": int(started_ms),
            "tz_offset_minutes": 180,
            "status": session_schema.SESSION_STATUS_COMPLETE,
            "counts": session_schema.default_counts(),
        },
    )
    return root


def test_load_replay_session_sorts_by_seq_and_loads_keyframes(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    root = _write_meta("default", "s1", started_ms=10)

    session_store.write_json(
        session_store.keyframe_path(root, 1),
        {
            "schema_version": session_schema.SCHEMA_VERSION,
            "keyframe_seq": 1,
            "snapshot": {
                "monitor_state": {"system:app_ui": {"state": "RUNNING"}},
                "trace_state": {"active_trace_id": "trace-a"},
            },
        },
    )

    session_store.records_path(root).write_text(
        "\n".join(
            [
                '{"seq":5,"type":"delta","ts_utc":"2026-02-24T10:00:05Z","ts_ms_epoch":5000,"tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:05","delta_type":"monitor.state.transition","metadata":{}}',
                '{"seq":2,"type":"event","ts_utc":"2026-02-24T10:00:02Z","ts_ms_epoch":2000,"tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:02","kind":"bus.request","severity":"info","message":"req"}',
                '{"seq":4,"type":"keyframe_ref","ts_utc":"2026-02-24T10:00:04Z","ts_ms_epoch":4000,"tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:04","keyframe_seq":1,"filename":"000001.json"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    timeline = load_replay_session(root)

    assert [frame.seq for frame in timeline.frames] == [2, 4, 5]
    assert timeline.session_id == "s1"
    assert timeline.workspace_id == "default"
    assert timeline.corrupt_lines == 0
    assert timeline.keyframes[1]["snapshot"]["trace_state"]["active_trace_id"] == "trace-a"
    assert timeline.warnings == []


def test_load_replay_session_tolerates_partial_artifacts(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    root = session_store.ensure_session_layout("default", "broken")

    session_store.records_path(root).write_text(
        "\n".join(
            [
                '{"seq":3,"type":"event","ts_utc":"2026-02-24T10:00:03Z","ts_ms_epoch":3000,"tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:03","kind":"bus.request","severity":"info","message":"ok"}',
                "not-json",
                '{"seq":"bad","type":"event","ts_ms_epoch":100}',
                '{"seq":2,"type":"keyframe_ref","ts_ms_epoch":2000,"keyframe_seq":1,"filename":"000001.json"}',
                '{"seq":1,"ts_ms_epoch":1000}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    timeline = load_replay_session(root)

    assert timeline.session_id == "broken"
    assert timeline.workspace_id == "default"
    assert timeline.status == session_schema.SESSION_STATUS_INCOMPLETE
    assert timeline.corrupt_lines == 1
    assert [frame.seq for frame in timeline.frames] == [2, 3]
    assert 1 not in timeline.keyframes
    assert any("session_meta missing" in item for item in timeline.warnings)
    assert any("keyframe load failed" in item for item in timeline.warnings)
    assert any("records corrupt_lines=1" in item for item in timeline.warnings)
