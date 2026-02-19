---
name: physicslab_worktrees
description: Start and clean PhysicsLab slice branches safely using git worktrees. Use when asked to create/start a slice branch (for example V5.5d2), start a milestone branch, or create a new worktree.
---

# PhysicsLab Worktrees

Use this skill when the user asks to start a new slice/milestone branch or create a worktree.

## Behavior

1. If branch name is missing, ask for it.
2. Start with safe defaults (no push):
   - `powershell ./tools/dev/start_slice_worktree.ps1 -Branch work/vX.Yz`
3. Remind the user:
   - Do all work inside the created worktree folder.
   - Push is disabled unless explicitly requested (`-Push`).
   - The start script enforces `fetch + ff-only pull` for local `main` vs `origin/main`; if main is ahead/diverged, repair main first.
4. Before wrapping up a slice, always provide:
   - one suggested PR title based on what was actually achieved in committed slice changes
   - a descriptive PR summary/body that covers all major change themes in that branch/slice.
5. If hot-reload gate workflow is active for the slice:
   - start/maintain `tools/dev/slice_session.py` artifacts under `.slice_tmp/<slice_id>/`
   - run gates sequentially by default (one gate, stop for user confirmation)
   - only batch multiple gates when the user explicitly asks
   - classify mid-gate changes and split into follow-up gates when scope/risk expands
   - keep commit messages non-ambiguous with explicit follow-up suffixes when repeating scope.
6. Before any push, enforce pre-push confirmation:
   - print push plan with branch, upstream target, and commits to be pushed
   - verify branch/slice match
   - wait for explicit user approval
   - if unclear, commit locally only and do not push.
7. Enforce same-slice branch containment:
   - keep all slice changes (code/docs/policies/tests/tweaks) on the same slice branch
   - verify current branch against `.physicslab_worktree.json` when available
   - if mismatch is detected, stop and present recovery plan before any commit/push
   - do not push mixed-slice commit batches.
8. Enforce no-leftover-commits + main-sync timing:
   - at slice handoff (or before switching slices), run/report:
     - `git status --short`
     - `git log --oneline @{u}..` (or equivalent ahead check)
   - if branch is ahead, either:
     - push after pre-push confirmation, or
     - record explicit user-approved deferral
   - do not begin the next slice with implicit unpushed commits.
   - sync `main` at two times:
     - after PR merge: `fetch` + `checkout main` + `pull --ff-only`
     - before starting the next slice: re-verify local `main` matches `origin/main`.
9. If wrong-branch edits are discovered, run patch-first recovery:
   - stop edits on wrong branch
   - create `.slice_tmp/<slice_id>/wrong_branch_recovery.patch` in the correct slice
   - export exact diff from wrong branch to that file
   - reapply from patch artifact only (no memory retype)
   - verify parity before commit (no missing/extra hunks)
   - use commit message suffix `(recovered-from-wrong-branch)`
   - report source branch, target branch, patch path, and verification method.

## One-liners

- Start (local only):
  - `powershell ./tools/dev/start_slice_worktree.ps1 -Branch work/v5.5d2`
- Start after syncing from remote main explicitly:
  - `git fetch origin --prune; git checkout main; git pull --ff-only origin main; powershell ./tools/dev/start_slice_worktree.ps1 -Branch work/v5.5d2`
- Start and push upstream (explicit only):
  - `powershell ./tools/dev/start_slice_worktree.ps1 -Branch work/v5.5d2 -Push`
- List worktrees:
  - `powershell ./tools/dev/list_worktrees.ps1`
- Cleanup worktree + local branch:
  - `powershell ./tools/dev/remove_slice_worktree.ps1 -Branch work/v5.5d2 -DeleteBranch`
