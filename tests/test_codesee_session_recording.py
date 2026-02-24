from __future__ import annotations

import os
from pathlib import Path

from app_ui.codesee.runtime.events import CodeSeeEvent
from app_ui.codesee.runtime.session_recording import SessionRecorder, SessionRecorderConfig
from app_ui.codesee.runtime import session_schema, session_store


class _Clock:
    def __init__(self, value: float = 1700001000.0) -> None:
        self.value = value

    def now(self) -> float:
        return self.value

    def step(self, seconds: float = 1.0) -> None:
        self.value += float(seconds)


def _event(kind: str = "bus.request") -> CodeSeeEvent:
    return CodeSeeEvent(
        ts="2026-02-24 10:00:00",
        kind=kind,
        severity="info",
        message=kind,
        node_ids=["system:app_ui"],
        payload={"trace_id": "trace-a"},
        source_node_id="system:runtime_bus",
        target_node_id="system:app_ui",
    )


def test_schema_record_build_and_validate() -> None:
    record = session_schema.build_event_record(seq=1, event=_event(), now=1700001234.5)
    assert record["type"] == session_schema.RECORD_EVENT
    assert "ts_utc" in record and "ts_ms_epoch" in record and "tz_offset_minutes" in record
    assert session_schema.validate_record(record) is True

    delta = session_schema.build_delta_record(seq=2, delta_type="monitor.state", node_id="system:app_ui", now=1700001234.5)
    assert session_schema.validate_record(delta) is True

    keyframe = session_schema.build_keyframe_ref_record(seq=3, keyframe_seq=1, filename="000001.json", now=1700001234.5)
    assert session_schema.validate_record(keyframe) is True


def test_session_recorder_writes_records_and_meta(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    clock = _Clock()
    recorder = SessionRecorder(SessionRecorderConfig(workspace_id="default"), now_provider=clock.now)

    meta_start = recorder.start_session(session_id="s1", build_info={"app_version": "5.5e"})
    assert meta_start.status == session_schema.SESSION_STATUS_ACTIVE

    recorder.record_event(_event("bus.request"))
    clock.step(1)
    recorder.record_state_delta({"delta_type": "monitor.state", "node_id": "system:app_ui", "metadata": {"state": "RUNNING"}})
    clock.step(1)
    recorder.record_keyframe({"graph_state_ref": "g1", "monitor_state": {"system:app_ui": "RUNNING"}})
    clock.step(1)
    meta_end = recorder.stop_session()

    assert meta_end.status == session_schema.SESSION_STATUS_COMPLETE
    root = recorder.session_dir()
    assert root is not None

    meta_path = session_store.meta_path(root)
    records_path = session_store.records_path(root)
    keyframe_path = session_store.keyframe_path(root, 1)

    assert meta_path.exists()
    assert records_path.exists()
    assert keyframe_path.exists()
    assert session_store.lock_path(root).exists() is False

    stored_meta = session_store.read_json(meta_path)
    assert stored_meta is not None
    assert session_schema.validate_session_meta(stored_meta) is True
    assert stored_meta["status"] == session_schema.SESSION_STATUS_COMPLETE
    assert stored_meta["counts"]["records"] == 3
    assert stored_meta["counts"]["events"] == 1
    assert stored_meta["counts"]["deltas"] == 1
    assert stored_meta["counts"]["keyframes"] == 1

    rows, corrupt = session_store.read_jsonl(records_path)
    assert corrupt == 0
    assert [row["type"] for row in rows] == [
        session_schema.RECORD_EVENT,
        session_schema.RECORD_DELTA,
        session_schema.RECORD_KEYFRAME_REF,
    ]
    assert [row["seq"] for row in rows] == [1, 2, 3]


def test_session_store_prune_respects_active_session(tmp_path: Path) -> None:
    os.chdir(tmp_path)

    w = "default"
    s1 = session_store.ensure_session_layout(w, "s1")
    s2 = session_store.ensure_session_layout(w, "s2")
    s3 = session_store.ensure_session_layout(w, "s3")

    session_store.write_json(
        session_store.meta_path(s1),
        {
            "schema_version": 1,
            "session_id": "s1",
            "workspace_id": w,
            "started_at_utc": "2026-01-01T00:00:00Z",
            "started_at_local": "2026-01-01 03:00:00",
            "started_at_ms_epoch": 1,
            "tz_offset_minutes": 180,
            "status": "COMPLETE",
            "counts": session_schema.default_counts(),
        },
    )
    session_store.write_json(
        session_store.meta_path(s2),
        {
            "schema_version": 1,
            "session_id": "s2",
            "workspace_id": w,
            "started_at_utc": "2026-01-01T00:00:01Z",
            "started_at_local": "2026-01-01 03:00:01",
            "started_at_ms_epoch": 2,
            "tz_offset_minutes": 180,
            "status": "COMPLETE",
            "counts": session_schema.default_counts(),
        },
    )
    session_store.write_json(
        session_store.meta_path(s3),
        {
            "schema_version": 1,
            "session_id": "s3",
            "workspace_id": w,
            "started_at_utc": "2026-01-01T00:00:02Z",
            "started_at_local": "2026-01-01 03:00:02",
            "started_at_ms_epoch": 3,
            "tz_offset_minutes": 180,
            "status": "COMPLETE",
            "counts": session_schema.default_counts(),
        },
    )

    for root in (s1, s2, s3):
        session_store.append_jsonl(session_store.records_path(root), {"dummy": True})

    result = session_store.prune_sessions(
        w,
        max_sessions_per_workspace=1,
        max_total_mb_per_workspace=1024,
        active_session_id="s3",
    )
    assert "s3" not in result["pruned"]
    remaining_ids = {entry["session_id"] for entry in session_store.list_sessions(w)}
    assert "s3" in remaining_ids


def test_read_jsonl_counts_corrupt_lines(tmp_path: Path) -> None:
    p = tmp_path / "records.jsonl"
    p.write_text('{"seq":1,"type":"event"}\nnot-json\n42\n{"seq":2,"type":"delta"}\n', encoding="utf-8")
    rows, corrupt = session_store.read_jsonl(p)
    assert len(rows) == 2
    assert corrupt == 2
