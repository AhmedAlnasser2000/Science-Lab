from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app_ui.versioning import get_build_info

REPORT_VERSION = 1


@dataclass
class PillarResult:
    pillar_id: str
    name: str
    status: str
    details: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = (self.status or "").upper()
        return data


def build_report(results: Iterable[PillarResult]) -> Dict[str, Any]:
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
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Invalid report: root is not an object")
    return data


def run_smoke_checks() -> List[PillarResult]:
    results: List[PillarResult] = []

    start = time.monotonic()
    build = get_build_info()
    status = "PASS" if build.get("app_version") else "SKIP"
    details = "Build info available" if status == "PASS" else "No build info found"
    results.append(
        PillarResult(
            pillar_id="pillar.build_identity",
            name="Build identity present",
            status=status,
            details=details,
            duration_ms=(time.monotonic() - start) * 1000,
        )
    )

    results.append(
        PillarResult(
            pillar_id="pillar.storage",
            name="Storage integrity",
            status="SKIP",
            details="Not implemented yet; placeholder for future pillar checks.",
            duration_ms=0.0,
        )
    )

    return results
