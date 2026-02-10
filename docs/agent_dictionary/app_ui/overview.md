# app_ui Agent Map

This page is a short entry map. For CodeSee details, use [app_ui/codesee](codesee.md).

## Entry Points
- **Path:** `app_ui/main.py`
  - **Role:** Main app startup + screen wiring.
  - **Key symbols:** `MainWindow`, imports of `CodeSeeScreen` / `CodeSeeWindow`.
  - **Edit-when:** Navigation, top-level screen registration, startup guards.
  - **Do-not-touch / risks:** Keep import paths stable for existing screens.

- **Path:** `app_ui/screens/`
  - **Role:** Non-CodeSee app screens.
  - **Edit-when:** Feature work outside architecture visualization.
  - **See:** [app_ui/screens map](screens.md)

- **Path:** `app_ui/codesee/`
  - **Role:** CodeSee runtime + UI + dialogs + graph canvas.
  - **Edit-when:** CodeSee-only feature and bug fixes.
  - **See:** [app_ui/codesee dictionary](codesee.md)

- **Path:** `app_ui/widgets/`
  - **Role:** Shared UI components reused by multiple screens.
  - **Edit-when:** Header/selector behavior and reusable widget styling.
  - **See:** [app_ui/widgets map](widgets.md)

- **Path:** `app_ui/labs/`
  - **Role:** Lab host and plugin labs.
  - **Edit-when:** Lab launcher flow, plugin registration, lab-level UX.
  - **See:** [app_ui/labs map](labs.md)

- **Path:** `app_ui/config.py`, `app_ui/versioning.py`
  - **Role:** UI policy/config defaults and app/build identity.
  - **Edit-when:** defaults, profile flags, version/build display rules.
  - **Do-not-touch / risks:** avoid hardcoding milestone/version values.

## Edit-When Quick Guide

- Change top-level navigation or screen routing:
  - `app_ui/main.py`
- Change a feature screen:
  - `app_ui/screens/*` (then update `screens.md` map if needed)
- Change reusable control behavior:
  - `app_ui/widgets/*`
- Change lab plugin behavior:
  - `app_ui/labs/*`
- Change CodeSee:
  - `app_ui/codesee/*` via `codesee.md`

## NAV Quick Jumps

- `app_ui/main.py [NAV-90] MainWindow`
- `app_ui/screens/system_health.py [NAV-35] Segments/panels: Pillars`
- `app_ui/screens/content_browser.py [NAV-31A] ctor / dependencies`
- `app_ui/kernel_bridge.py [NAV-30] Public bridge API`
- `app_ui/safe_viewer.py [NAV-20] SafeViewer entrypoints`
- `app_ui/config.py [NAV-10] Config loading (defaults/roaming/policy)`
- `app_ui/ui_scale.py [NAV-20] Apply-to-Qt helpers`
- `app_ui/versioning.py [NAV-10] Build info / version API`
- `app_ui/window_state.py [NAV-10] Save/restore window state`
- `app_ui/screens/block_catalog.py [NAV-30] Filtering/search/sort`
- `app_ui/screens/block_host.py [NAV-30] Component mount/host lifecycle`
- `app_ui/screens/component_management.py [NAV-40] Progress/polling`
- `app_ui/widgets/app_header.py [NAV-30] Signals/actions`
- `app_ui/widgets/workspace_selector.py [NAV-30] Events + update flow`
- `app_ui/labs/host.py [NAV-30] Guide panel + tier gating`
