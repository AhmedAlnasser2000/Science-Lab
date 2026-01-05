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
