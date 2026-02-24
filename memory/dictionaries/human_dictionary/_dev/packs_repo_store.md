> Snapshot generated during slice d9 from working tree based on HEAD 55fbe3f80f21b0722c1d7ab46aa5ee467f8cb766.
> Snapshot copy for portability; source-of-truth remains under docs/ at commit 55fbe3f80f21b0722c1d7ab46aa5ee467f8cb766.

# Packs, Repo, and Store

## Core distinction
- `*_repo`: source-of-truth assets under version control.
- `*_store`: installed/active copies used by runtime systems.

## Why both exist
- Repos keep canonical authoring history.
- Stores provide runtime stability and isolation.
- Update/migration flows can refresh store state from repo state safely.

## Practical implications
- Editing repo files does not always immediately affect runtime behavior.
- Refresh/reload operations may be required to propagate changes.
- Troubleshooting should verify both source and active store state.

## Common pitfalls
- Assuming store content updates automatically after repo edits.
- Mixing manual store edits with managed update flows.
- Comparing outputs from different stores without noting version/template context.

