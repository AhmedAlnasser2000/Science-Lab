from __future__ import annotations

import os
from pathlib import Path

from app_ui.codesee.runtime import session_schema, session_store
from app_ui.codesee.runtime.session_replay import (
    load_replay_session,
    nearest_seq_for_timestamp,
    seek_to_seq,
)


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


def test_timeline_indexes_and_nearest_seq_for_timestamp(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    root = _write_meta("default", "idx", started_ms=1)

    session_store.records_path(root).write_text(
        "\n".join(
            [
                '{"seq":5,"type":"event","ts_ms_epoch":7000,"ts_utc":"2026-02-24T10:00:07Z","tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:07","kind":"e5","severity":"info","message":"e5"}',
                '{"seq":1,"type":"event","ts_ms_epoch":1000,"ts_utc":"2026-02-24T10:00:01Z","tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:01","kind":"e1","severity":"info","message":"e1"}',
                '{"seq":2,"type":"event","ts_ms_epoch":2500,"ts_utc":"2026-02-24T10:00:02Z","tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:02","kind":"e2","severity":"info","message":"e2"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    timeline = load_replay_session(root)

    assert timeline.ordered_seqs == [1, 2, 5]
    assert sorted(timeline.seq_index.keys()) == [1, 2, 5]
    assert nearest_seq_for_timestamp(timeline, 500) == 1
    assert nearest_seq_for_timestamp(timeline, 2600) == 2
    assert nearest_seq_for_timestamp(timeline, 6400) == 5


def test_seek_to_seq_uses_nearest_prior_keyframe_then_applies_deltas(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    root = _write_meta("default", "seek-ok", started_ms=1)

    session_store.write_json(
        session_store.keyframe_path(root, 1),
        {
            "schema_version": session_schema.SCHEMA_VERSION,
            "keyframe_seq": 1,
            "snapshot": {
                "monitor_state": {
                    "system:app_ui": {
                        "state": "INACTIVE",
                        "active": False,
                        "stuck": False,
                        "fatal": False,
                    }
                },
                "trace_state": {
                    "active_trace_id": None,
                    "edges": [],
                    "nodes": [],
                    "edge_count": 0,
                    "node_count": 0,
                },
            },
        },
    )
    session_store.write_json(
        session_store.keyframe_path(root, 2),
        {
            "schema_version": session_schema.SCHEMA_VERSION,
            "keyframe_seq": 2,
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
                    "active_trace_id": "trace-a",
                    "edges": [["system:runtime_bus", "system:app_ui"]],
                    "nodes": ["system:app_ui", "system:runtime_bus"],
                    "edge_count": 1,
                    "node_count": 2,
                },
            },
        },
    )

    session_store.records_path(root).write_text(
        "\n".join(
            [
                '{"seq":2,"type":"keyframe_ref","ts_ms_epoch":2000,"ts_utc":"2026-02-24T10:00:02Z","tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:02","keyframe_seq":1,"filename":"000001.json"}',
                '{"seq":3,"type":"delta","ts_ms_epoch":3000,"ts_utc":"2026-02-24T10:00:03Z","tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:03","delta_type":"monitor.state.transition","node_id":"system:app_ui","after_ref":"RUNNING","metadata":{"after":{"state":"RUNNING","active":true,"stuck":false,"fatal":false}}}',
                '{"seq":4,"type":"delta","ts_ms_epoch":4000,"ts_utc":"2026-02-24T10:00:04Z","tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:04","delta_type":"trace.state.transition","node_id":"trace","after_ref":"trace-a","metadata":{"after":{"active_trace_id":"trace-a","edges":[["system:runtime_bus","system:app_ui"]],"nodes":["system:app_ui","system:runtime_bus"]}}}',
                '{"seq":5,"type":"keyframe_ref","ts_ms_epoch":5000,"ts_utc":"2026-02-24T10:00:05Z","tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:05","keyframe_seq":2,"filename":"000002.json"}',
                '{"seq":6,"type":"delta","ts_ms_epoch":6000,"ts_utc":"2026-02-24T10:00:06Z","tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:06","delta_type":"monitor.state.transition","node_id":"system:app_ui","after_ref":"ERROR","metadata":{"after":{"state":"ERROR","active":true,"stuck":false,"fatal":true}}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    timeline = load_replay_session(root)

    result = seek_to_seq(timeline, 6)
    assert result.resolved_seq == 6
    assert result.base_keyframe_record_seq == 5
    assert result.base_keyframe_seq == 2
    assert result.applied_records == 1
    assert result.monitor_state["system:app_ui"]["state"] == "ERROR"
    assert bool(result.monitor_state["system:app_ui"]["fatal"]) is True
    assert result.trace_state["active_trace_id"] == "trace-a"

    earlier = seek_to_seq(timeline, 4)
    assert earlier.resolved_seq == 4
    assert earlier.base_keyframe_record_seq == 2
    assert earlier.base_keyframe_seq == 1
    assert earlier.applied_records == 2
    assert earlier.monitor_state["system:app_ui"]["state"] == "RUNNING"
    assert earlier.trace_state["active_trace_id"] == "trace-a"


def test_seek_to_seq_falls_back_when_keyframe_missing(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    root = _write_meta("default", "seek-fallback", started_ms=1)

    session_store.records_path(root).write_text(
        "\n".join(
            [
                '{"seq":2,"type":"keyframe_ref","ts_ms_epoch":2000,"ts_utc":"2026-02-24T10:00:02Z","tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:02","keyframe_seq":1,"filename":"000001.json"}',
                '{"seq":3,"type":"delta","ts_ms_epoch":3000,"ts_utc":"2026-02-24T10:00:03Z","tz_offset_minutes":180,"ts_local":"2026-02-24 13:00:03","delta_type":"monitor.state.transition","node_id":"system:app_ui","after_ref":"RUNNING","metadata":{"after":{"state":"RUNNING","active":true,"stuck":false,"fatal":false}}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    timeline = load_replay_session(root)
    result = seek_to_seq(timeline, 10)

    assert result.resolved_seq == 3
    assert result.base_keyframe_record_seq == 0
    assert result.base_keyframe_seq is None
    assert result.applied_records == 2
    assert result.monitor_state["system:app_ui"]["state"] == "RUNNING"
    assert any("keyframe load failed" in item for item in result.warnings)
