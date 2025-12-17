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

## V3 Runtime Notes
- **Runtime Bus** – local pub/sub + request/reply broker (`runtime_bus/`); enable trace logging with `PHYSICSLAB_BUS_DEBUG=1`.
- **System Health** – prefers Core Center endpoints when available (storage report, cleanup, module install), but still runs without Core Center.
- **Policies** – overrides live in `data/roaming/policy.json`; resolved policy available via `core.policy.get.request`.
- **Registry** – unified `data/roaming/registry.json`; fetch via `core.registry.get.request`.
- **Run artifacts** – labs allocate `data/store/runs/<lab_id>/<run_id>/run.json` through `core.storage.allocate_run_dir.request`.
- **Local module install/uninstall** – repo → store copy through `core.content.module.install.request` / `.uninstall.request`. Demo CLI:
  - `python -m core_center.demo_install --action install --module physics_v1`
  - `python -m core_center.demo_install --action uninstall --module physics_v1`
