# PhysicsLab Development Workflow Rules
_Last updated: 2025-12-26_

This doc defines how we separate **functionality** work from **UX** work so we don’t constantly second-guess whether we’re “doing it in the right order,” especially when redefining foundation systems.

## Core principle
When building or redefining a base system, separate the work into two phases:

1) **MVP (Functionality / Contract correctness)**  
2) **Polish (UX / presentation + usability)**

Do **not** mix them in the same milestone unless explicitly stated.

---

## What “Functionality” means
Functionality is anything that affects correctness, truth sources, or safety.

Functionality-first is required when work touches:
- **Data contracts** (inventory, schemas/validation rules, manifest semantics)
- **Truth sources** (Management Core inventory/jobs/runs, policies)
- **State machines** (job terminal states, enable/disable rules)
- **Open paths** (how a Block/Activity is launched)
- **Persistence** (project prefs, workspace state, run storage)
- Anything that could cause **data loss**, **stuck jobs**, **corruption**, or **wrong status reporting**

**Allowed UI during functionality milestones:** ugly but accurate.

---

## What “UX” means
UX is presentation, layout, wording, affordances, and discoverability, without changing the underlying contract.

UX-first is appropriate when:
- Contracts are stable and verified
- The user experience is confusing or cluttered
- You are standardizing a UI pattern (catalog layouts, navigation consistency)
- You are improving flow without changing underlying state behavior

**Rule:** UX milestones must not alter data contracts or truth sources.

---

## The standard milestone pattern
Every feature should typically be delivered as two milestones:

### Milestone A — MVP (Functionality baseline)
**Goal:** prove the loop works end-to-end using existing seams.  
**DoD:**
- Compile checks pass
- App runs without crash
- Manual test checklist passes
- States are accurate and safe (no guessing)

**UI is allowed to be basic.**

### Milestone B — UX Polish
**Goal:** make it understandable, efficient, and pleasant.  
**DoD:**
- No contract changes
- Same data sources and open paths
- Improvements are mostly layout, labels, and minor affordances

**If UX requires new capabilities:** create a new Functionality milestone first, then polish.

---

## Freeze points (to reduce “foundation anxiety”)
When a system feels “base-defining,” introduce freeze points:

### Freeze Point 1 — Contract Freeze
Document the non-negotiables:
- Definitions (Pack, Block, Topic/Unit/Lesson/Activity, Project)
- Truth source ownership (Management Core is authoritative)
- Enable/disable rules
- What “open” means
- Persistence boundaries

After Contract Freeze, UX can iterate freely without re-litigating semantics.

### Freeze Point 2 — UI Pattern Freeze
Once a UI surface stabilizes, document the standard layout pattern
(e.g., Catalog: left navigation → center list/grid → right details).

UI Pattern Freeze can happen later than Contract Freeze.

---

## Decision filter (use this every time)
Ask: **If we shipped this tomorrow, what’s the bigger risk?**

- **Wrong behavior** (bad states, incorrect enable/disable, data loss, stuck jobs)  
  → do Functionality first.

- **User confusion** (can’t find it, can’t understand it, UX clutter)  
  → do UX next (without changing contracts).

---

## Practical rules for Codex/agents
Agents must follow these rules unless explicitly overridden:

1) **Start with RECON**  
   - Identify truth sources and existing seams  
   - List exact files to touch before editing

2) **Touchlist / Forbidden list are binding**  
   - No edits outside Touchlist  
   - If uncertain, stop and ask

3) **Verification is mandatory**
   - `python -m compileall ...` on relevant folders
   - Run the app once (`python -m app_ui.main`)
   - Provide manual tests

4) **Checkpoint frequently**
   - Commit after MVP baseline
   - Commit after UX polish

5) **Hot-reload gates are sequential by default**
   - For slice execution, use `tools/dev/slice_session.py` with notes and gates under `.slice_tmp/<slice_id>/`.
   - Run one gate at a time and stop for user confirmation before the next gate.
   - Batch gate progression is allowed only with explicit user request.

6) **Commit naming must be explicit and unique**
   - Include slice id + concrete scope in every commit message.
   - For repeated/follow-up commits in same area, append a follow-up suffix:
     - `(follow-up 1)`, `(follow-up 2)`, etc.
   - In handoff updates, always map commit hash to a plain one-line description.

6.1) **Pre-push confirmation is mandatory**
   - Before any push, print a push plan and wait for explicit user approval.
   - Push plan must include:
     - active branch
     - target remote branch
     - commit list to be pushed (hash + summary)
     - ahead/behind/diverged state vs upstream
     - exact push command
   - If branch/slice mismatch is detected, stop and ask.
   - If upstream differs from intended slice branch, stop and ask.
   - If user asks "commit and push", still present the plan first, then push only after explicit confirmation.
   - If intent is ambiguous, default to local commit only (no push).

