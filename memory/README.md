# Memory Bundle (`memory/`)

This folder is the portable recall bundle for PhysicsLab. If copied alone, it should preserve protocol, current state, checkpoints, governance snapshots, dictionary snapshots, and publishing templates.

## Relationship to `.slice_tmp`
- `.slice_tmp/` is working-state scratch for active slices.
- `memory/` is published recall state intended for portable context and durable references.

## Canonical vs non-canonical
- Canonical: `current-state`, `sessions/checkpoints`, `decisions`, `issues`, `runbooks`, approved extracts, and protocol docs.
- Non-canonical: `discussions/*` and `external/inbox/*` until explicitly promoted.
- Domain canon: `memory/world-canon.md` stores stable high-level truths.

## Write policy (trigger-only)
No writes to `memory/` unless the user explicitly commands one of these exact triggers:
- `MEMORY CAPTURE`
- `MEMORY PROMOTE`
- `SESSION PUBLISH`
- `CHECKPOINT UPDATE`
- `INDEX UPDATE`
- `DISCUSSION SAVE`
- `DISCUSSION ARCHIVE`
- `DISCUSSION APPROVE`

Accepted aliases (input-only; canonical commands above remain source-of-truth):
- `MC` => `MEMORY CAPTURE`
- `MP` => `MEMORY PROMOTE`
- `SP` => `SESSION PUBLISH`
- `CU` => `CHECKPOINT UPDATE`
- `IU` => `INDEX UPDATE`
- `DS` => `DISCUSSION SAVE`
- `DC` => `DISCUSSION ARCHIVE`
- `DA` => `DISCUSSION APPROVE`

## Provenance and time format
- Memory records should include:
  - `recorded_by_agent` (for example: `codex`, `opus`, `gemini`)
  - `recorded_at_local` (user-local datetime with timezone offset)
  - `user_region`
  - `user_timezone`
- Approvals also include human `approver`.

## Git approval policy
- No `git commit` without explicit user approval.
- No `git push` without explicit user approval.

## Quick links
- Protocol: `memory/PROTOCOL.md`
- Index: `memory/INDEX.md`
- Current state: `memory/current-state.md`
- World canon: `memory/world-canon.md`
- Discussions index: `memory/discussions/INDEX.md`
- Latest checkpoint summary: `memory/sessions/checkpoints/app_summary_latest__SUMMARY.md`
- Latest checkpoint dossier: `memory/sessions/checkpoints/app_summary_latest__DOSSIER.md`

## Runtime header policy for this slice
All planning/final responses for this memory slice start with:
- model
- reasoning effort (thinking level)
- scope statement
- short rationale for chosen level
