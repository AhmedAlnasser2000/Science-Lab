from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from app_ui.versioning import get_build_info

REPORT_VERSION = 1

PILLAR_TITLES: List[Tuple[int, str]] = [
    (1, "Versioning & build identity"),
    (2, "Schema versions + migrations"),
    (3, "CI baseline (Windows-first)"),
    (4, "Release & packaging pipeline"),
    (5, "Crash capture + Safe Viewer"),
    (6, "Logging & structured events"),
    (7, "Telemetry / metrics (opt-in)"),
    (8, "Activity spans + runtime tracing contract"),
    (9, "Config layering & reproducibility"),
    (10, "Runtime data hygiene (data layout + .gitignore)"),
    (11, "Plugin/pack dependency metadata"),
    (12, "Security & capability boundaries"),
]


@dataclass
class PillarEntry:
    id: int
    title: str
    status: str
    reason: str
    evidence: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = (self.status or "").upper()
        data["pillar_id"] = self.id
        data["name"] = self.title
        return data


def _check_build_identity() -> PillarEntry:
    try:
        build = get_build_info()
    except Exception as exc:
        return PillarEntry(
            id=1,
            title=PILLAR_TITLES[0][1],
            status="FAIL",
            reason=f"Build identity failed: {exc}",
            evidence=["app_ui.versioning.get_build_info"],
        )
    app_version = (build or {}).get("app_version") or ""
    build_id = (build or {}).get("build_id") or ""
    if not app_version:
        return PillarEntry(
            id=1,
            title=PILLAR_TITLES[0][1],
            status="FAIL",
            reason="Build identity missing app_version",
            evidence=["app_ui.versioning.get_build_info"],
        )
    return PillarEntry(
        id=1,
        title=PILLAR_TITLES[0][1],
        status="PASS",
        reason="Build identity available",
        evidence=[
            "app_ui.versioning.get_build_info",
            f"app_version={app_version}",
            f"build_id={build_id or 'unknown'}",
        ],
        details=build,
    )


def _check_ci_baseline() -> PillarEntry:
    path = Path(".github/workflows/ci.yml")
    if not path.exists():
        return PillarEntry(
            id=3,
            title=PILLAR_TITLES[2][1],
            status="FAIL",
            reason="CI workflow missing",
            evidence=[str(path)],
        )
    content = path.read_text(encoding="utf-8", errors="ignore")
    required = {
        "actions/setup-python@v5": "setup-python",
        'python-version: "3.12"': "python-version",
        "pytest -q tests/pillars": "pillars pytest",
    }
    missing = []
    for token, label in required.items():
        if token not in content:
            missing.append(label)
    if "compileall" not in content:
        missing.append("compile step")
    if missing:
        return PillarEntry(
            id=3,
            title=PILLAR_TITLES[2][1],
            status="FAIL",
            reason="CI workflow missing required steps",
            evidence=missing,
        )
    return PillarEntry(
        id=3,
        title=PILLAR_TITLES[2][1],
        status="PASS",
        reason="CI workflow enforces compile + pillars tests",
    )


def _check_config_layering() -> PillarEntry:
    try:
        import app_ui.config as config  # local import to keep scope small
    except Exception as exc:
        return PillarEntry(
            id=9,
            title=PILLAR_TITLES[8][1],
            status="FAIL",
            reason=f"Config module import failed: {exc}",
        )
    defaults = getattr(config, "_DEFAULT_UI_CONFIG", {})
    config_path = getattr(config, "CONFIG_PATH", Path("data/roaming/ui_config.json"))
    files_read: List[str] = []
    sources = ["defaults"]
    effective: Dict[str, Any] = {}
    if isinstance(defaults, dict):
        effective.update(defaults)
    else:
        defaults = {}
    if Path(config_path).exists():
        try:
            data = json.loads(Path(config_path).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                effective.update(data)
                files_read.append(str(config_path))
                sources.append("roaming")
        except Exception:
            pass
    if not defaults or not effective:
        return PillarEntry(
            id=9,
            title=PILLAR_TITLES[8][1],
            status="FAIL",
            reason="Effective config snapshot is empty",
            evidence=[f"config_path={config_path}"],
        )
    return PillarEntry(
        id=9,
        title=PILLAR_TITLES[8][1],
        status="PASS",
        reason="Config snapshot available",
        evidence=[f"config_path={config_path}", f"sources={sources}"],
        details={
            "sources": sources,
            "files_read": files_read,
            "env_keys": [],
        },
    )


def _check_schema_manifest(base_dir: Path | None = None) -> PillarEntry:
    root = base_dir or Path(".")
    manifest_path = root / "schemas" / "schema_manifest.json"
    migrations_path = root / "docs" / "migrations" / "README.md"
    if not manifest_path.exists():
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason="schema_manifest.json missing",
            evidence=[str(manifest_path)],
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason=f"schema_manifest.json invalid: {exc}",
        )
    if not isinstance(manifest, dict):
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason="schema_manifest.json root is not an object",
        )
    if not isinstance(manifest.get("manifest_version"), int):
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason="manifest_version missing or not int",
        )
    entries = manifest.get("schemas")
    if not isinstance(entries, list) or not entries:
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason="schemas list missing or empty",
        )
    missing = []
    for entry in entries:
        if not isinstance(entry, dict):
            missing.append("entry-not-object")
            continue
        path = entry.get("path")
        schema_id = entry.get("schema_id")
        schema_version = entry.get("schema_version")
        if not path or not schema_id or not isinstance(schema_version, int):
            missing.append(str(path or "missing-path"))
            continue
        if not (root / "schemas" / path).exists():
            missing.append(str(path))
    if missing:
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason="Schema manifest entries invalid or missing files",
            evidence=missing,
        )
    if not migrations_path.exists():
        return PillarEntry(
            id=2,
            title=PILLAR_TITLES[1][1],
            status="FAIL",
            reason="Migrations README missing",
            evidence=[str(migrations_path)],
        )
    return PillarEntry(
        id=2,
        title=PILLAR_TITLES[1][1],
        status="PASS",
        reason="Schema manifest and migrations note present",
        evidence=[str(manifest_path), str(migrations_path)],
    )


