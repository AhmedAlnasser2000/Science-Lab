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
   - one suggested PR title
   - a concise PR summary/body ready to paste into GitHub.
5. If hot-reload gate workflow is active for the slice:
   - start/maintain `tools/dev/slice_session.py` artifacts under `.slice_tmp/<slice_id>/`
   - run gates sequentially by default (one gate, stop for user confirmation)
   - only batch multiple gates when the user explicitly asks
   - classify mid-gate changes and split into follow-up gates when scope/risk expands
   - keep commit messages non-ambiguous with explicit follow-up suffixes when repeating scope.

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
