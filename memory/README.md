# Memory Bundle (`memory/`)

This folder is the portable recall bundle for PhysicsLab. If copied alone, it should preserve protocol, current state, checkpoints, governance snapshots, dictionary snapshots, and publishing templates.

## Relationship to `.slice_tmp`
- `.slice_tmp/` is working-state scratch for active slices.
- `memory/` is published recall state intended for portable context and durable references.

## Canonical vs non-canonical
- Canonical: `canon/verbatim_ledger`, `current-state`, `sessions/checkpoints`, `decisions`, `issues`, `runbooks`, approved extracts, and protocol docs.
- Non-canonical: `discussions/*` and `external/inbox/*` until explicitly promoted.
- Domain canon: `memory/world-canon.md` stores stable high-level truths.

Canon relationship:
- `memory/canon/verbatim_ledger.md` is the primary saved-memory timeline.
- `memory/world-canon.md` is invariants only and is not auto-updated by `CS`.

Recall usage rule:
- When the user asks for past work/state recall ("did you remember", "from what we did", "last time"), read canon ledger first, then canonical summaries, then verify in code.

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
- `CANON SAVE`
- `CS`
- `WORKLOG AUTO ON`
- `WORKLOG AUTO OFF`

Accepted aliases (input-only; canonical commands above remain source-of-truth):
- `MC` => `MEMORY CAPTURE`
- `MP` => `MEMORY PROMOTE`
- `SP` => `SESSION PUBLISH`
- `CU` => `CHECKPOINT UPDATE`
- `IU` => `INDEX UPDATE`
- `DS` => `DISCUSSION SAVE`
- `DC` => `DISCUSSION ARCHIVE`
- `DA` => `DISCUSSION APPROVE`
- `CS` => `CANON SAVE` (also accepted as explicit short trigger phrase)

`CS` behavior (default):
- Append one verbatim entry to canon ledger.
- Then suggest optional promotion commands only (no auto-promotion).

Alias help command:
- `H` / `h`: show current trigger and alias mappings (helper only, no write).

Worklog auto mode (operational):
- `WORKLOG AUTO ON`: after each completed task/gate/mid-gate, update current-state/sessions/journal and runbooks when procedure changes exist.
- `WORKLOG AUTO OFF`: stop automatic operational updates and return to trigger-only writes.
- This mode does not auto-write canon and does not auto-promote decisions/issues.
- Approval-first even in worklog auto mode: state what will be written, wait for explicit approval, then write only approved items.

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
- Canon index: `memory/canon/INDEX.md`
- Canon ledger: `memory/canon/verbatim_ledger.md`
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

## Status lifecycle (borrowed pattern)
Use consistent status labels across memory artifacts:
- `draft`, `active`, `locked`, `superseded`, `rejected`, `completed`

Supersession rule:
- when a plan/task/decision is replaced, keep history and set `superseded` with a link to replacement (`superseded_by`) and reason.
- do not silently overwrite prior approved records.

Next-task rule:
- `memory/current-state.md` next task is operational guidance only and can be rejected/replaced by user at any time.
- session/journal task logs must capture that outcome explicitly.
