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
    build = get_build_info()
    results: Dict[int, PillarEntry] = {}

    results[1] = PillarEntry(
        id=1,
        title=PILLAR_TITLES[0][1],
        status="PASS" if build.get("app_version") else "SKIP",
        reason="Build identity available" if build.get("app_version") else "Build info missing",
        details=build,
    )
    results[2] = PillarEntry(
        id=2,
        title=PILLAR_TITLES[1][1],
        status="SKIP",
        reason="Schema checks not implemented yet",
    )
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
    results[9] = PillarEntry(
        id=9,
        title=PILLAR_TITLES[8][1],
        status="SKIP",
        reason="Config checks not implemented yet",
    )
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
