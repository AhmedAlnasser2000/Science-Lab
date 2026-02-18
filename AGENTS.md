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

Gate workflow is mandatory for slice work.

Rules:
- Start a slice session before substantial slice edits:
  - `python tools/dev/slice_session.py start <slice_id>`
- Record progress continuously:
  - `python tools/dev/slice_session.py note "..."`
  - `python tools/dev/slice_session.py gate <gate_name> --kind ui|backend`
- Close backend gates only with command/test evidence.
- Leave UI gates open until user confirms in-app behavior.
- Do not commit slice implementation until session + gates exist under `.slice_tmp/<slice_id>/`.
- If work started without session, backfill session/gates before commit.

Gate sequencing policy:
- Default is sequential: one gate at a time.
- After each gate implementation/verification summary, stop and wait for user confirmation before moving to the next gate.
- Open/close multiple gates in one step only when the user explicitly requests batch handling.

Mid-gate change policy:
- Purpose:
  - Prevent hidden scope growth inside one gate.
  - Keep verification evidence matched to exactly one acceptance target.
- Classification step (must be explicit in a note before proceeding):
  - What changed
  - Why it changed
  - What risk class it touches: `ui-only`, `logic`, `persistence`, `contract`, `performance`, `safety`
  - Which files and tests are affected
- Keep change in current gate only if **all** are true:
  - Acceptance target of current gate is unchanged.
  - No new risk class beyond what this gate already covered.
  - Existing verification plan still fully validates the change.
  - No new user-facing behavior outside the gate statement.
- Split into follow-up gate if **any** is true:
  - Acceptance target changed or expanded.
  - New risk class appears (especially `logic`, `persistence`, `contract`, `safety`).
  - New validation steps/tests are required.
  - Change affects additional surfaces not in current gate.
  - Reviewer/user could reasonably read it as a different fix.
- Backend risk discovered during a UI gate:
  - Open backend follow-up gate immediately.
  - Complete backend verification first.
  - Return to UI gate only after backend gate is resolved or explicitly blocked.
- Gate naming convention for follow-ups:
  - `<gate_name>_followup_1`, `<gate_name>_followup_2`, etc.
  - Keep names stable and descriptive (no generic `misc`/`extra`).
- Required gate note fields for every mid-gate change:
  - `trigger` (what prompted the change)
  - `decision` (stay in gate vs split)
  - `reason`
  - `files_touched`
  - `verification_delta` (new/changed tests or checks)
  - `user_impact`
- Gate close rule:
  - Do not close a gate with unresolved scope changes.
  - Do not close a gate if evidence only covers part of the final behavior in that gate.

Commit naming policy (non-ambiguous):
- Commit messages must include slice id and a specific scope.
- For follow-up commits in the same slice/scope, add an explicit suffix, e.g.:
  - `fix(V5.5d7): facet labels and glyph spacing (follow-up 1)`
  - `fix(V5.5d7): facet labels and glyph spacing (follow-up 2)`
- In user status/final updates, always map each commit hash to a one-line summary.

PR handoff completeness policy (mandatory):
- When providing PR title + summary/body for a slice, content must cover the full slice delta on that branch, not a partial subset.
- PR title rule:
  - Keep title focused on what was actually achieved by committed changes in that slice branch.
  - Do not title PR as only `chore`/`docs` if commits also include feature/fix work.
- PR summary rule:
  - Summary/body must be more descriptive than title and include all significant shipped themes in that branch/slice.
- The agent must check branch commits since slice start (or agreed base) and ensure major change categories are represented:
  - features/fixes
  - docs/policy updates
  - tests/tooling changes
- If a PR title/body only describes one category while branch includes others, the agent must revise it before presenting.
- Before final PR handoff, include a brief coverage checklist mapping:
  - commit ranges/hashes -> summarized themes
  - and confirm no significant slice changes are omitted.
- If there is any ambiguity about intended PR scope, stop and ask before proposing final PR text.

Operational note:
- Closing the app window does not stop terminal workflow; continue via terminal/tests/gates and relaunch app for UI verification.


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
