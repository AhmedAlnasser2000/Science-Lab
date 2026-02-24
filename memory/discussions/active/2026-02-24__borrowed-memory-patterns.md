# Discussion: Borrowed Memory Patterns

## Metadata
- discussion_id: discussion-2026-02-24-borrowed-memory-patterns
- created_at_local: 2026-02-24 04:02:55 +03:00
- owner: ahmed
- status: active
- user_region: Kuwait/Riyadh
- user_timezone: Arab Standard Time
- recorded_by_agent: codex
- recorded_at_local: 2026-02-24 04:02:55 +03:00

## Problem statement
Decide whether to adopt four practical patterns from another project's memory setup into PhysicsLab memory infrastructure.

## Options
- option_a: Keep current memory structure unchanged.
- option_b: Adopt all four patterns with PhysicsLab policy compatibility.
- option_c: Adopt only selected patterns.

## Constraints
- Keep trigger-gated writes and non-binding discussion rules.
- Preserve canonical command names and approvals traceability.
- Keep new additions lightweight and readable.

## Unknowns
- Whether task-table approvals should become required or remain optional mirror view.

## What would change my mind
- Evidence that added sections increase maintenance cost without recall benefit.
- Policy conflict with existing trigger or governance rules.

## Notes and references
- `memory/current-state.md`
- `memory/approvals.md`
- `memory/INDEX.md`

## Approval Extract
- Approved by user to borrow all four:
  - Locked decisions block in current state
  - Next task field with explicit user-overridable semantics
  - Task-oriented approvals scan view
  - Domain canon file (`world-canon` style)
- Canonical target created:
  - `memory/decisions/2026-02-24__borrowed-memory-patterns.md`
