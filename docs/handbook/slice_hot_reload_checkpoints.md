# Slice Hot-Reload Checkpoints
_Last updated: 2026-02-18_

## Purpose
This workflow defines how to run one larger slice with explicit checkpoints ("gates"), pause for confirmation between gates, and keep temporary slice notes in a local scratch area that can be deleted after acceptance.

## Gate model
A gate is a named checkpoint inside one slice.

- UI gate: requires visual verification in the app.
- Backend gate: requires command/test verification.

Each gate must have:
- Name
- Kind (`ui` or `backend`)
- Opened timestamp
- Result (`pass`, `fail`, `blocked`)
- Evidence notes

## UI gate checklist
For UI gates, the agent should provide:
- Exact steps to reproduce
- Expected behavior
- What the user should confirm
- Any screenshots or short notes requested by the user

## Backend gate checklist
For backend gates, the agent should provide:
- Exact commands run
- Pass/fail summary
- If failed: short root-cause + next fix attempt

## Stop-and-wait rule
After each gate summary, Codex must stop and ask to continue before starting the next gate.

Required handoff text pattern:
- Gate name/kind
- What changed in this gate
- Verification result
- Explicit question: "Proceed to next gate?"

## Bugfix attempt limit (3-tries rule)
For one bug in one gate:
- Try up to 3 focused fixes.
- After 3 unsuccessful attempts, stop and report:
  - attempted fixes
  - evidence from each attempt
  - recommended next options

Do not continue silently past failed attempts.

## Amendments convention (prompt self-amendments)
Prompt refinement is allowed during the same slice.

Standard:
- Add an `## Amendments` section in the active prompt document.
- Append each refinement with:
  - timestamp (UTC)
  - gate number/name
  - request text
  - status (`Applied`, `Deferred`, or `Withdrawn`)
  - optional rollback commit if withdrawn after implementation

If the prompt is large, create a sibling file:
- `<prompt_name>__amendments.md`
- Link it from the prompt file.

## Scratch workspace
Use `.slice_tmp/<slice_id>/...` for temporary gate state and notes.

Expected contents:
- `state.json`
- `notes.md`
- `gates/*.md`

`.slice_tmp/` must stay ignored by git.

## Finalize definition
"Finalize" means:
1. Keep only committed docs/tests/tooling files in the repo.
2. Delete `.slice_tmp/<slice_id>`.
3. Confirm cleanup in the gate summary.

## Safe rollback guidance
Use lightweight git rollback by context:

- Not pushed:
  - `git reset --hard <good_commit>`
- Already pushed:
  - `git revert <bad_commit>`

For slice branch/worktree operations, use existing scripts:
- `tools/dev/start_slice_worktree.ps1`
- `tools/dev/list_worktrees.ps1`
- `tools/dev/remove_slice_worktree.ps1`

## Minimal helper usage
Use `tools/dev/slice_session.py`:

```bash
python tools/dev/slice_session.py start V5.5d6
python tools/dev/slice_session.py note "Gate 1 started"
python tools/dev/slice_session.py gate inspector-routing --kind ui
python tools/dev/slice_session.py gate-done inspector-routing --result pass
python tools/dev/slice_session.py finalize V5.5d6
```
