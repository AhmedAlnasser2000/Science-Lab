# Core Center (Optional, V2.1)

Optional management helper for PhysicsLab that keeps a registry, observes storage, and can safely clean caches/dumps. It is not required for app startup.

## Data Roots (in-repo for now)
- `data/store/`
- `data/cache/`
- `data/dumps/`
- `data/roaming/` (registry lives here)

## Capabilities
- Discover components by scanning:
  - `content_repo/**/module_manifest.json`
  - `content_store/**/module_manifest.json`
  - `ui_repo/**/ui_pack_manifest.json` (if present)
  - `ui_store/**/ui_pack_manifest.json` (if present)
- Maintain `data/roaming/registry.json` with fields: `id`, `type`, `version`, `source`, `state`, `install_path`, `last_seen`, `disk_usage_bytes`.
- Storage reports: totals per data root and per-component usage (JSON + human-readable text).
- Safe cleanup helpers (not auto-run): purge `data/cache/`, prune `data/dumps/` by age/size; never delete `data/store/` by default.

## How to Run the Demo
From repo root:
```bash
python -m core_center.demo_report
```
- Prints a human-readable storage report.
- Creates/updates `data/roaming/registry.json`.
- Exits with code 0 even if the data folders are missing.

Expected sample output (will vary with local files):
```
Storage Roots:
  store: 0 bytes
  cache: 0 bytes
  dumps: 0 bytes
  roaming: 261 bytes
  total: 261 bytes

Components:
  physics [module] content_repo present 4316 bytes @ content_repo\physics_v1
```

- Module install/uninstall helper:
```bash
python -m core_center.demo_install --module physics_v1 --action install
python -m core_center.demo_install --module physics_v1 --action uninstall
```
- Prints Runtime Bus progress, waits for completion, and confirms the module folder + registry.

## Notes
- Uses Python stdlib only.
- Core Center remains optional and is not wired into any app startup flow yet.
