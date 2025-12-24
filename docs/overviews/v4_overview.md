# PhysicsLab V4 Overview

V4 builds on V3 by adding workspace-backed runs, workspace templates, and a segmented System Health UI while keeping the runtime bus and Core Center optional. This document summarizes the current runtime behavior and where to find state files.

## Runtime Bus
- `runtime_bus/` provides in-process pub/sub plus request/reply (`RuntimeBus`).
- Requests return `{"ok": True, ...}` or `{"ok": False, "error": "..."}`.
- Set `PHYSICSLAB_BUS_DEBUG=1` to log publish/request/reply lines.
- Topics in active use (non-exhaustive, see `runtime_bus/topics.py`):
  - Runtime diagnostics: `runtime.bus.report.request`
  - Core services: `core.storage.report.request`, `core.cleanup.request`, `core.storage.allocate_run_dir.request`,
    `core.policy.get.request`, `core.registry.get.request`, `core.inventory.get.request`
  - Runs: `core.runs.list.request`, `core.runs.delete.request`, `core.runs.delete_many.request`, `core.runs.prune.request`
  - Workspaces: `core.workspace.get_active.request`, `core.workspace.set_active.request`, `core.workspace.list.request`,
    `core.workspace.create.request`, `core.workspace.delete.request`, `core.workspace.templates.list.request`
  - Jobs: `job.started`, `job.progress`, `job.completed`, plus `core.jobs.list.request` / `core.jobs.get.request`
  - Module install: `core.content.module.install.request`, `core.content.module.uninstall.request`
  - Component packs: `core.component_pack.install.request`, `core.component_pack.uninstall.request`

## Core Center (Optional)
- Lives under `core_center/`; the UI remains functional without it, but job-driven flows are richer when available.
- Responsibilities:
  - Inventory and registry output (`data/roaming/registry.json`, bus endpoint `core.inventory.get.request`).
  - Storage report generation (`python -m core_center.demo_report`).
  - Cleanup helpers (cache / dumps) via job manager.
  - Policy resolution (`data/roaming/policy.json` overrides).
  - Run directory allocation via `core.storage.allocate_run_dir.request`.
  - Module install/uninstall (repo to store) via bus endpoints.
  - Runs management (list/delete/prune) for the active workspace.
  - Workspace lifecycle (list/create/delete/set active) and template listing.

## Workspaces and Templates
- Workspace root: `data/workspaces/<workspace_id>/`.
- Expected subfolders: `runs/`, `runs_local/`, `cache/`, `store/`, `prefs/`.
- Active workspace is tracked in `data/roaming/workspace.json` (via `core.workspace.get_active.request`).
- Templates live in `workspace_repo/templates/<template_id>/` and can seed:
  - `workspace_config.json`
  - `lab_prefs.json`
  - `policy_overrides.json`
  - `pins.json`

## App UI Highlights
- PyQt6 main window with:
  - Home/Quick Start
  - Physics Content (Content Browser)
  - Content/Module Management
  - Settings (profiles + reduced motion)
  - System Health (segmented: Overview, Maintenance, Modules, Jobs, Runs)
- LabHost injects guide markdown, run-dir paths, resolved policy, workspace context, and user prefs into labs.
- Parts that launch labs declare `x_extensions.lab.lab_id`; the UI uses this metadata when available, with a legacy fallback.

## Runtime State Files
- `data/roaming/policy.json` (optional overrides; schema: `schemas/policy.schema.json`).
- `data/roaming/registry.json` (registry snapshot; schema: `schemas/registry.schema.json`).
- `data/roaming/workspace.json` (active workspace metadata).
- `data/workspaces/<id>/runs/<lab>/<run>/run.json` (per-lab run metadata).
- `data/workspaces/<id>/prefs/lab_prefs.json` (per-lab grid/axes prefs).

## Testing Tips
1. `python -m runtime_bus.demo_bus` - sanity check for bus behavior.
2. `python -m core_center.demo_report` - regenerate registry + storage report.
3. `python -m core_center.demo_install --module physics_v1 --action install` - copy module repo to store.
4. `python -m app_ui.main` - exercise System Health, workspaces, and lab runs.
