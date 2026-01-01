from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from diagnostics.pillars_report import build_report, run_smoke_checks, write_report


def run_harness(output: Path) -> Path:
    start = time.monotonic()
    results = run_smoke_checks()
    report = build_report(results)
    report["duration_ms"] = (time.monotonic() - start) * 1000
    written = write_report(report, output)
    try:
        canonical_dir = Path("data/roaming")
        canonical_dir.mkdir(parents=True, exist_ok=True)
        canonical_path = canonical_dir / "pillars_report_latest.json"
        canonical_path.write_text(written.read_text())
    except Exception:
        pass
    return written


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PhysicsLab Pillars harness (scaffold).")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory for pillars_report.json (default: temp folder).",
    )
    args = parser.parse_args(argv)

    output_dir = args.out or Path(tempfile.mkdtemp(prefix="pillars_report_"))
    try:
        written = run_harness(output_dir)
    except Exception as exc:  # pragma: no cover - defensive
        sys.stderr.write(f"Failed to run harness: {exc}\n")
        return 1

    sys.stdout.write(f"Wrote pillars report to: {written}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
