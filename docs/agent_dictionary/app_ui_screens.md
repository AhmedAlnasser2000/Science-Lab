# app_ui/screens Agent Map

Focused map for high-traffic screens.

## system_health.py
- **Path:** `app_ui/screens/system_health.py`
- **Role:** Operational control panel (runs, maintenance, modules, jobs, pillars, crashes).
- **Key symbols:** `SystemHealthScreen`, `CrashViewerPanel`, `_BusDispatchBridge`, `TaskWorker`.
- **Edit-when:** Segment UI behavior, bus-driven status updates, pillars/crash workflows.
- **NAV anchors:** `[NAV-20]`, `[NAV-30..36]`, `[NAV-90]`
- **Risks/Notes:** Integrates multiple bus topics and diagnostics providers; keep event handlers stable.

## workspace_management.py
- **Path:** `app_ui/screens/workspace_management.py`
- **Role:** Workspace create/switch/delete, import/export, and template application.
- **Key symbols:** `WorkspaceManagementScreen`, `_request_inventory_snapshot`, `_diff_dicts`.
- **Edit-when:** Workspace lifecycle and template UX.
- **NAV anchors:** `[NAV-20]`, `[NAV-30]`, `[NAV-40]`, `[NAV-90]`
- **Risks/Notes:** I/O heavy; avoid breaking config persistence and import summary flow.

## content_browser.py
- **Path:** `app_ui/screens/content_browser.py`
- **Role:** Content browsing and pack/module visibility UX.
- **Key symbols:** screen-level content browser classes and filters.
- **Edit-when:** browsing UX, selection behavior, display filtering.
- **NAV anchors:** file-local.
- **Risks/Notes:** Shares workspace context; verify active workspace updates.

## component_management.py
- **Path:** `app_ui/screens/component_management.py`
- **Role:** Component inventory and management operations.
- **Key symbols:** screen-level component management classes and actions.
- **Edit-when:** component list/actions or status presentation.
- **NAV anchors:** file-local.
- **Risks/Notes:** Works with registry/storage operations; avoid accidental destructive defaults.

## block_catalog.py
- **Path:** `app_ui/screens/block_catalog.py`
- **Role:** Block catalog browsing and filtering.
- **Key symbols:** catalog view and filter helpers.
- **Edit-when:** catalog display, filtering logic, block metadata UX.
- **NAV anchors:** file-local.
- **Risks/Notes:** Keep taxonomy/terms alignment with `ui_helpers/terms.py`.

## block_host.py
- **Path:** `app_ui/screens/block_host.py`
- **Role:** Block host workflow and block runtime handoff UI.
- **Key symbols:** host screen class and launch/action handlers.
- **Edit-when:** host workflow, attach/detach flow, host-state rendering.
- **NAV anchors:** file-local.
- **Risks/Notes:** Entry surface for downstream runtime behavior; preserve launch contract.
