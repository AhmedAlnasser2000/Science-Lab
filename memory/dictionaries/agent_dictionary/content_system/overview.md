> Snapshot generated during slice d9 from working tree based on HEAD 55fbe3f80f21b0722c1d7ab46aa5ee467f8cb766.
> Snapshot copy for portability; source-of-truth remains under docs/ at commit 55fbe3f80f21b0722c1d7ab46aa5ee467f8cb766.

# content_system Agent Map

## Path(s)
- `content_system/`
- app touchpoints: `app_ui/screens/content_browser.py`, `app_ui/screens/system_health.py`

## Role
- Content manifest validation, install orchestration, and content runtime services.

## Key symbols
- Validation/report helpers, install/uninstall pipeline functions, content tree/list APIs.

## Edit-when
- Content validation rules.
- Install/uninstall behavior.
- Content diagnostics surfaced in app screens.

## Risks/Notes
- Validation schema changes can affect existing content packs.
- Keep install pipeline resilient to partial failures.

## NAV quick jumps
- placeholder (to backfill when content_system NAV anchors are added).