def _check_runtime_data_hygiene() -> PillarEntry:
    git_path = Path(".gitignore")
    if not git_path.exists():
        return PillarEntry(
            id=10,
            title=PILLAR_TITLES[9][1],
            status="FAIL",
            reason=".gitignore missing",
        )
    ignore_text = git_path.read_text(encoding="utf-8", errors="ignore")
    if "data/" not in ignore_text and "/data/" not in ignore_text:
        if "/data/roaming/" not in ignore_text and "/data/workspaces/" not in ignore_text:
            return PillarEntry(
                id=10,
                title=PILLAR_TITLES[9][1],
                status="FAIL",
                reason="data/ ignores not found in .gitignore",
            )
    if not _git_available():
        return PillarEntry(
            id=10,
            title=PILLAR_TITLES[9][1],
            status="SKIP",
            reason="git not available",
        )
    probe_dir = Path("data/roaming/pillars_reports")
    probe_dir.mkdir(parents=True, exist_ok=True)
    probe_path = probe_dir / "_gitignore_probe.tmp"
    try:
        probe_path.write_text("probe")
        output = _run_git_status()
        if output is None:
            return PillarEntry(
                id=10,
                title=PILLAR_TITLES[9][1],
                status="SKIP",
                reason="git status failed",
            )
        if str(probe_path.as_posix()) in output or str(probe_path) in output:
            return PillarEntry(
                id=10,
                title=PILLAR_TITLES[9][1],
                status="FAIL",
                reason="data/ probe file appears in git status",
                evidence=[str(probe_path)],
            )
        return PillarEntry(
            id=10,
            title=PILLAR_TITLES[9][1],
            status="PASS",
            reason="data/ outputs ignored by git",
        )
    finally:
        try:
            probe_path.unlink(missing_ok=True)
        except Exception:
            pass


def _git_available() -> bool:
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return False
    return result.returncode == 0


def _run_git_status() -> str | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=4,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout or ""


def run_pillar_checks() -> List[PillarEntry]:
    results: Dict[int, PillarEntry] = {}

    results[1] = _check_build_identity()
    results[2] = _check_schema_manifest()
    results[3] = _check_ci_baseline()
    results[4] = PillarEntry(
        id=4,
        title=PILLAR_TITLES[3][1],
        status="SKIP",
        reason="Release pipeline checks not implemented yet",
    )
    results[5] = PillarEntry(
        id=5,
        title=PILLAR_TITLES[4][1],
        status="SKIP",
        reason="Crash checks not implemented yet",
    )
    results[6] = PillarEntry(
        id=6,
        title=PILLAR_TITLES[5][1],
        status="SKIP",
        reason="Logging checks not implemented yet",
    )
    results[7] = PillarEntry(
        id=7,
        title=PILLAR_TITLES[6][1],
        status="SKIP",
        reason="Telemetry checks not implemented yet",
    )
    results[8] = PillarEntry(
        id=8,
        title=PILLAR_TITLES[7][1],
        status="SKIP",
        reason="Activity tracing checks not implemented yet",
    )
    results[9] = _check_config_layering()
    results[10] = _check_runtime_data_hygiene()
    results[11] = PillarEntry(
        id=11,
        title=PILLAR_TITLES[10][1],
        status="SKIP",
        reason="Dependency metadata checks not implemented yet",
    )
    results[12] = PillarEntry(
        id=12,
        title=PILLAR_TITLES[11][1],
        status="SKIP",
        reason="Security boundary checks not implemented yet",
    )

    return [results[i] for i, _ in PILLAR_TITLES]


def build_report(results: Iterable[PillarEntry]) -> Dict[str, Any]:
    build = get_build_info()
    return {
        "report_version": REPORT_VERSION,
        "generated_at": time.time(),
        "app_version": build.get("app_version", "unknown"),
        "build_id": build.get("build_id", "unknown"),
        "results": [r.to_dict() for r in results],
    }


def write_report(report: Dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "pillars_report.json"
    target.write_text(json.dumps(report, indent=2))
    return target


def load_report(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def find_latest_report(report_dir: Path) -> Path | None:
    candidates: List[Path] = []
    latest = Path("data/roaming/pillars_report_latest.json")
    if latest.exists():
        candidates.append(latest)
    if report_dir.exists():
        candidates.extend(
            sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        )
    return candidates[0] if candidates else None
