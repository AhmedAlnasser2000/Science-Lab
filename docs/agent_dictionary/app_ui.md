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

- **Path:** `app_ui/codesee/`
  - **Role:** CodeSee runtime + UI + dialogs + graph canvas.
  - **Edit-when:** CodeSee-only feature and bug fixes.
  - **See:** [app_ui/codesee dictionary](app_ui_codesee.md)
