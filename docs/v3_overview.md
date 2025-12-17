# PhysicsLab V3 Overview

V3 builds on the V1 scaffold by wiring a local runtime bus, optional Core Center services, and richer PyQt6 UX flows. This document captures the key pieces so contributors can find state files and test the new runtime behaviors.

## Runtime Bus
- `runtime_bus/` hosts an in-process pub/sub + request/reply broker (`RuntimeBus`). No sockets, no threads required.
- Requests reply with `{"ok": True, ...}` or `{"ok": False, "error": "..."}`; callers check `ok` before continuing.
- Set `PHYSICSLAB_BUS_DEBUG=1` to log every publish/request/reply line.
- Topics presently used:
  - Runtime diagnostics: `runtime.bus.report.request`
  - Core services: `core.storage.report.request`, `core.cleanup.request`, `core.storage.allocate_run_dir.request`, `core.policy.get.request`, `core.registry.get.request`, `core.content.module.install.request`, `core.content.module.uninstall.request`
  - Job lifecycle: `job.started`, `job.progress`, `job.completed`
  - Content job events: `content.install.progress`, `content.install.completed`

## Core Center (Optional)
- Lives under `core_center/`; UI remains functional without it.
- Responsibilities:
  - Discover modules/UI packs/labs → `data/roaming/registry.json`
  - Generate storage reports (`python -m core_center.demo_report`)
  - Cleanup helpers (cache / dumps) via jobs
  - Policy resolution (`data/roaming/policy.json` overrides)
  - Run directory allocation (`data/store/runs/<lab>/<run>/run.json`)
  - Local module install/uninstall (repo → store) via bus endpoints / `python -m core_center.demo_install`

## App UI Highlights
- PyQt6 main window exposing the Primary Mode hierarchy, lab host, and System Health.
- Experience Profiles + Reduced Motion saved in `data/roaming/` and applied live.
- System Health (Educator/Explorer) shows storage report, cleanup, install/uninstall controls with live progress.
- LabHost injects guide markdown, run-dir paths, and resolved policy into labs without coupling labs to Core Center.

## Runtime State Files
- `data/roaming/policy.json` – optional overrides (schema: `schemas/policy.schema.json`)
- `data/roaming/registry.json` – unified registry (schema: `schemas/registry.schema.json`)
- `data/store/runs/<lab>/<run>/run.json` – per-lab run metadata

## Testing Tips
1. `python -m runtime_bus.demo_bus` – sanity check for bus behavior.
2. `python -m core_center.demo_report` – regenerate registry + storage report.
3. `python -m core_center.demo_install --module physics_v1 --action install` – copy module repo → store, watch bus progress.
4. `python -m app_ui.main` – interact with System Health (Explorer), labs, and settings.
