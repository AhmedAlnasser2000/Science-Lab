> Snapshot generated during slice d9 from working tree based on HEAD 55fbe3f80f21b0722c1d7ab46aa5ee467f8cb766.
> Snapshot copy for portability; source-of-truth remains under docs/ at commit 55fbe3f80f21b0722c1d7ab46aa5ee467f8cb766.

# ui_system Agent Map

## Path(s)
- `ui_system/`
- app touchpoints: `app_ui/config.py`, `app_ui/main.py`, UI pack selectors in screens

## Role
- UI pack lifecycle, metadata handling, and runtime UI assets/services.

## Key symbols
- UI pack discovery/apply helpers, metadata readers, runtime style asset accessors.

## Edit-when
- UI pack selection or apply flow changes.
- UI metadata parsing/validation changes.
- Runtime UI asset policy changes.

## Risks/Notes
- Keep UI pack apply failures non-fatal where possible.
- Avoid hard-coding pack names in runtime code.

## NAV quick jumps
- placeholder (to backfill when ui_system NAV anchors are added).

