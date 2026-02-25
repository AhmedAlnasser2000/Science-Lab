from __future__ import annotations

import os
from pathlib import Path

from app_ui.codesee.runtime import session_schema, session_store


def _write_meta(workspace_id: str, session_id: str, *, started_ms: int, status: str = "COMPLETE") -> Path:
    root = session_store.ensure_session_layout(workspace_id, session_id)
    session_store.write_json(
        session_store.meta_path(root),
        {
            "schema_version": session_schema.SCHEMA_VERSION,
            "session_id": session_id,
            "workspace_id": workspace_id,
            "started_at_utc": "2026-01-01T00:00:00Z",
            "started_at_local": "2026-01-01 03:00:00",
            "started_at_ms_epoch": int(started_ms),
            "tz_offset_minutes": 180,
            "status": status,
            "counts": session_schema.default_counts(),
        },
    )
    return root


def _write_blob(path: Path, size_bytes: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * max(0, int(size_bytes)))


def test_prune_by_count_removes_oldest_completed_first(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    workspace = "default"
    for idx in range(1, 5):
        root = _write_meta(workspace, f"s{idx}", started_ms=idx)
        session_store.append_jsonl(session_store.records_path(root), {"seq": idx, "type": "event"})

    result = session_store.prune_sessions(
        workspace,
        max_sessions_per_workspace=2,
        max_total_mb_per_workspace=1024,
    )
    assert result["pruned"] == ["s1", "s2"]
    remaining = {entry["session_id"] for entry in session_store.list_sessions(workspace)}
    assert remaining == {"s3", "s4"}


def test_prune_by_size_removes_oldest_until_within_cap(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    workspace = "default"
    for idx in range(1, 4):
        root = _write_meta(workspace, f"s{idx}", started_ms=idx)
        _write_blob(root / "records.jsonl", 700 * 1024)

    result = session_store.prune_sessions(
        workspace,
        max_sessions_per_workspace=20,
        max_total_mb_per_workspace=1,
    )
    assert result["pruned"] == ["s1", "s2"]
    remaining = [entry["session_id"] for entry in session_store.list_sessions(workspace)]
    assert remaining == ["s3"]
    assert result["remaining_bytes"] <= 1024 * 1024


def test_prune_mixed_caps_honors_both_count_and_size(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    workspace = "default"
    for idx in range(1, 4):
        root = _write_meta(workspace, f"s{idx}", started_ms=idx)
        _write_blob(root / "records.jsonl", 600 * 1024)

    result = session_store.prune_sessions(
        workspace,
        max_sessions_per_workspace=2,
        max_total_mb_per_workspace=1,
    )
    assert result["pruned"] == ["s1", "s2"]
    remaining = [entry["session_id"] for entry in session_store.list_sessions(workspace)]
    assert remaining == ["s3"]
    assert result["remaining"] == 1
    assert result["remaining_bytes"] <= 1024 * 1024


def test_prune_never_deletes_locked_session(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    workspace = "default"
    s1 = _write_meta(workspace, "s1", started_ms=1)
    s2 = _write_meta(workspace, "s2", started_ms=2)
    s3 = _write_meta(workspace, "s3", started_ms=3)

    session_store.write_json(
        session_store.lock_path(s1),
        {"pid": 1234, "started_at_ms_epoch": 1, "session_id": "s1"},
    )
    for root in (s1, s2, s3):
        session_store.append_jsonl(session_store.records_path(root), {"seq": 1, "type": "event"})

    result = session_store.prune_sessions(
        workspace,
        max_sessions_per_workspace=1,
        max_total_mb_per_workspace=1024,
    )
    assert "s1" not in result["pruned"]
    remaining = {entry["session_id"] for entry in session_store.list_sessions(workspace)}
    assert "s1" in remaining


def test_list_sessions_propagates_corrupt_lines_to_meta(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    workspace = "default"
    root = _write_meta(workspace, "s1", started_ms=1)
    session_store.records_path(root).write_text(
        '{"seq":1,"type":"event"}\nnot-json\n42\n',
        encoding="utf-8",
    )

    sessions = session_store.list_sessions(workspace)
    assert len(sessions) == 1
    counts = sessions[0]["meta"]["counts"]
    assert counts["corrupt_lines"] == 2

    stored_meta = session_store.read_json(session_store.meta_path(root))
    assert stored_meta is not None
    assert stored_meta["counts"]["corrupt_lines"] == 2


def test_list_sessions_marks_missing_or_partial_meta_incomplete(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    workspace = "default"
    missing_root = session_store.ensure_session_layout(workspace, "missing")
    session_store.append_jsonl(session_store.records_path(missing_root), {"seq": 1, "type": "event"})

    partial_root = session_store.ensure_session_layout(workspace, "partial")
    session_store.write_json(
        session_store.meta_path(partial_root),
        {
            "session_id": "partial",
            "workspace_id": workspace,
            "status": "COMPLETE",
        },
    )

    sessions = {entry["session_id"]: entry for entry in session_store.list_sessions(workspace)}
    assert "missing" in sessions
    assert "partial" in sessions
    assert sessions["missing"]["status"] == session_schema.SESSION_STATUS_INCOMPLETE
    assert sessions["partial"]["status"] == session_schema.SESSION_STATUS_INCOMPLETE
    assert sessions["partial"]["meta"]["counts"]["records"] == 0
    assert sessions["partial"]["meta"]["counts"]["corrupt_lines"] == 0


def test_list_sessions_marks_active_without_lock_incomplete(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    workspace = "default"
    root = _write_meta(
        workspace,
        "active-no-lock",
        started_ms=10,
        status=session_schema.SESSION_STATUS_ACTIVE,
    )

    sessions = {entry["session_id"]: entry for entry in session_store.list_sessions(workspace)}
    assert sessions["active-no-lock"]["status"] == session_schema.SESSION_STATUS_INCOMPLETE
    stored_meta = session_store.read_json(session_store.meta_path(root))
    assert stored_meta is not None
    assert stored_meta["status"] == session_schema.SESSION_STATUS_INCOMPLETE


def test_delete_session_respects_lock_and_active_guards(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    workspace = "default"
    root = _write_meta(workspace, "s1", started_ms=1)
    session_store.append_jsonl(session_store.records_path(root), {"seq": 1, "type": "event"})

    session_store.write_json(
        session_store.lock_path(root),
        {"pid": 999, "started_at_ms_epoch": 1, "session_id": "s1"},
    )
    locked = session_store.delete_session(workspace, "s1")
    assert locked["ok"] is False
    assert locked["reason"] == "locked"
    assert root.exists() is True

    session_store.lock_path(root).unlink()
    active = session_store.delete_session(workspace, "s1", active_session_id="s1")
    assert active["ok"] is False
    assert active["reason"] == "active"
    assert root.exists() is True

    deleted = session_store.delete_session(workspace, "s1")
    assert deleted["ok"] is True
    assert deleted["reason"] == "deleted"
    assert root.exists() is False
