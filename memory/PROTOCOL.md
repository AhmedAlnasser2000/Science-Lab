# Memory Protocol

## 0) Slice communication requirement (d9)
- All planning/final responses for this slice start with a Runtime Header:
  - model
  - reasoning effort
  - short rationale for scope fit

## 1) Precedence and authority
- Tier-0 authority:
  - `AGENTS.md`
  - `docs/handbook/agent_safety_rules.md`
- Tier-1 memory protocol:
  - `memory/PROTOCOL.md`

If a conflict exists, Tier-0 wins.

## 2) Read order when ambiguous
1. Read `memory/INDEX.md` and canonical memory artifacts:
- `memory/current-state.md`
- `memory/sessions/checkpoints/*`
- `memory/decisions/*`
- `memory/issues/*`
- `memory/runbooks/*`
2. Verify claims in code/repo.
3. Consult `memory/discussions/*` only when explicitly referenced or needed for unresolved context.

## 3) Write guardrail (strict)
Do not write to `memory/` unless user command includes one exact trigger phrase:
- `MEMORY CAPTURE`
- `MEMORY PROMOTE`
- `SESSION PUBLISH`
- `CHECKPOINT UPDATE`
- `INDEX UPDATE`
- `DISCUSSION SAVE`
- `DISCUSSION ARCHIVE`
- `DISCUSSION APPROVE`

## 3.1) Git approval guardrail (strict)
- Do not run `git commit` without explicit user approval.
- Do not run `git push` without explicit user approval.
- Before commit/push, present a short plan and wait for approval.

## 4) Trigger semantics
### `MEMORY CAPTURE`
- Store raw material in `memory/external/sources/{chatgpt|codex|other_ai|docs}/`.
- Create import manifest under `memory/external/manifests/`.
- Update external inbox pointer in `memory/INDEX.md`.

### `MEMORY PROMOTE`
- Promote a referenced raw import or discussion into canonical targets:
  - `memory/decisions/` or
  - `memory/issues/` or
  - `memory/runbooks/`
- Keep source back-links.
- Update `memory/INDEX.md`.
- Append approval record in `memory/approvals.md` when canonical truth is created.

### `SESSION PUBLISH`
- Export `.slice_tmp/<slice_id>/` artifacts into `memory/sessions/<slice_id>/`.
- Create/update related `memory/journal/<date>__<slice_id>.md`.
- Update `memory/INDEX.md`.

### `CHECKPOINT UPDATE`
- Update `memory/current-state.md` and checkpoint summary/dossier pointers.

### `INDEX UPDATE`
- Update only `memory/INDEX.md`.

### `DISCUSSION SAVE`
- Create a discussion doc in `memory/discussions/active/` from template.
- Update `memory/discussions/INDEX.md`.

### `DISCUSSION ARCHIVE`
- Move discussion doc from active to archived.
- Update `memory/discussions/INDEX.md`.

### `DISCUSSION APPROVE`
- Create canonical extract in `memory/decisions/`, `memory/issues/`, or `memory/runbooks/`.
- Link source discussion and approved extract.
- Update `memory/INDEX.md`.
- Mandatory append in `memory/approvals.md` with datetime, approver, source discussion, canonical targets, and commit hash once committed.

## 5) Discussions lane policy (non-binding)
- `memory/discussions/*` is context only.
- Discussions are not truth by default.
- No canonical promotion unless explicit `DISCUSSION APPROVE` (or explicit `MEMORY PROMOTE` referencing discussion source).

## 6) External lane policy
- Raw drops belong to `memory/external/sources/*` only.
- Each raw drop must have manifest metadata:
  - source
  - author/model
  - captured_at
  - scope
  - promotion_status
- Keep external lane curated and lean.

## 7) Sessions and journals
- Sessions capture gate artifacts/evidence.
- Journals capture post-task narrative and outcome context.
- Use templates and include:
  - gate table
  - mid-gate amendment table
  - verification evidence
  - risks and rollback notes

## 8) Snapshot policy
- Snapshot banners must identify base commit hash explicitly:
- `Snapshot generated during slice d9 from working tree based on HEAD <hash>.`
- `<hash>` comes from `git rev-parse HEAD` at snapshot time.

- Dictionary snapshots are text-first to keep repo lean:
- copy `.md`, `.txt`, `.json` files only.
- preserve folder structure.

## 9) Auditability
- `memory/approvals.md` is append-only.
- Canonical records must cross-link source artifacts and related approvals.

## 10) Trigger exactness guard
- Trigger spellings must stay exactly identical across:
  - `memory/PROTOCOL.md`
  - `.agents/skills/physicslab_memory/SKILL.md`
  - `memory/README.md` (quick reference list)
- Do not use underscore variants (for example `SESSION_PUBLISH`).
