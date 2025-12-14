from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .discovery import discover_components, ensure_data_roots
from .registry import load_registry, save_registry, upsert_records
from .storage_report import format_report_text, generate_report

REPORT_REQUEST_TOPIC = "core.storage.report.request"
REPORT_READY_TOPIC = "core.storage.report.ready"


def register_core_center_endpoints(bus: Any) -> None:
    """Register Core Center request handlers on the provided bus."""

    if bus is None:
        return

    if getattr(bus, "_core_center_registered", False):
        return
    setattr(bus, "_core_center_registered", True)

    def _handle_report(envelope) -> Dict[str, object]:
        try:
            ensure_data_roots()
            registry_path = Path("data/roaming/registry.json")
            existing = load_registry(registry_path)
            discovered = discover_components()
            merged = upsert_records(existing, discovered)
            save_registry(registry_path, merged)
            report = generate_report(merged)
            text = format_report_text(report)
            _publish_ready(bus, envelope.trace_id, text, report)
            return {"ok": True, "text": text, "json": report}
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": str(exc)}

    bus.register_handler(REPORT_REQUEST_TOPIC, _handle_report)


def _publish_ready(bus: Any, trace_id: Optional[str], text: str, payload_json: Dict[str, object]) -> None:
    if not hasattr(bus, "publish"):
        return
    try:
        bus.publish(
            REPORT_READY_TOPIC,
            {"text": text, "json": payload_json},
            source="core_center",
            trace_id=trace_id,
        )
    except Exception:  # pragma: no cover - defensive
        return
