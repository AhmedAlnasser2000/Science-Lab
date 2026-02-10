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
