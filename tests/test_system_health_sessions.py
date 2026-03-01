from __future__ import annotations

import os
from pathlib import Path

from app_ui.screens.system_health import (
    SESSION_TABLE_COLUMNS,
    SESSION_TABLE_DEFAULT_WIDTHS,
    SESSION_TABLE_MIN_WIDTHS,
    _format_size_bytes,
    _clamp_session_row_height,
    _load_session_table_layout,
    _load_session_display_names,
    _save_session_table_layout,
    _save_session_display_name,
    _clamp_session_header_height,
    _sanitize_session_display_name,
    _session_summary_from_entry,
)


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
    assert summary["reviewable"] is True


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
    assert summary["reviewable"] is False


def test_session_summary_from_entry_ignores_unknown_fields() -> None:
    entry = {
        "session_id": "s3",
        "status": "COMPLETE",
        "size_bytes": 1024,
        "meta": {
            "schema_version": 1,
            "status": "COMPLETE",
            "counts": {
                "records": 1,
                "events": 0,
                "deltas": 0,
                "keyframes": 0,
                "corrupt_lines": 0,
            },
            "future_field": {"x": 1},
        },
        "future_outer": ["ignore", "me"],
    }

    summary = _session_summary_from_entry(entry)
    assert summary["session_id"] == "s3"
    assert summary["status"] == "COMPLETE"
    assert summary["records"] == 1
    assert summary["reviewable"] is True


def test_format_size_bytes_units() -> None:
    assert _format_size_bytes(500) == "500 B"
    assert _format_size_bytes(4096) == "4.0 KB"
    assert _format_size_bytes(1048576) == "1.00 MB"


def test_session_table_columns_have_metric_designations() -> None:
    labels = [label for label, _tooltip in SESSION_TABLE_COLUMNS]
    assert labels == [
        "Session",
        "Status",
        "Started",
        "Ended",
        "Records",
        "Events",
        "Deltas",
        "Keyframes",
        "Corrupt",
        "Schema",
        "Size",
    ]
    metrics = {"Records", "Events", "Deltas", "Keyframes", "Corrupt", "Schema", "Size"}
    for label, tooltip in SESSION_TABLE_COLUMNS:
        assert isinstance(tooltip, str) and tooltip.strip()
        if label in metrics:
            text = tooltip.lower()
            assert (
                "count" in text
                or "size" in text
                or "schema" in text
                or label.lower() in text
            )


def test_session_display_name_roundtrip(tmp_path: Path) -> None:
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert _save_session_display_name("default", "s1", "My Session")
        names = _load_session_display_names("default")
        assert names["s1"] == "My Session"
    finally:
        os.chdir(cwd)


def test_session_display_name_blank_clears_alias(tmp_path: Path) -> None:
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert _save_session_display_name("default", "s1", "Alias")
        assert _save_session_display_name("default", "s1", "")
        names = _load_session_display_names("default")
        assert "s1" not in names
    finally:
        os.chdir(cwd)


def test_sanitize_session_display_name_collapses_and_limits() -> None:
    assert _sanitize_session_display_name("   hello   world   ") == "hello world"
    assert len(_sanitize_session_display_name("x" * 200)) == 72


def test_session_table_layout_roundtrip(tmp_path: Path) -> None:
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        widths = [w + 7 for w in SESSION_TABLE_DEFAULT_WIDTHS]
        assert _save_session_table_layout("default", widths, 40, 32)
        loaded = _load_session_table_layout("default")
        assert loaded["column_widths"] == widths
        assert loaded["header_height"] == 40
        assert loaded["row_height"] == 32
    finally:
        os.chdir(cwd)


def test_session_table_layout_sanitizes_invalid_values(tmp_path: Path) -> None:
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert _save_session_table_layout("default", [1, -2, 0], 999, 999)
        loaded = _load_session_table_layout("default")
        assert loaded["header_height"] == 64
        assert loaded["row_height"] == 26
        assert loaded["column_widths"][0] == SESSION_TABLE_MIN_WIDTHS[0]
        assert loaded["column_widths"][1] == SESSION_TABLE_DEFAULT_WIDTHS[1]
        assert loaded["column_widths"][2] == SESSION_TABLE_DEFAULT_WIDTHS[2]
    finally:
        os.chdir(cwd)


def test_clamp_session_header_height_clamps_to_range() -> None:
    assert _clamp_session_header_height(34) == 34
    assert _clamp_session_header_height("40") == 40
    assert _clamp_session_header_height("bad") == 34
    assert _clamp_session_header_height(31) == 31
    assert _clamp_session_header_height(5) == 24
    assert _clamp_session_header_height(500) == 64


def test_clamp_session_row_height_defaults_for_unknown_values() -> None:
    assert _clamp_session_row_height(26) == 26
    assert _clamp_session_row_height("32") == 32
    assert _clamp_session_row_height("bad") == 26
    assert _clamp_session_row_height(29) == 26
