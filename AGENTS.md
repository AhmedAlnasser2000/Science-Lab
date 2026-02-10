## Git Hygiene: Worktree-First

This repository uses a worktree-first workflow for all new slices/milestones.

Rules:
- Start new work via `tools/dev/start_slice_worktree.ps1`.
- Do not create new slice branches in-place in the main repo folder.
- Do not run destructive git commands (`git reset --hard`, `git clean -fd`) unless explicitly requested by the user.
- Default workflow is local commit only. Push/PR only when explicitly requested.
- If user asks to start a slice (example: `V5.5d2`), use worktree workflow first.
- Respect `.gitattributes` line endings to avoid CRLF/LF churn.
  - Repo defaults: source/docs stay `LF`; PowerShell scripts (`*.ps1`) stay `CRLF`.
  - On Windows, prefer `git config --global core.autocrlf false` and `git config --global core.safecrlf warn`.

Quick start:
- `powershell ./tools/dev/start_slice_worktree.ps1 -Branch work/v5.5d2`
- `powershell ./tools/dev/list_worktrees.ps1`
- `powershell ./tools/dev/remove_slice_worktree.ps1 -Branch work/v5.5d2 -DeleteBranch`
