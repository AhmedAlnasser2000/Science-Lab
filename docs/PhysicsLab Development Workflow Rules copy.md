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
