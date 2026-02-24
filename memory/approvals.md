# Approvals Ledger (append-only)

## Format
- approved_at_local
- approver
- command
- recorded_by_agent
- recorded_at_local
- user_region
- user_timezone
- source
- canonical_targets
- commit_hash
- notes

## Entries
- approved_at_local: 2026-02-24 04:02:55 +03:00
  approver: ahmed
  command: DISCUSSION APPROVE
  recorded_by_agent: codex
  recorded_at_local: 2026-02-24 04:02:55 +03:00
  user_region: Kuwait/Riyadh
  user_timezone: Arab Standard Time
  source: memory/discussions/active/2026-02-24__checking-memory-infrastructure.md
  canonical_targets: memory/decisions/2026-02-24__memory-infrastructure-check.md
  commit_hash: pending_local_commit
  notes: Approved extract for memory infrastructure verification discussion.
- approved_at_local: 2026-02-24 04:02:55 +03:00
  approver: ahmed
  command: DISCUSSION APPROVE
  recorded_by_agent: codex
  recorded_at_local: 2026-02-24 04:02:55 +03:00
  user_region: Kuwait/Riyadh
  user_timezone: Arab Standard Time
  source: memory/discussions/active/2026-02-24__borrowed-memory-patterns.md
  canonical_targets: memory/decisions/2026-02-24__borrowed-memory-patterns.md
  commit_hash: pending_local_commit
  notes: Approved adoption of four borrowed memory patterns.

## Task Approval View (operational mirror)
| item_id | status | approver | recorded_by_agent | approved_at_local | source | canonical_target |
|---|---|---|---|---|---|---|
| MEM-2026-02-24-001 | completed | ahmed | codex | 2026-02-24 04:02:55 +03:00 | discussion-2026-02-24-checking-memory-infrastructure | memory/decisions/2026-02-24__memory-infrastructure-check.md |
| MEM-2026-02-24-002 | completed | ahmed | codex | 2026-02-24 04:02:55 +03:00 | discussion-2026-02-24-borrowed-memory-patterns | memory/decisions/2026-02-24__borrowed-memory-patterns.md |
