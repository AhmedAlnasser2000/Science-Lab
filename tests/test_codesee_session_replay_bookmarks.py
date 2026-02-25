from __future__ import annotations

import os
from pathlib import Path

from app_ui.codesee.runtime import session_schema, session_store
from app_ui.codesee.storage import session_store as bookmark_store


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


def test_read_bookmarks_returns_defaults_when_sidecar_missing(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    root = _write_meta("default", "bookmark-missing")

    payload = bookmark_store.read_bookmarks(root)

    assert payload["schema_version"] == bookmark_store.BOOKMARKS_SCHEMA_VERSION
    assert payload["session_id"] == "bookmark-missing"
    assert payload["workspace_id"] == "default"
    assert payload["updated_at_ms_epoch"] == 0
    assert payload["bookmarks"] == []


def test_write_bookmarks_roundtrip_and_sorts_by_seq(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    root = _write_meta("default", "bookmark-roundtrip")

    written = bookmark_store.write_bookmarks(
        root,
        {
            "schema_version": 999,
            "session_id": "wrong-id",
            "workspace_id": "wrong-workspace",
            "updated_at_ms_epoch": 1,
            "bookmarks": [
                {"bookmark_id": "b2", "label": "later", "seq": 9, "ts_ms_epoch": 9000, "created_at_ms_epoch": 3},
                {"bookmark_id": "b1", "label": "first", "seq": 2, "ts_ms_epoch": 2000, "created_at_ms_epoch": 2},
            ],
        },
    )

    assert written["session_id"] == "bookmark-roundtrip"
    assert written["workspace_id"] == "default"
    assert written["updated_at_ms_epoch"] > 0
    assert [item["bookmark_id"] for item in written["bookmarks"]] == ["b1", "b2"]

    loaded = bookmark_store.read_bookmarks(root)
    assert [item["bookmark_id"] for item in loaded["bookmarks"]] == ["b1", "b2"]
    assert loaded["bookmarks"][0]["seq"] == 2
    assert loaded["bookmarks"][1]["seq"] == 9


def test_read_bookmarks_normalizes_invalid_entries(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    root = _write_meta("default", "bookmark-normalize")
    session_store.write_json(
        bookmark_store.bookmarks_path(root),
        {
            "schema_version": 7,
            "session_id": "bookmark-normalize",
            "workspace_id": "default",
            "updated_at_ms_epoch": "bad",
            "bookmarks": [
                {"bookmark_id": "ok", "label": "ok", "seq": 5, "ts_ms_epoch": 5000},
                {"bookmark_id": "bad-seq", "label": "bad", "seq": 0},
                {"bookmark_id": "ok", "label": "duplicate", "seq": 7},
                "not-an-object",
                {"label": "", "seq": 2, "ts_ms_epoch": 2000},
            ],
        },
    )

    payload = bookmark_store.read_bookmarks(root)

    assert payload["schema_version"] == bookmark_store.BOOKMARKS_SCHEMA_VERSION
    assert payload["updated_at_ms_epoch"] == 0
    assert len(payload["bookmarks"]) == 2
    assert [item["bookmark_id"] for item in payload["bookmarks"]] == ["bookmark_5", "ok"]
    assert payload["bookmarks"][0]["seq"] == 2
