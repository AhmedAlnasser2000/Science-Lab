# Agent Safety & Workflow Header (Paste into every Codex prompt)
_Last updated: 2025-12-26_

This header is mandatory for all agent-assisted work on PhysicsLab, especially when the agent has elevated/“full access” mode.

---

## 0) Hard safety boundaries (do NOT violate)
- You may ONLY read/write files inside the repo workspace folder.
- FORBIDDEN: any path outside the repo (e.g., `C:\Users\...`, `Downloads`, `Documents`, `Desktop`, `C:\Windows`, `Program Files`, external drives).
- FORBIDDEN destructive commands:
  - `del`, `rmdir /s`, `Remove-Item -Recurse`, `rm -rf`
  - `git reset --hard`, `git clean -fdx`, `git push --force`
- If you believe a forbidden action is required, STOP and ask.

---

## 1) Don’t guess meanings
- “Vx.y…” is a VERSION milestone label only (e.g., V4.15b). Not a file, schema field, or feature flag.
- “Management Core” = `core_center/` (optional). Do not invent another “core”.
- “Kernel” = `kernel/` (supreme authority). Do not bypass its boundaries.

---

## 2) RECON is required before editing
Before making changes:
1) Identify the existing seam/truth source(s) involved.
2) Find the code paths currently used (open path, policy path, inventory path).
3) List the exact files you will touch (Touchlist).
4) State what you will NOT touch (Forbidden list).

If RECON reveals ambiguity, stop and ask rather than guessing.

---

## 3) Milestone discipline: Functionality vs UX
Default pattern:
- MVP milestone = functionality baseline (contracts correct; UI can be basic)
- Next milestone = UX polish (no contract changes)

Do not mix functionality and UX redesign in the same milestone unless explicitly requested.

---

## 4) Verification is mandatory (must run)
Run compile checks:
```bash
python -m compileall app_ui content_system core_center component_runtime runtime_bus ui_system schemas diagnostics
