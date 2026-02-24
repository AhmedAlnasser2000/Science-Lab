---
name: physicslab_memory
description: Use the root memory bundle (`memory/`) for portable recall, trigger-gated writes, session publishing, and discussion approval flow.
---

# PhysicsLab Memory

Use this skill when the user asks to capture/promote memory artifacts, publish sessions, update checkpoints/indexes, or save/archive/approve discussions.

## Behavior

1. Recall order when ambiguous:
   - For app-state/development recall ("did you remember", "from what we did", "last time"), read `memory/canon/verbatim_ledger.md` first.
   - Then read `memory/INDEX.md` and other canonical memory docs.
   - Verify claims in code/repo before asserting truth.
   - Consult `memory/discussions/*` only when explicitly referenced or needed.

2. Strict write gate:
   - Do not write under `memory/` unless the user command includes one exact trigger:
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
   - Accepted aliases (input-only):
     - `MC` => `MEMORY CAPTURE`
     - `MP` => `MEMORY PROMOTE`
     - `SP` => `SESSION PUBLISH`
     - `CU` => `CHECKPOINT UPDATE`
     - `IU` => `INDEX UPDATE`
     - `DS` => `DISCUSSION SAVE`
     - `DC` => `DISCUSSION ARCHIVE`
     - `DA` => `DISCUSSION APPROVE`
     - `CS` => `CANON SAVE` (also accepted as explicit short trigger phrase)
   - Alias policy:
     - aliases are reserved and unique,
     - alias matching is case-insensitive,
     - canonical command names are used for approvals/index/canonical records.
   - Alias help command:
     - `H` / `h` prints current alias mappings and trigger list.
     - This helper command does not write to `memory/`.
   - Canon-save exactness:
     - `CANON SAVE` and `CS` are both exact trigger phrases.
     - `CS` is not alias-only behavior.
   - Worklog-auto exactness:
     - `WORKLOG AUTO ON` and `WORKLOG AUTO OFF` are exact trigger phrases.
     - No short aliases are defined for these commands yet.

2.1 Git approval gate:
   - Do not run `git commit` without explicit user approval.
   - Do not run `git push` without explicit user approval.
   - Always show a short commit/push plan and wait for approval.
   - Workflow aliases:
     - `AC` => approve commit
     - `AP` => approve push
     - aliases are case-insensitive
   - `AC`/`AP` are workflow approvals only, not memory trigger commands.
   - Pre-commit plan is mandatory and must include:
     - active branch
     - intended slice branch
     - worktree branch proof (when available)
     - staged/unstaged file list
     - mixed-slice risk check
     - exact commit message
     - exact commit command
   - If branch/scope mismatch appears, stop and ask; no commit.

3. Discussion lane policy:
   - Discussions are non-binding context by default.
   - Do not create canonical decisions/issues/runbooks from discussions unless explicit `DISCUSSION APPROVE` (or explicit `MEMORY PROMOTE` referencing the discussion source).

4. Approval ledger policy:
   - `DISCUSSION APPROVE` must append a ledger line in `memory/approvals.md` with:
     - approved_at_local
     - approver
     - recorded_by_agent
     - recorded_at_local
     - source discussion
     - canonical targets
     - commit hash (once committed)
   - Identity split is mandatory:
     - `approver` = human authority
     - `recorded_by_agent` = assistant that wrote the record

4.1 Timestamp policy:
   - Use local timestamp fields for memory records (`*_at_local`) with timezone offset.
   - Include `user_region` and `user_timezone` in metadata for unambiguous context.
   - Avoid UTC-only placeholder records for new entries.

5. Session publishing policy:
   - `SESSION PUBLISH` exports from `.slice_tmp/<slice_id>/` into `memory/sessions/<slice_id>/`.
   - Create/update a journal entry in `memory/journal/`.
   - Update `memory/INDEX.md` links.

5.1 Operational auto mode policy:
   - `WORKLOG AUTO ON` enables operational auto updates after each completed task/gate/mid-gate.
   - Auto-update scope:
     - `memory/current-state.md`
     - `memory/sessions/`
     - `memory/journal/`
     - `memory/runbooks/` when procedure-level changes exist.
   - `WORKLOG AUTO OFF` disables this behavior.
   - Auto mode never writes canon directly and never auto-promotes decisions/issues.
   - Approval-first cycle is mandatory:
     - state what will be written,
     - wait for explicit user approval,
     - then write only approved items.

6. Trigger exactness guard:
   - Keep the same trigger spellings in:
     - `memory/PROTOCOL.md`
     - `.agents/skills/physicslab_memory/SKILL.md`
     - `memory/README.md`
   - Do not introduce underscore variants.
   - Keep alias table identical across the same files.


7.1 Status and supersession discipline:
   - Use shared statuses in memory artifacts: `draft`, `active`, `locked`, `superseded`, `rejected`, `completed`.
   - If a task/decision is replaced, mark it `superseded` and add:
     - `superseded_by`
     - `superseded_at_local`
     - `supersession_reason`
   - Do not delete old records when superseded.
   - When user rejects/replaces next task, log the outcome explicitly in session+journal task logs.
7. Canon-save behavior:
   - `CANON SAVE` / `CS` appends one verbatim record to `memory/canon/verbatim_ledger.md`.
   - Must include: `entry_id`, local timestamp, region/timezone, `recorded_by_agent`, source metadata.
   - Update `memory/canon/INDEX.md` latest/next IDs.
   - Do not auto-promote to world-canon/current-state/decisions/issues/runbooks.
   - After save, provide optional next commands only (`MEMORY PROMOTE`, `CHECKPOINT UPDATE`, `DISCUSSION APPROVE`).

## One-liners

- `MEMORY CAPTURE`: store raw import + manifest + inbox/index pointer.
- `MEMORY PROMOTE`: turn approved source into canonical decision/issue/runbook + index update.
- `SESSION PUBLISH`: export slice artifacts to `memory/sessions/` + journal entry.
- `CHECKPOINT UPDATE`: refresh `memory/current-state.md` + checkpoint pointers.
- `INDEX UPDATE`: update only `memory/INDEX.md`.
- `DISCUSSION SAVE`: create discussion in `memory/discussions/active/` from template.
- `DISCUSSION ARCHIVE`: move discussion active -> archived and update discussion index.
- `DISCUSSION APPROVE`: create canonical extract + update approvals ledger + update index.
- `CANON SAVE` / `CS`: append verbatim canon entry and return optional promotion suggestions.
- `WORKLOG AUTO ON`: enable automatic operational updates for current-state/sessions/journal/runbooks (when applicable).
- `WORKLOG AUTO OFF`: disable automatic operational updates and return to trigger-only writes.
- `H` / `h`: show current alias mappings and trigger list (no write).

