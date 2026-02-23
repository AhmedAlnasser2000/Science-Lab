---
name: physicslab_memory
description: Use the root memory bundle (`memory/`) for portable recall, trigger-gated writes, session publishing, and discussion approval flow.
---

# PhysicsLab Memory

Use this skill when the user asks to capture/promote memory artifacts, publish sessions, update checkpoints/indexes, or save/archive/approve discussions.

## Behavior

1. Recall order when ambiguous:
   - Read `memory/INDEX.md` and canonical memory docs first.
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

3. Discussion lane policy:
   - Discussions are non-binding context by default.
   - Do not create canonical decisions/issues/runbooks from discussions unless explicit `DISCUSSION APPROVE` (or explicit `MEMORY PROMOTE` referencing the discussion source).

4. Approval ledger policy:
   - `DISCUSSION APPROVE` must append a ledger line in `memory/approvals.md` with:
     - datetime
     - approver
     - source discussion
     - canonical targets
     - commit hash (once committed)

5. Session publishing policy:
   - `SESSION PUBLISH` exports from `.slice_tmp/<slice_id>/` into `memory/sessions/<slice_id>/`.
   - Create/update a journal entry in `memory/journal/`.
   - Update `memory/INDEX.md` links.

6. Trigger exactness guard:
   - Keep the same trigger spellings in:
     - `memory/PROTOCOL.md`
     - `.agents/skills/physicslab_memory/SKILL.md`
     - `memory/README.md`
   - Do not introduce underscore variants.

## One-liners

- `MEMORY CAPTURE`: store raw import + manifest + inbox/index pointer.
- `MEMORY PROMOTE`: turn approved source into canonical decision/issue/runbook + index update.
- `SESSION PUBLISH`: export slice artifacts to `memory/sessions/` + journal entry.
- `CHECKPOINT UPDATE`: refresh `memory/current-state.md` + checkpoint pointers.
- `INDEX UPDATE`: update only `memory/INDEX.md`.
- `DISCUSSION SAVE`: create discussion in `memory/discussions/active/` from template.
- `DISCUSSION ARCHIVE`: move discussion active -> archived and update discussion index.
- `DISCUSSION APPROVE`: create canonical extract + update approvals ledger + update index.
