# app_ui Agent Map

This page is a short entry map. For CodeSee details, use [app_ui/codesee](app_ui_codesee.md).

## Entry Points
- **Path:** `app_ui/main.py`
  - **Role:** Main app startup + screen wiring.
  - **Key symbols:** `MainWindow`, imports of `CodeSeeScreen` / `CodeSeeWindow`.
  - **Edit-when:** Navigation, top-level screen registration, startup guards.
  - **Do-not-touch / risks:** Keep import paths stable for existing screens.

- **Path:** `app_ui/screens/`
  - **Role:** Non-CodeSee app screens.
  - **Edit-when:** Feature work outside architecture visualization.
  - **See:** [app_ui/screens map](app_ui_screens.md)

- **Path:** `app_ui/codesee/`
  - **Role:** CodeSee runtime + UI + dialogs + graph canvas.
  - **Edit-when:** CodeSee-only feature and bug fixes.
  - **See:** [app_ui/codesee dictionary](app_ui_codesee.md)

- **Path:** `app_ui/widgets/`
  - **Role:** Shared UI components reused by multiple screens.
  - **Edit-when:** Header/selector behavior and reusable widget styling.
  - **See:** [app_ui/widgets map](app_ui_widgets.md)

- **Path:** `app_ui/labs/`
  - **Role:** Lab host and plugin labs.
  - **Edit-when:** Lab launcher flow, plugin registration, lab-level UX.
  - **See:** [app_ui/labs map](app_ui_labs.md)

- **Path:** `app_ui/config.py`, `app_ui/versioning.py`
  - **Role:** UI policy/config defaults and app/build identity.
  - **Edit-when:** defaults, profile flags, version/build display rules.
  - **Do-not-touch / risks:** avoid hardcoding milestone/version values.

## Edit-When Quick Guide

- Change top-level navigation or screen routing:
  - `app_ui/main.py`
- Change a feature screen:
  - `app_ui/screens/*` (then update `app_ui_screens.md` map if needed)
- Change reusable control behavior:
  - `app_ui/widgets/*`
- Change lab plugin behavior:
  - `app_ui/labs/*`
- Change CodeSee:
  - `app_ui/codesee/*` via `app_ui_codesee.md`

## NAV Quick Jumps

- `app_ui/main.py [placeholder -> NAV tag]`
- `app_ui/screens/system_health.py [placeholder -> NAV tag]`
- `app_ui/screens/content_browser.py [placeholder -> NAV tag]`
- `app_ui/kernel_bridge.py [placeholder -> NAV tag]`
- `app_ui/safe_viewer.py [placeholder -> NAV tag]`
- `app_ui/config.py [placeholder -> NAV tag]`
- `app_ui/ui_scale.py [placeholder -> NAV tag]`
- `app_ui/versioning.py [placeholder -> NAV tag]`
- `app_ui/window_state.py [placeholder -> NAV tag]`
- `app_ui/screens/block_catalog.py [placeholder -> NAV tag]`
- `app_ui/screens/block_host.py [placeholder -> NAV tag]`
- `app_ui/screens/component_management.py [placeholder -> NAV tag]`
- `app_ui/widgets/app_header.py [placeholder -> NAV tag]`
- `app_ui/widgets/workspace_selector.py [placeholder -> NAV tag]`
- `app_ui/labs/host.py [placeholder -> NAV tag]`
