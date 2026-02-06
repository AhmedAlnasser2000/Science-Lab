# core_center Agent Map

## Path(s)
- `core_center/`
- key app touchpoints: `app_ui/screens/system_health.py`, `app_ui/screens/workspace_management.py`

## Role
- Core orchestration for discovery, registry, cleanup, jobs, runs, and workspace services.

## Key symbols
- Discovery/registry APIs, jobs/runs handlers, cleanup/report helpers, workspace service endpoints.

## Edit-when
- Inventory/discovery behavior changes.
- Jobs/runs lifecycle changes.
- Cleanup/storage report logic changes.

## Risks/Notes
- High blast radius: many screens and diagnostics depend on these APIs.
- Preserve bus contracts when changing request/reply payloads.

## NAV quick jumps
- placeholder (to backfill when core_center NAV anchors are added).
