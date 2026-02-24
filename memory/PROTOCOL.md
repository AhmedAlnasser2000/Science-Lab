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
1. For app-state/development recall (for example: "did you remember", "from what we did", "last time"), read canon ledger first:
- `memory/canon/verbatim_ledger.md`
2. Then read canonical memory pointers and summaries:
- `memory/INDEX.md`
- `memory/current-state.md`
- `memory/sessions/checkpoints/*`
- `memory/decisions/*`
- `memory/issues/*`
- `memory/runbooks/*`
3. Verify claims in code/repo.
4. Consult `memory/discussions/*` only when explicitly referenced or needed for unresolved context.

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
- `CANON SAVE`
- `CS`
- `WORKLOG AUTO ON`
- `WORKLOG AUTO OFF`

### Trigger aliases (input convenience)
Canonical commands above remain source-of-truth. The following short aliases are accepted as input only:
- `MC` => `MEMORY CAPTURE`
- `MP` => `MEMORY PROMOTE`
- `SP` => `SESSION PUBLISH`
- `CU` => `CHECKPOINT UPDATE`
- `IU` => `INDEX UPDATE`
- `DS` => `DISCUSSION SAVE`
- `DC` => `DISCUSSION ARCHIVE`
- `DA` => `DISCUSSION APPROVE`
- `CS` => `CANON SAVE` (also accepted as explicit short trigger phrase)

Alias rules:
- aliases are reserved and non-reusable (global within memory protocol),
- alias matching is case-insensitive,
- canonical command names are used in approvals/index/canonical records.

Alias help command:
- `H` / `h` prints current alias mappings and trigger list.
- This is a helper command only and does not write to `memory/`.

Worklog auto note:
- `WORKLOG AUTO ON` and `WORKLOG AUTO OFF` are exact trigger phrases.
- No short aliases are defined for these commands yet.

Canon save note:
- `CANON SAVE` and `CS` are both exact trigger phrases.
- `CS` is not alias-only behavior.

## 3.1) Git approval guardrail (strict)
- Do not run `git commit` without explicit user approval.
- Do not run `git push` without explicit user approval.
- Before commit/push, present a short plan and wait for approval.
- Workflow approval aliases:
  - `AC` => explicit approval to run `git commit` after plan.
  - `AP` => explicit approval to run `git push` after plan.
  - aliases are case-insensitive.
- `AC`/`AP` are workflow approvals only (not memory write triggers).

## 3.2) Pre-commit plan contract
- Before any commit, present a commit plan and wait for explicit approval (`AC` or equivalent).
- Required plan fields:
  - active branch
  - intended slice branch
  - worktree branch proof when available
  - staged/unstaged file list
  - mixed-slice risk check
  - exact commit message
  - exact commit command
- Stop rules:
  - branch mismatch => stop, ask, no commit
  - mixed-slice scope without explicit approval => stop, ask, no commit

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

### `WORKLOG AUTO ON`
- Enable operational auto mode for this repo/workspace.
- While enabled, after each completed task/gate/mid-gate:
  - update `memory/current-state.md`,
  - update/add session artifact under `memory/sessions/`,
  - update/add journal entry under `memory/journal/`,
  - update `memory/runbooks/` when a repeatable operational procedure was added or changed.
- Canon remains explicit-only (`CS` / `CANON SAVE`).
- Decisions/issues remain explicit promotion/approval only.

### `WORKLOG AUTO OFF`
- Disable operational auto mode.
- After disable, writes return to trigger-only behavior.

### `INDEX UPDATE`
- Update only `memory/INDEX.md`.

### `H` / `h` (alias help)
- Show current trigger list and alias mappings.
- No writes are performed.

### `DISCUSSION SAVE`
- Create a discussion doc in `memory/discussions/active/` from template.
- Update `memory/discussions/INDEX.md`.
- Include provenance fields:
  - `recorded_by_agent`
  - `recorded_at_local`

