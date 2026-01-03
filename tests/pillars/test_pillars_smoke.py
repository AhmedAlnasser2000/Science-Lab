from __future__ import annotations

from pathlib import Path

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