6.2) **Same-slice branch containment is mandatory**
   - Keep all slice-related changes on the same slice branch from first edit to final push.
   - Include all change categories:
     - code, tests, docs, policy files, workflow files, and tiny follow-up tweaks.
   - Verify branch identity before commit and push using:
     - `git rev-parse --abbrev-ref HEAD`
     - `.physicslab_worktree.json` `branch` value (when file exists)
   - If branch mismatch is found:
     - stop immediately
     - do not commit or push
     - present recovery plan and wait for approval
   - If wrong-branch commit already happened:
     - transfer to correct branch first
     - verify on correct branch
     - clean wrong branch with approved recovery action
   - Do not push mixed-slice commit batches.

6.3) **No unpushed leftovers + main sync timing**
   - At slice handoff (or before switching to a new slice), always report:
     - `git status --short`
     - branch ahead check vs upstream (`git log --oneline @{u}..` or equivalent)
   - If commits are ahead of upstream:
     - push with pre-push confirmation, or
     - explicitly record user-approved deferment.
   - Do not move to next slice with implicit/unreported unpushed commits.
   - Main sync timing is fixed:
     - after PR merge, sync local `main` immediately (`fetch` + `checkout main` + `pull --ff-only`)
     - before creating the next slice, re-check local `main` against `origin/main`
     - if local `main` is ahead/diverged, stop and repair before slice start.

6.4) **PR title/summary must match full slice outcome**
   - PR title should reflect what was achieved by committed changes in the slice branch.
   - PR summary/body should be descriptive and include all major change themes present in that branch/slice.
   - Do not publish misleading PR metadata that mentions only one subset (for example only `chore`) when feature/fix commits are also included.
   - Validate title/summary against commit list before handoff.

6.5) **PR conflict prevention + deterministic recovery**
   - Before each push to an open PR branch:
     - `git fetch origin --prune`
     - check branch state vs `origin/main` (ahead/behind/diverged)
   - If branch is behind main, integrate first:
     - rebase on `origin/main` (preferred) unless merge is explicitly chosen
     - resolve conflicts locally
     - rerun required verification/tests for touched scope
     - then push.
   - If history was rewritten by rebase:
     - only use `git push --force-with-lease`
     - never use plain `--force`.
   - Pre-push confirmation remains mandatory even during conflict recovery.
   - If conflicts occur, write recovery evidence to:
     - `.slice_tmp/<slice_id>/pr_conflict_recovery.md`
     - include conflicted files, resolution basis, and verification evidence.
   - If PR is already merged/closed:
     - do not append unrelated new work to that branch
     - start a new follow-up branch from updated `main`.

7) **Mid-gate changes: split only when needed**
   - **First classify the change** in the gate note:
     - what changed
     - why it changed
     - risk class (`ui-only`, `logic`, `persistence`, `contract`, `performance`, `safety`)
     - affected files/tests
   - **Keep in current gate** only when all are true:
     - same acceptance target
     - no new risk class
     - existing verification still sufficient
     - no additional user-facing behavior outside gate scope
   - **Create follow-up gate** when any are true:
     - acceptance target changed/expanded
     - new risk class introduced
     - extra validation or tests required
     - additional surfaces touched beyond gate scope
   - **UI gate + backend risk discovered**:
     - open backend follow-up gate immediately
     - resolve backend gate first, then return to UI gate
   - **Naming for follow-up gates**:
     - `<gate_name>_followup_1`, `<gate_name>_followup_2`, ...
   - **Do not close a gate** with unresolved scope changes or partial evidence.

8) **Discuss first, implement second (explicit approval required)**
   - Before implementing any new idea/step/gate, discuss scope, approach, and tradeoffs first.
   - Do not begin implementation edits until the user explicitly approves start (for example: "go", "proceed", "implement").
   - Read-only recon is allowed before approval; write actions must wait for approval.

9) **Policy updates require conflict-check first**
   - Before adding/changing policy rules, audit current policy docs to avoid conflicts or duplicates.
   - Minimum audit targets:
     - `AGENTS.md`
     - `docs/handbook/workflow_rules.md`
   - Prefer merging into existing sections rather than adding parallel rules.

10) **Gate completion output contract**
   - Every completed gate or mid-gate must be labeled as `Frontend` or `Backend`.
   - Classification:
     - any UI/manual in-app validation needed -> `Frontend`
     - pure logic/runtime/tests/docs with no UI behavior validation -> `Backend`
   - For `Frontend` completions, always provide:
     - manual verification checklist for the user (actions + expected results)
     - accurate summary of completed gate changes
     - exact next gate plan
   - For `Backend` completions, provide:
     - accurate summary only
     - no manual verification checklist

---

## Example: Block Catalog
- **MVP milestone**: prove pack → registry → policy → open path works, refresh on project change  
  UI can be a simple tree/details view.

- **UX milestone**: redesign into a Construct-like catalog (pack list + grid + details)  
  No changes to policy rules, inventory sources, or open path.

---

## Glossary (for workflow context)
- **Project**: unified workspace/sandbox context (Unity/Godot style)
- **Pack**: installable container of Blocks (inventory owned by Management Core when available)
- **Block**: a runtime-openable component (may wrap a LabHost-backed experience)
- **Topic/Unit/Lesson/Activity**: curriculum-facing hierarchy used for educational organization
