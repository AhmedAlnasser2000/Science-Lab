# Core Center Plan (V2.1)

Scope: optional central management that scans manifests, keeps a registry, reports storage, and offers safe cleanup (cache purge, dumps prune). No integration into app startup.

Data roots (in repo): `data/store`, `data/cache`, `data/dumps`, `data/roaming` (registry).

Discovery (read-only): `content_repo/**/module_manifest.json`, `content_store/**/module_manifest.json`, future `ui_repo/**/ui_pack_manifest.json`, `ui_store/**/ui_pack_manifest.json` if present. Each record stores id, type, version, source, state, install_path, last_seen, disk_usage_bytes.

Registry: `data/roaming/registry.json` (JSON list). Upsert discovered records, leave others untouched for now.

Report: JSON with roots totals and components; human-readable text summary.

Cleanup: `purge_cache()` deletes only `data/cache` contents. `prune_dumps(max_age_days, max_total_bytes)` removes dumps by age/size. Never touch `data/store` by default.

CLI demo: `python -m core_center.demo_report` prints report, updates registry, exits 0 even if folders are missing.

## V3 Status (quick note)
- Storage report + cleanup shipped as Runtime Bus jobs (optional Core Center).
- Registry now includes modules, UI packs, and labs; schema documented in `schemas/registry.schema.json`.
- Policy overrides (`data/roaming/policy.json`) flow through `core.policy.get.request`.
- Run directory allocation + local module install/uninstall are live, with demo CLI helpers for testing.
