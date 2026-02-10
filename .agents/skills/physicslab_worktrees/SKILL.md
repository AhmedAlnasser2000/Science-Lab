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
4. Before wrapping up a slice, always provide:
   - one suggested PR title
   - a concise PR summary/body ready to paste into GitHub.

## One-liners

- Start (local only):
  - `powershell ./tools/dev/start_slice_worktree.ps1 -Branch work/v5.5d2`
- Start and push upstream (explicit only):
  - `powershell ./tools/dev/start_slice_worktree.ps1 -Branch work/v5.5d2 -Push`
- List worktrees:
  - `powershell ./tools/dev/list_worktrees.ps1`
- Cleanup worktree + local branch:
  - `powershell ./tools/dev/remove_slice_worktree.ps1 -Branch work/v5.5d2 -DeleteBranch`
