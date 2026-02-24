# Runbook: Memory Worklog Auto Mode

## Purpose
Provide deterministic operational logging behavior for memory artifacts while keeping canon writes explicit-only.

## Preconditions
- Branch scope is correct (`work/v5.5d9` for this slice context).
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
- Do not write canon automatically.
- Do not auto-promote decisions/issues.

## Behavior when OFF
- Return to strict trigger-only writes.

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
