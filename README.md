# PhysicsLab (Workspace Sandbox)

PhysicsLab is a PyQt6 desktop sandbox for learning physics, backed by a local Management Core (optional) and a runtime bus. It uses content packs, labs, and components with an active workspace model.

Canonical app summary: `docs/app_summary.md`.

## Folder Overview
- `schemas/` JSON Schemas for manifests and runtime state.
- `content_repo/` canonical Physics content pack source.
- `content_store/` installed content mirror (module installs land here).
- `content_system/` loader that ingests manifests and prepares runtime payloads.
- `runtime_bus/` in-process pub/sub + request/reply broker.
- `core_center/` Management Core (jobs, inventory, runs, workspaces, policy).
- `component_runtime/` component registry/host and component packs.
- `component_repo/` + `component_store/` component pack source + installed mirror.
- `workspace_repo/` workspace templates (seed files).
- `app_ui/` PyQt6 UI, labs, and component host screens.
- `ui_system/` + `ui_repo/` + `ui_store/` UI pack manager + QSS packs.
- `kernel/` Rust gravity kernel DLL.
- `docs/` checkpoint summaries, plans, and prompts.
- `test_rust/` temporary Rust experiment, not the PhysicsLab kernel.

## Quick Start (dev)
- Run the app: `python -m app_ui.main`
- Optional Core Center demos:
  - `python -m core_center.demo_report`
  - `python -m core_center.demo_install --action install --module physics_v1`

## Runtime Notes (current)
- **Runtime Bus**: local pub/sub + request/reply (`runtime_bus/`); enable trace logging with `PHYSICSLAB_BUS_DEBUG=1`.
- **System Health**: segmented UI (Overview/Runs/Maintenance/Modules/Jobs) using Core Center endpoints when available.
- **Workspaces**: active workspace stored in `data/roaming/workspace.json`; runs live under `data/workspaces/<id>/runs/<lab>/<run>/run.json`.
- **Policies**: overrides live in `data/roaming/policy.json`; resolved policy via `core.policy.get.request`.
- **Registry/Inventory**: `data/roaming/registry.json` and `core.inventory.get.request`.
- **Component Packs**: installable via Core Center job endpoints to `component_store/component_v1/packs/`.
