from __future__ import annotations

from pathlib import Path

from app_ui.screens.system_health import _format_size_bytes, _session_summary_from_entry


def test_session_summary_from_entry_complete_meta() -> None:
    entry = {
        "session_id": "s1",
        "path": Path("data/workspaces/default/codesee/sessions/s1"),
        "status": "COMPLETE",
        "started_at_ms_epoch": 1700000000000,
        "size_bytes": 2 * 1024 * 1024,
        "meta": {
            "schema_version": 1,
            "status": "COMPLETE",
            "started_at_ms_epoch": 1700000000000,
            "ended_at_ms_epoch": 1700000300000,
            "counts": {
                "records": 10,
                "events": 4,
                "deltas": 3,
                "keyframes": 3,
                "corrupt_lines": 1,
            },
        },
    }

    summary = _session_summary_from_entry(entry)
    assert summary["session_id"] == "s1"
    assert summary["status"] == "COMPLETE"
    assert summary["schema_version"] == "1"
    assert summary["records"] == 10
    assert summary["events"] == 4
    assert summary["deltas"] == 3
    assert summary["keyframes"] == 3
    assert summary["corrupt_lines"] == 1
    assert summary["size_bytes"] == 2 * 1024 * 1024
    assert summary["size_text"] == "2.00 MB"
    assert summary["started"] != "-"
    assert summary["ended"] != "-"


def test_session_summary_from_entry_incomplete_defaults() -> None:
    entry = {
        "session_id": "s2",
        "path": Path("data/workspaces/default/codesee/sessions/s2"),
        "status": "INCOMPLETE",
        "size_bytes": "bad-value",
        "meta": {},
    }

    summary = _session_summary_from_entry(entry)
    assert summary["session_id"] == "s2"
    assert summary["status"] == "INCOMPLETE"
    assert summary["schema_version"] == "?"
    assert summary["records"] == 0
    assert summary["events"] == 0
    assert summary["deltas"] == 0
    assert summary["keyframes"] == 0
    assert summary["corrupt_lines"] == 0
    assert summary["started"] == "-"
    assert summary["ended"] == "-"
    assert summary["size_bytes"] == 0
    assert summary["size_text"] == "0 B"
    assert summary["path"].endswith("s2")


def test_format_size_bytes_units() -> None:
    assert _format_size_bytes(500) == "500 B"
    assert _format_size_bytes(4096) == "4.0 KB"
    assert _format_size_bytes(1048576) == "1.00 MB"
