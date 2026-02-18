## Git Hygiene: Worktree-First

This repository uses a worktree-first workflow for all new slices/milestones.

Rules:
- Start new work via `tools/dev/start_slice_worktree.ps1`.
- Do not create new slice branches in-place in the main repo folder.
- Do not run destructive git commands (`git reset --hard`, `git clean -fd`) unless explicitly requested by the user.
- Default workflow is local commit only. Push/PR only when explicitly requested.
- If user asks to start a slice (example: `V5.5d2`), use worktree workflow first.
- Enforce `origin/main` sync before slice start (`fetch` + `pull --ff-only`); if local `main` is ahead/diverged, stop and repair first.
- Before finalizing a slice, provide a suggested PR title and concise PR summary/body.
- Before finalizing a slice, provide a suggested PR title and a concise PR summary/body in plain text.
- Respect `.gitattributes` line endings to avoid CRLF/LF churn.
  - Repo defaults: source/docs stay `LF`; PowerShell scripts (`*.ps1`) stay `CRLF`.
  - On Windows, prefer `git config --global core.autocrlf false` and `git config --global core.safecrlf warn`.

Quick start:
- `powershell ./tools/dev/start_slice_worktree.ps1 -Branch work/v5.5d2`
- `powershell ./tools/dev/list_worktrees.ps1`
- `powershell ./tools/dev/remove_slice_worktree.ps1 -Branch work/v5.5d2 -DeleteBranch`

## Hot-Reload Gate Workflow: Permanent Policy

This repository now treats gate-based slice workflow as mandatory for all new slices.

Rules:
- Start a slice session before substantial edits:
  - `python tools/dev/slice_session.py start <slice_id>`
- Record progress continuously:
  - `python tools/dev/slice_session.py note "..."`
  - `python tools/dev/slice_session.py gate <gate_name> --kind ui|backend`
- Close backend gates only with command/test evidence.
- Leave UI gates open until user confirms in-app behavior, then close with:
  - `python tools/dev/slice_session.py gate-done <gate_name> --result pass|fail|blocked`
- Do not commit slice code until the session and gate artifacts exist under `.slice_tmp/<slice_id>/`.
- If work began before session start, create the session retroactively in the same slice and backfill gates/notes before committing.
- Use non-destructive finalize by default:
  - `python tools/dev/slice_session.py finalize <slice_id>`
  - delete only with explicit intent: `--delete`

Operational note:
- Closing the app window does not end terminal workflow. Keep using terminal evidence (tests/logs/gates) and relaunch app when UI verification is needed.


## Skills
A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and file path so you can open the source for full instructions when using a specific skill.
### Available skills
- skill-creator: Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Codex's capabilities with specialized knowledge, workflows, or tool integrations. (file: C:/Users/ahmed/.codex/skills/.system/skill-creator/SKILL.md)
- skill-installer: Install Codex skills into $CODEX_HOME/skills from a curated list or a GitHub repo path. Use when a user asks to list installable skills, install a curated skill, or install a skill from another repo (including private repos). (file: C:/Users/ahmed/.codex/skills/.system/skill-installer/SKILL.md)
### How to use skills
- Discovery: The list above is the skills available in this session (name + description + file path). Skill bodies live on disk at the listed paths.
- Trigger rules: If the user names a skill (with `$SkillName` or plain text) OR the task clearly matches a skill's description shown above, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- Missing/blocked: If a named skill isn't in the list or the path can't be read, say so briefly and continue with the best fallback.
- How to use a skill (progressive disclosure):
  1) After deciding to use a skill, open its `SKILL.md`. Read only enough to follow the workflow.
  2) When `SKILL.md` references relative paths (e.g., `scripts/foo.py`), resolve them relative to the skill directory listed above first, and only consider other paths if needed.
  3) If `SKILL.md` points to extra folders such as `references/`, load only the specific files needed for the request; don't bulk-load everything.
  4) If `scripts/` exist, prefer running or patching them instead of retyping large code blocks.
  5) If `assets/` or templates exist, reuse them instead of recreating from scratch.
- Coordination and sequencing:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- Context hygiene:
  - Keep context small: summarize long sections instead of pasting them; only load extra files when needed.
  - Avoid deep reference-chasing: prefer opening only files directly linked from `SKILL.md` unless you're blocked.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- Safety and fallback: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue.
