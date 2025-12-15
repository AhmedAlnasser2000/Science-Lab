from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

from runtime_bus.bus import RuntimeBus

try:
    from runtime_bus import topics as BUS_TOPICS
except Exception:  # pragma: no cover
    BUS_TOPICS = None

from .bus_endpoints import register_core_center_endpoints

INSTALL_REQUEST_TOPIC = (
    BUS_TOPICS.CORE_CONTENT_MODULE_INSTALL_REQUEST
    if BUS_TOPICS
    else "core.content.module.install.request"
)
UNINSTALL_REQUEST_TOPIC = (
    BUS_TOPICS.CORE_CONTENT_MODULE_UNINSTALL_REQUEST
    if BUS_TOPICS
    else "core.content.module.uninstall.request"
)
PROGRESS_TOPIC = BUS_TOPICS.CONTENT_INSTALL_PROGRESS if BUS_TOPICS else "content.install.progress"
COMPLETED_TOPIC = (
    BUS_TOPICS.CONTENT_INSTALL_COMPLETED if BUS_TOPICS else "content.install.completed"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Demo module install/uninstall via Core Center")
    parser.add_argument("--module", default="physics_v1", help="Module ID to operate on")
    parser.add_argument(
        "--action",
        choices=("install", "uninstall"),
        default="install",
        help="Action to perform",
    )
    parser.add_argument("--timeout", type=float, default=60.0, help="Timeout in seconds")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    bus = RuntimeBus()
    register_core_center_endpoints(bus)

    done = threading.Event()
    result_payload: dict | None = None

    def _on_progress(envelope):
        payload = getattr(envelope, "payload", {}) or {}
        if payload.get("module_id") != args.module:
            return
        percent = payload.get("percent")
        stage = payload.get("stage")
        if percent is not None:
            print(f"[progress] {args.module}: {percent:.1f}% - {stage}")
        else:
            print(f"[progress] {args.module}: {stage}")

    def _on_completed(envelope):
        nonlocal result_payload
        payload = getattr(envelope, "payload", {}) or {}
        if payload.get("module_id") != args.module:
            return
        result_payload = payload
        ok = payload.get("ok")
        action = payload.get("action")
        msg = "SUCCESS" if ok else f"FAILED ({payload.get('error')})"
        print(f"[completed] {args.module} {action}: {msg}")
        done.set()

    sub_progress = bus.subscribe(PROGRESS_TOPIC, _on_progress)
    sub_completed = bus.subscribe(COMPLETED_TOPIC, _on_completed)

    try:
        request_topic = (
            INSTALL_REQUEST_TOPIC if args.action == "install" else UNINSTALL_REQUEST_TOPIC
        )
        print(f"[request] {args.action} {args.module}")
        response = bus.request(
            request_topic,
            {"module_id": args.module},
            source="cli",
            timeout_ms=2000,
        )
        if not response.get("ok"):
            print(f"[error] request failed: {response.get('error')}")
            return 1
        job_id = response.get("job_id")
        print(f"[request] job_id={job_id}")
        start = time.time()
        while not done.wait(0.5):
            if time.time() - start > args.timeout:
                print("[error] operation timed out")
                return 1
        _print_final_state(args.module)
        return 0 if (result_payload or {}).get("ok") else 1
    finally:
        bus.unsubscribe(sub_progress)
        bus.unsubscribe(sub_completed)


def _print_final_state(module_id: str) -> None:
    store_path = Path("content_store") / module_id
    exists = store_path.exists()
    print(f"[state] content_store/{module_id} exists: {exists}")
    registry_path = Path("data/roaming/registry.json")
    if registry_path.exists():
        try:
            data = json.loads(registry_path.read_text(encoding="utf-8"))
            total = len(data) if isinstance(data, list) else 0
            store_entries = [
                rec for rec in data if isinstance(rec, dict) and rec.get("source") == "store"
            ]
            count_store = len(store_entries)
            print(f"[registry] total entries: {total}, store entries: {count_store}")
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[registry] failed to read registry: {exc}")
    else:
        print("[registry] registry file missing")


if __name__ == "__main__":
    sys.exit(main())
