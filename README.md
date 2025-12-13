# PhysicsLab V1 Scaffold

V1 focuses on delivering a single Physics subject pack via the Primary Mode schemas with a minimal offline pipeline.

## Folder Overview
- `schemas/` frozen JSON Schemas for V1 (do not edit).
- `content_repo/` frozen reference Physics content pack.
- `content_store/` staging area where new packs will be unpacked.
- `content_system/` Python loader that ingests manifests and prepares runtime payloads.
- `runtime_bus/` lightweight broker moving payloads between loader, kernel, UI, and diagnostics.
- `diagnostics/` friendly event sink for schema or asset issues.
- `app_ui/` shell UI for rendering text parts and the gravity demo preset.
- `kernel/` Rust gravity-demo kernel that exports the Primary Mode DLL.
- `docs/` optional planning notes for V1 decisions.
- `test_rust/` temporary Rust experiment, not the PhysicsLab kernel.

## Next Steps
1. Build the content loader pipeline (content_store -> content_system).
2. Feed curated payloads into the UI (runtime_bus -> app_ui).
3. Implement the actual kernel behaviors and wire diagnostics end-to-end.
