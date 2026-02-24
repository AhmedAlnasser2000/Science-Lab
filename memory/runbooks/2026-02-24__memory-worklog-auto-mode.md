# Runbook: Memory Worklog Auto Mode

## Purpose
Provide deterministic operational logging behavior for memory artifacts while keeping canon writes explicit-only.

## Preconditions
- Branch scope is correct for the active slice branch.
- Memory protocol and skill files are in sync.

## Commands
1. Enable: `WORKLOG AUTO ON`
2. Disable: `WORKLOG AUTO OFF`
3. Alias help (no write): `h` or `H`

## Behavior when ON
- After each completed task/gate/mid-gate, update:
  - `memory/current-state.md`
  - `memory/sessions/...`
  - `memory/journal/...`
  - `memory/runbooks/...` only when procedure-level operations changed
- Treat each commit as a task record:
  - before commit: create/update one `active` task row in session+journal artifacts
  - after commit: fill the commit hash and mark the row `completed`
  - if replaced before commit: mark `superseded` (or `rejected`) and link replacement/reason
- Do not write canon automatically.
- Do not auto-promote decisions/issues.

## Status model
Use shared statuses:
- `draft`, `active`, `locked`, `superseded`, `rejected`, `completed`

Supersession fields:
- `supersedes`
- `superseded_by`
- `superseded_at_local`
- `supersession_reason`

## Behavior when OFF
- Return to strict trigger-only writes.

## Commit-as-task artifacts (V5.5e)
- Journal task log: `memory/journal/2026-02-24__v5.5e-commit-task-tracking.md`
- Session task log: `memory/sessions/v5.5e/2026-02-24__commit-task-log.md`

## Verification
- Confirm trigger strings in:
  - `memory/PROTOCOL.md`
  - `.agents/skills/physicslab_memory/SKILL.md`
  - `memory/README.md`
- Confirm latest operational updates exist in:
  - `memory/current-state.md`
  - `memory/sessions/`
  - `memory/journal/`

## Rollback
- Revert runbook and corresponding protocol/skill/readme changes if policy needs redesign.

