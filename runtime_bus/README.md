# Runtime Bus (V3 baseline)

Lightweight, in-process message broker that links UI, content, labs, and diagnostics without network sockets.

## Capabilities

- **Message envelope** (`runtime_bus/messages.py`) ensures every payload carries `msg_id`, `type`, `timestamp`, `source`, optional `target`, `trace_id`, and a dict `payload`.
- **Publish/Subscribe** (`runtime_bus/bus.py`) lets any component `subscribe(topic, handler)` and receive `MessageEnvelope` instances. Handlers run in the caller thread, and failures are caught/logged so they never crash the publisher.
- **Request/Reply** via `register_handler()` + `request()` for simple RPC-style exchanges with timeout protection and graceful `{"ok": False, "error": ...}` fallbacks.
- **Topic constants** live in `runtime_bus/topics.py` to keep strings consistent across the app stack.
- **Demo** (`python -m runtime_bus.demo_bus`) exercises pub/sub, request/reply, and timeout behavior.

## Usage

```python
from runtime_bus import get_global_bus, topics

bus = get_global_bus()

def on_profile(msg):
    print("profile change", msg.payload)

sub_id = bus.subscribe(topics.UI_PROFILE_CHANGED, on_profile)
bus.publish(topics.UI_PROFILE_CHANGED, {"profile": "Explorer"}, source="app_ui", trace_id=None)
bus.unsubscribe(sub_id)
```

Request example:

```python
bus.register_handler(topics.CORE_STORAGE_REPORT_REQUEST, lambda msg: {"ok": True, "data": "ready"})
response = bus.request(
    topics.CORE_STORAGE_REPORT_REQUEST,
    {"scope": "all"},
    source="core_center",
    timeout_ms=500,
)
```

All operations are local/thread-safe and never perform I/O. Use `logging` configuration to capture warning/error lines emitted when handlers raise.

## Topics Used in V3

- **Runtime**
  - `runtime.bus.report.request`
- **Core / Governor**
  - `core.storage.report.request`
  - `core.cleanup.request`
  - `core.storage.allocate_run_dir.request`
  - `core.policy.get.request`
  - `core.registry.get.request`
  - `core.content.module.install.request`
  - `core.content.module.uninstall.request`
- **Content job events**
  - `content.install.progress`
  - `content.install.completed`
- **Job lifecycle**
  - `job.started`
  - `job.progress`
  - `job.completed`

All request topics expect structured replies: handlers return `{"ok": True, ...}` on success or `{"ok": False, "error": "<reason>"}` on failure. Callers should always check the `ok` flag before using other fields.
