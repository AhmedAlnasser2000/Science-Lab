# ADR: Borrowed Memory Patterns (from external comparison)

## Record metadata
- date_local: 2026-02-24 04:02:55 +03:00
- user_region: Kuwait/Riyadh
- user_timezone: Arab Standard Time
- approver: ahmed
- recorded_by_agent: codex
- recorded_at_local: 2026-02-24 04:02:55 +03:00

## Context
User approved adopting four practical memory patterns from another project after comparison with PhysicsLab memory infrastructure.

## Decision
Adopt these patterns in PhysicsLab memory:
1. Locked decisions section in `memory/current-state.md`.
2. Next task section in `memory/current-state.md` with explicit user-overridable semantics.
3. Task-oriented approvals scan view in `memory/approvals.md` (as an operational mirror, not replacement for append-only ledger).
4. Domain canon file: `memory/world-canon.md`.

## Consequences
- Faster operational recall at start of a session.
- Clearer handoff target while preserving user control over changing priorities.
- Easier at-a-glance approvals scanning.
- Explicit product-canon lane without overloading ADR files.

## Alternatives considered
- Keep current memory unchanged.
- Add only locked decisions and next task, skip approvals scan and canon file.

## References
- `memory/discussions/active/2026-02-24__borrowed-memory-patterns.md`
- `memory/decisions/2026-02-24__memory-infrastructure-check.md`
