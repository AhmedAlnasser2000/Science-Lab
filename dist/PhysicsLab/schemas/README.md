# PhysicsLab V1 Schemas

Draft 2020-12 JSON Schemas for the PhysicsLab Primary Mode content format. Objects are tightly scoped with `additionalProperties: false` everywhere except for `x_extensions` and `details`, which stay open for vendor data and diagnostics.

## Files
- `common.schema.json` — shared defs: identifiers, versions, titles, asset refs, `x_extensions`, `details`.
- `mode_profile.schema.json` — Primary Mode capabilities, limits, and security.
- `module_manifest.schema.json` — Subject Module entry point; lists sections and points at the Primary Mode profile.
- `section_manifest.schema.json` — Groups packages within a section.
- `package_manifest.schema.json` — Lists ordered parts inside a package.
- `part_manifest.schema.json` — Describes a part (text or simple simulation) plus its asset reference.
- `diagnostic_event.schema.json` — Friendly error/status event with optional scope and free-form details.

## Hierarchy
Subject Module → Section → Package → Part (use these names exactly).
- Each manifest includes `schema_version`, `content_version`, and its ids.
- Asset paths are module-relative (e.g., `assets/text_intro.md`).
- Only a Primary Mode is supported in V1; modules carry a `primary_mode_ref` pointing to a `mode_profile.json`.

## Validation Tips
- Use the `$id` or local relative paths in `$schema` to validate each JSON file.
- Keep ids lowercase with dashes/underscores to satisfy the `identifier` pattern.
- Extend cautiously via `x_extensions`; richer debugging can live in `details` on diagnostics.

## Runtime State Schemas (V3)
The `schemas/` folder now also includes lightweight schemas for runtime state files under `data/roaming/`:
- `policy.schema.json` – best-effort validation for policy overrides (`policy.json`). All fields are optional overrides; schema is permissive to allow future keys.
- `registry.schema.json` – best-effort validation for the unified registry (`registry.json`). Accepts either a top-level array or an object with an `entries` array plus summary keys.

These runtime schemas are informational (not enforced inside the app) and are intended to help contributors understand the shapes of the generated files while keeping room for evolution.
