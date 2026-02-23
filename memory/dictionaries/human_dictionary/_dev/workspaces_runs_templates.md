> Snapshot generated during slice d9 from working tree based on HEAD 55fbe3f80f21b0722c1d7ab46aa5ee467f8cb766.
> Snapshot copy for portability; source-of-truth remains under docs/ at commit 55fbe3f80f21b0722c1d7ab46aa5ee467f8cb766.

# Workspaces, Runs, and Templates

## Workspace lifecycle
1. Create workspace from a template.
2. Select packs/content for the workspace.
3. Execute runs.
4. Inspect outcomes in System Health and CodeSee.

## Run semantics
- A run is an execution slice with timestamps and status.
- Runs can generate bus events, spans, and diagnostics.
- Failed runs should be traceable through crash and diagnostics flows.

## Template semantics
- Templates provide a default pack/content baseline.
- Templates should minimize setup friction for repeated experiments.
- Templates are expected to be deterministic and reproducible.

## Operator guidance
- Prefer creating new workspaces for isolated experiments.
- Keep run notes short and tied to objective outcomes.
- Use snapshots/diff in CodeSee to compare behavioral changes over time.

