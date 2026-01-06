from __future__ import annotations

import json
from pathlib import Path

from tools import pillars_report
from tools.pillars_report import build_report, run_pillar_checks, write_report


def test_smoke_report_writes(temp_output_dir: Path) -> None:
    results = run_pillar_checks()
    report = build_report(results)
    target = write_report(report, temp_output_dir)
    assert target.exists()
    assert target.read_text()
    statuses = {r["status"] for r in report["results"]}
    assert statuses.issubset({"PASS", "SKIP", "FAIL"})


def test_schema_fields_present(temp_output_dir: Path) -> None:
    report = build_report(run_pillar_checks())
    required = {"report_version", "generated_at", "app_version", "build_id", "results"}
    assert required.issubset(report.keys())
    target = write_report(report, temp_output_dir)
    loaded = target.read_text()
    assert "report_version" in loaded


def test_report_has_12_pillars() -> None:
    report = build_report(run_pillar_checks())
    results = report["results"]
    assert len(results) == 12
    ids = sorted(r["id"] for r in results)
    assert ids == list(range(1, 13))


def test_pillar_3_ci_baseline_passes() -> None:
    report = build_report(run_pillar_checks())
    p3 = next(r for r in report["results"] if r["id"] == 3)
    assert p3["status"] == "PASS"


def test_pillar_10_hygiene_passes_or_skips() -> None:
    report = build_report(run_pillar_checks())
    p10 = next(r for r in report["results"] if r["id"] == 10)
    assert p10["status"] in {"PASS", "SKIP"}


def test_pillar_1_build_identity_passes() -> None:
    report = build_report(run_pillar_checks())
    p1 = next(r for r in report["results"] if r["id"] == 1)
    assert p1["status"] == "PASS"


def test_pillar_1_build_identity_fail(monkeypatch) -> None:
    monkeypatch.setattr(
        pillars_report,
        "get_build_info",
        lambda: {"app_version": "", "build_id": ""},
    )
    result = pillars_report._check_build_identity()
    assert result.status == "FAIL"


def test_pillar_9_config_layering_passes() -> None:
    report = build_report(run_pillar_checks())
    p9 = next(r for r in report["results"] if r["id"] == 9)
    assert p9["status"] == "PASS"


def test_pillar_9_config_layering_fail(monkeypatch, tmp_path: Path) -> None:
    import app_ui.config as config

    monkeypatch.setattr(config, "_DEFAULT_UI_CONFIG", {})
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "ui_config.json")
    result = pillars_report._check_config_layering()
    assert result.status == "FAIL"


def test_pillar_2_schema_manifest_passes() -> None:
    report = build_report(run_pillar_checks())
    p2 = next(r for r in report["results"] if r["id"] == 2)
    assert p2["status"] == "PASS"


def test_pillar_2_schema_manifest_fail(tmp_path: Path) -> None:
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "manifest_version": 1,
        "schemas": [
            {"path": "missing.schema.json", "schema_id": "missing", "schema_version": 1}
        ],
    }
    (schemas_dir / "schema_manifest.json").write_text(json.dumps(manifest, indent=2))
    result = pillars_report._check_schema_manifest(base_dir=tmp_path)
    assert result.status == "FAIL"


def test_run_pillars_does_not_systemexit(tmp_path: Path) -> None:
    from tools import pillars_harness

    report_path = pillars_harness.run_pillars(tmp_path)
    assert report_path.exists()


def test_pillars_thread_ref_cleared_on_thread_finished_only() -> None:
    import inspect
    from app_ui.screens.system_health import SystemHealthScreen

    finished_src = inspect.getsource(SystemHealthScreen._on_pillars_run_finished)
    error_src = inspect.getsource(SystemHealthScreen._on_pillars_run_error)
    assert "self._pillars_thread = None" not in finished_src
    assert "self._pillars_thread = None" not in error_src


def test_pillars_thread_finished_does_not_delete_worker() -> None:
    import inspect
    from app_ui.screens.system_health import SystemHealthScreen

    finished_src = inspect.getsource(SystemHealthScreen._on_pillars_thread_finished)
    assert "pillars_worker.deleteLater" not in finished_src


def test_pillar_5_crash_capture_pass(tmp_path: Path) -> None:
    result = pillars_report._check_crash_capture(
        base_dir=tmp_path, viewer_symbol="app_ui.screens.system_health.CrashViewerPanel"
    )
    assert result.status == "PASS"


def test_pillar_5_crash_capture_fail(tmp_path: Path) -> None:
    result = pillars_report._check_crash_capture(
        base_dir=tmp_path, viewer_symbol="missing.module.Symbol"
    )
    assert result.status == "FAIL"


def test_pillar_6_logging_pass(tmp_path: Path) -> None:
    result = pillars_report._check_logging_baseline(base_dir=tmp_path)
    assert result.status == "PASS"


def test_pillar_6_logging_fail(tmp_path: Path, monkeypatch) -> None:
    from diagnostics import logging_setup

    def fake_configure_logging(base_dir=None):
        return {
            "log_path": str(tmp_path.parent / "outside.log"),
            "format": "kv",
            "handlers": "file",
            "logger_name": "physicslab",
        }

    monkeypatch.setattr(logging_setup, "configure_logging", fake_configure_logging)
    result = pillars_report._check_logging_baseline(base_dir=tmp_path)
    assert result.status == "FAIL"


def test_pillar_7_telemetry_pass() -> None:
    result = pillars_report._check_telemetry_opt_in()
    assert result.status == "PASS"


def test_pillar_7_telemetry_fail(tmp_path: Path, monkeypatch) -> None:
    from diagnostics import telemetry

    monkeypatch.setattr(telemetry, "is_telemetry_enabled", lambda base_dir=None: True)
    result = pillars_report._check_telemetry_opt_in()
    assert result.status == "FAIL"


def test_pillar_8_tracing_pass() -> None:
    result = pillars_report._check_tracing_contract()
    assert result.status == "PASS"


def test_pillar_8_tracing_fail(monkeypatch) -> None:
    from diagnostics import tracing

    monkeypatch.setattr(tracing, "get_recent_spans", lambda: [])
    result = pillars_report._check_tracing_contract()
    assert result.status == "FAIL"
