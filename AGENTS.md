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

Pre-implementation discussion policy (mandatory):
- Before implementing any new idea/step/gate, discuss scope, approach, and tradeoffs with the user first.
- Do not start implementation edits until explicit user approval to proceed (for example: "go", "proceed", "implement").
- Read-only recon is allowed before approval; write actions must wait for approval.

Policy conflict-check rule (mandatory):
- Before adding or changing workflow/policy rules, audit existing rules first to avoid conflicting or duplicate instructions.
- Minimum audit targets:
  - `AGENTS.md`
  - `docs/handbook/workflow_rules.md`
- Merge into existing sections whenever possible; avoid creating parallel rules that say the same thing differently.

Gate completion output contract (mandatory):
- Every completed gate or mid-gate must be explicitly labeled as `Frontend` or `Backend`.
- Classification rule:
  - Any gate that touches UI/manual in-app behavior is `Frontend`.
  - Pure logic/runtime/tests/docs with no UI behavior validation is `Backend`.
- For `Frontend` completions, always provide:
  - manual verification checklist for the user (`action` + expected result)
  - accurate summary of what changed in the completed gate
  - exact next gate plan
- For `Backend` completions, provide:
  - accurate summary of what changed
  - no manual verification checklist

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

Pre-push confirmation policy (mandatory, no exceptions):
- At the end of gates, before any push, the agent must print a push plan and wait for explicit user approval.
- Required push-plan fields:
  - active branch (`git rev-parse --abbrev-ref HEAD`)
  - target remote branch (for example `origin/work/v5.5d7`)
  - list of commit hashes to push (short hash + one-line message)
  - whether branch is ahead/behind/diverged vs upstream
  - exact push command that will be executed
- If branch name and slice id do not match user intent, stop and ask; do not push.
- If upstream branch differs from requested slice branch, stop and ask; do not push.
- If the user says "commit and push", still show push plan first and require explicit "yes/push".
- Default behavior if unclear: commit locally only, no push.
- After push, report:
  - pushed branch
  - resulting remote range (for example `abc1234..def5678`)
  - remaining local commits (if any).

Unpushed commits + main sync policy (mandatory):
- Do not end a slice with unknown local-only commits.
- At slice handoff (or before moving to another slice), always run and report:
  - `git status --short`
  - `git log --oneline @{u}..` (or equivalent ahead check)
- If commits are ahead of upstream:
  - either push them after pre-push confirmation, or
  - get explicit user confirmation to defer push.
- Do not start the next slice until this ahead/defer state is explicit.
- Main sync timing:
  - **After PR merge:** sync local `main` immediately (`fetch` + `checkout main` + `pull --ff-only`).
  - **Before starting any new slice:** re-verify `main` is up to date with `origin/main`.
  - If local `main` is ahead/diverged, stop and repair before slice creation.

Same-slice branch containment policy (mandatory, no exceptions):
- All changes for an active slice must stay in that slice branch from first edit through final push.
- This applies to every change type:
  - features, fixes, docs, policy updates, tests, tiny tweaks, workflow files, and prompt amendments.
- Before commit and before push, the agent must verify branch identity using both:
  - `git rev-parse --abbrev-ref HEAD`
  - `.physicslab_worktree.json` (`branch` field) when present
- If these do not match the intended slice branch, stop and ask; do not commit, do not push.
- If work is discovered on a wrong branch:
  - freeze further edits immediately
  - present a recovery plan (target branch, commits affected, transfer method)
  - move changes first (for example cherry-pick or equivalent safe port)
  - verify moved changes on the correct slice branch
  - only then commit/push on the correct branch
  - clean the wrong branch (revert/reset only with explicit user approval)
- Mixed-slice commit batches are forbidden.
  - If a commit contains content from different slice IDs/scopes, split before push.
- End-of-gates push plan must explicitly state:
  - active branch
  - intended slice branch
  - proof they match
  - exact commits that belong to this slice only.

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

PR conflict prevention + resolution policy (mandatory):
- Objective:
  - avoid merge-conflict PRs when possible
  - resolve unavoidable conflicts with deterministic, auditable steps.
- Prevention checks (before each push to an open PR branch):
  - `git fetch origin --prune`
  - compare branch vs `origin/main` (`ahead/behind/diverged`)
  - if branch is behind `origin/main`, integrate first (rebase preferred unless user requests merge).
- Required pre-push integration for behind branches:
  - `git rebase origin/main` (or approved merge alternative)
  - resolve conflicts locally
  - rerun required verification/tests for touched scope
  - only then push.
- Force push safety:
  - if rebase rewrites history, only use `--force-with-lease`
  - never use plain `--force`
  - still require pre-push confirmation plan before push.
- Conflict recovery record (when conflicts occur):
  - create `.slice_tmp/<slice_id>/pr_conflict_recovery.md`
  - list conflicted files, chosen resolution basis, and verification evidence.
- Closed/merged PR branch rule:
  - do not continue adding unrelated commits to a merged/closed slice branch.
  - create a new slice/follow-up branch from updated `main` for new policy or feature deltas.

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
