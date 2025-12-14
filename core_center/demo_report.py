import json
import sys
from pathlib import Path

from . import cleanup  # noqa: F401  # placeholder for future optional use
from .discovery import discover_components
from .registry import load_registry, save_registry, upsert_records
from .storage_report import format_report_text, generate_report


def main() -> None:
    try:
        registry_path = Path("data/roaming/registry.json")
        existing = load_registry(registry_path)
        discovered = discover_components()
        merged = upsert_records(existing, discovered)
        save_registry(registry_path, merged)
        report = generate_report(merged)
        print(format_report_text(report))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Core Center demo encountered an error but will exit 0: {exc}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
