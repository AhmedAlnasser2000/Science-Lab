from __future__ import annotations

from pathlib import Path

from diagnostics.pillars_report import build_report, run_smoke_checks, write_report


def test_smoke_report_writes(temp_output_dir: Path) -> None:
    results = run_smoke_checks()
    report = build_report(results)
    target = write_report(report, temp_output_dir)
    assert target.exists()
    assert target.read_text()
    statuses = {r["status"] for r in report["results"]}
    assert statuses.issubset({"PASS", "SKIP", "FAIL"})


def test_schema_fields_present(temp_output_dir: Path) -> None:
    report = build_report(run_smoke_checks())
    required = {"report_version", "generated_at", "app_version", "build_id", "results"}
    assert required.issubset(report.keys())
    target = write_report(report, temp_output_dir)
    loaded = target.read_text()
    assert "report_version" in loaded
