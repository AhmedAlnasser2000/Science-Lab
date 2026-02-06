# Repo Stacks Agent Map

Fast map for the repo's repo/system/store triads.

## UI triad
- **Path(s):** `ui_repo/`, `ui_system/`, `ui_store/`
- **Role:** UI source bundles, install/runtime behavior, persisted installed UI packs.
- **Key symbols:** repo metadata and catalog loaders in each package.
- **Edit-when:** UI pack catalog behavior, install flow, or UI pack persistence rules.
- **Risks/Notes:** Keep source repo (`*_repo`) distinct from installed mirror (`*_store`).
- **NAV quick jumps:** placeholder.

## Components triad
- **Path(s):** `component_repo/`, `component_runtime/`, `component_store/`
- **Role:** Component source catalog, runtime component behavior, installed mirror.
- **Key symbols:** component descriptors, runtime execution helpers, store indexing.
- **Edit-when:** Component install/resolve/runtime behavior.
- **Risks/Notes:** Avoid crossing source metadata with installed state.
- **NAV quick jumps:** placeholder.

## Content triad
- **Path(s):** `content_repo/`, `content_system/`, `content_store/`
- **Role:** Content source repository, runtime/content services, installed content mirror.
- **Key symbols:** content manifests, validation/install orchestration, store scanners.
- **Edit-when:** Content discovery, validation, and install pipeline behavior.
- **Risks/Notes:** Keep manifests and installed state decoupled.
- **NAV quick jumps:** placeholder.

## Source vs installed mirror
- `*_repo`: source-of-truth assets/metadata checked into or synced into repo.
- `*_store`: installed/mirrored copies used at runtime.
- `*_system` / `*_runtime`: orchestration and execution layers.

## Common pitfalls
- Mixing repo content paths with store paths in runtime code.
- Writing runtime state into repo folders.
- Assuming install state exists without checking store/index first.
