# app_ui/widgets Agent Map

Core reusable widget surfaces used across screens.

## app_header.py
- **Path:** `app_ui/widgets/app_header.py`
- **Role:** App header/title actions and consistent top-row UX.
- **Key symbols:** `AppHeader`.
- **Edit-when:** shared header behavior, top action affordances, branding/header spacing.
- **NAV anchors:** `[NAV-00]` imports/constants, `[NAV-20]` AppHeader widget, `[NAV-30]` signals/actions.
- **Risks/Notes:** Used broadly; changes ripple across many screens.

## workspace_selector.py
- **Path:** `app_ui/widgets/workspace_selector.py`
- **Role:** Workspace chooser/activation UI component.
- **Key symbols:** `WorkspaceSelector`.
- **Edit-when:** workspace switch UX and selector event behavior.
- **NAV anchors:** `[NAV-00]` imports/constants, `[NAV-20]` selector widget, `[NAV-30]` event/update flow.
- **Risks/Notes:** Used by multiple screens; keep signal API stable.

## other shared widgets
- **Path:** `app_ui/widgets/` (remaining modules)
- **Role:** Reusable controls and compact display components.
- **Edit-when:** only when behavior should be shared across multiple screens.
- **NAV anchors:** file-local.
- **Risks/Notes:** Prefer screen-local overrides first; shared widget edits are high blast radius.
