# Worktree-first slice workflow

This folder contains local-only helper scripts for starting and cleaning slice worktrees safely.

## Scripts

- `start_slice_worktree.ps1`
  - Creates a new branch in a new worktree outside repo root.
  - Refuses to run on dirty working tree.
  - Refuses existing branch/path unless `-Force` is explicitly provided for branch checks.
  - Push is opt-in via `-Push`.

- `list_worktrees.ps1`
  - Shows registered worktrees and whether each is clean/dirty.

- `remove_slice_worktree.ps1`
  - Removes a worktree safely.
  - Refuses when that worktree has uncommitted changes.
  - Optional local branch delete with safety checks.

## Safety model

- No auto-stash.
- No destructive cleanup commands (`reset --hard`, `clean -fd`).
- No remote branch deletion.
- Default is local-only (no push).

## Typical usage

Start a slice locally:

```powershell
powershell ./tools/dev/start_slice_worktree.ps1 -Branch work/v5.5d2
```

List worktrees:

```powershell
powershell ./tools/dev/list_worktrees.ps1
```

Cleanup:

```powershell
powershell ./tools/dev/remove_slice_worktree.ps1 -Branch work/v5.5d2 -DeleteBranch
```

## Failure conditions

Start script fails if:
- repo is dirty,
- base ref cannot be resolved,
- branch exists locally/remotely (unless `-Force` for existence checks),
- destination path already exists,
- `main` cannot fast-forward cleanly.

Remove script fails if:
- it cannot resolve a target path,
- worktree is dirty,
- branch has unique commits vs base and `-ForceDeleteBranch` is not provided.