### `CANON SAVE` / `CS`
- Append one verbatim entry to `memory/canon/verbatim_ledger.md`.
- Do not auto-update `current-state`, `decisions`, `issues`, `runbooks`, or `world-canon`.
- Immediately return suggested optional promotion commands (no auto-write), for example:
  - `MEMORY PROMOTE`
  - `CHECKPOINT UPDATE`
  - `DISCUSSION APPROVE`

### `DISCUSSION ARCHIVE`
- Move discussion doc from active to archived.
- Update `memory/discussions/INDEX.md`.

### `DISCUSSION APPROVE`
- Create canonical extract in `memory/decisions/`, `memory/issues/`, or `memory/runbooks/`.
- Link source discussion and approved extract.
- Update `memory/INDEX.md`.
- Mandatory append in `memory/approvals.md` with:
  - `approved_at_local`
  - `approver`
  - `recorded_by_agent`
  - `recorded_at_local`
  - `source`
  - `canonical_targets`
  - `commit_hash` once committed.

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

## 7.1) Current-state conventions
- `memory/current-state.md` may include `Locked decisions` and `Next task`.
- `Next task` is operational guidance only and never binding.
- User can reject/replace/pause `Next task` at any time for fixes or changed objectives.

## 7.2) Operational auto mode
- Auto mode is controlled only by explicit triggers:
  - `WORKLOG AUTO ON`
  - `WORKLOG AUTO OFF`
- Auto mode updates operational artifacts only:
  - `memory/current-state.md`
  - `memory/sessions/`
  - `memory/journal/`
  - `memory/runbooks/` (when procedure-level changes exist)
- Auto mode never writes canon directly and never auto-promotes decisions/issues.
- If auto mode is enabled and a completed task has no runbook-grade procedure change, skip runbook updates.
- Approval-first update cycle is mandatory even in auto mode:
  - state exactly what will be written,
  - wait for explicit user approval,
  - then write only approved items.


## 7.3) Status and supersession model
Use a shared status vocabulary across decisions/tasks/session logs:
- `draft`: captured but not approved/active.
- `active`: currently in execution.
- `locked`: approved baseline decision/plan.
- `superseded`: replaced by a newer approved item.
- `rejected`: explicitly declined by user.
- `completed`: execution finished and verified.

Supersession fields (when applicable):
- `supersedes`
- `superseded_by`
- `superseded_at_local`
- `supersession_reason`

Rules:
- Do not delete prior records when superseded; mark status and link replacement.
- `Next task` in `memory/current-state.md` must be tracked as `active`, `rejected`, `replaced`, or `completed` in session/journal logs.
- Commit-task logging uses `active -> completed` by default; if replaced before commit, mark `superseded` or `rejected` with reason.
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
- Distinguish:
  - `approver` = human decision authority
  - `recorded_by_agent` = assistant that wrote the memory record.

## 9.1) Timestamp standard
- Use user-local time fields by default:
  - `*_at_local` format: `YYYY-MM-DD HH:MM:SS +/-HH:MM`
- Include user locale context with:
  - `user_region`
  - `user_timezone`
- UTC-only placeholders are not preferred for new records.

## 9.2) Canon vs world-canon
- `memory/canon/verbatim_ledger.md` is the chronological saved-memory timeline.
- `memory/world-canon.md` stores durable invariants only.
- `CS` writes to canonical timeline only and never mutates `world-canon` automatically.

## 10) Trigger exactness guard
- Trigger spellings must stay exactly identical across:
  - `memory/PROTOCOL.md`
  - `.agents/skills/physicslab_memory/SKILL.md`
  - `memory/README.md` (quick reference list)
- Include `WORKLOG AUTO ON` and `WORKLOG AUTO OFF` exactly (no underscore variants).
- Include alias-help command `H` / `h` exactly as a non-write helper.
- Do not use underscore variants (for example `SESSION_PUBLISH`).
- Alias table must also stay aligned across the same files.


