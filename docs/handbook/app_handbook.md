# PhysicsLab Contributor Handbook

This document explains how the app fits together, based strictly on the verified code checkpoint in `docs/app_summary.md`.

## 1. Mental Model

PhysicsLab is a **PyQt6 desktop application** that uses a `QStackedWidget` to manage navigation between screens (Home, Content Browser, Labs, System Health).

*   **Entry Point**: The app starts in `app_ui/main.py:main`, which creates the `QApplication`, applies the active UI pack, and constructs the `MainWindow`.
*   **Labs**: Interactive simulations (Gravity, Projectile, etc.) are plugins wrapped by a `LabHost`. The host handles common features like the guide panel, export menu, and grid/axes toggles.
*   **Content**: Content is split between a **Repo** (canonical source) and a **Store** (installed/ready-to-use). The app only runs content that is "READY" (installed in the store).
*   **Bus**: A local, in-process `RuntimeBus` handles decoupling between components (e.g., System Health requesting storage reports from Core Center).
*   **Core Center**: An optional backend module for management tasks (registry, jobs, storage, policy). The UI works even if this module is missing.

> **Anchor**: `app_ui/main.py:main`, `app_ui/main.py:MainWindow.__init__`, `app_ui/labs/host.py:LabHost`, `content_system/loader.py:REPO_BASE`, `content_system/loader.py:STORE_BASE`, `app_ui/main.py:ContentBrowserScreen._open_selected`, `runtime_bus/bus.py:RuntimeBus`, `app_ui/main.py:SystemHealthScreen._refresh_report`, `app_ui/main.py:CORE_CENTER_AVAILABLE`

---

## 2. User Journeys

### Quick Start
1.  User clicks "Quick Start" on the Main Menu.
2.  The app calls `MainWindow._start_physics`.
3.  It searches for the **first READY lab part** (a part with `lab_id` or ending in `_demo`) via `MainWindow._find_quick_start_part`.
4.  If found, it opens the lab directly.
5.  If *none* are READY, it routes to the **Content Management** screen with an install message.

> **Anchor**: `app_ui/main.py:MainWindow._start_physics`, `app_ui/main.py:MainWindow._find_quick_start_part`, `app_ui/main.py:MainWindow.open_part_by_id`

### Physics Content
1.  User clicks "Physics Content".
2.  The app always opens the full **Content Browser** (`ContentBrowserScreen`).

> **Anchor**: `app_ui/main.py:MainWindow._open_content_browser`

### Install Flow
1.  User selects a part in **Content Browser** or **Content Management**.
2.  Triggers `download_part()` (or a module install job via Core Center).
3.  Assets are copied from `content_repo` to `content_store`.
4.  Status updates to `READY`.

> **Anchor**: `content_system/loader.py:download_part`, `app_ui/main.py:ContentBrowserScreen._install_selected`, `core_center/bus_endpoints.py:_handle_module_install`

---

## 3. Content System Explained

The system builds a hierarchy from `content_repo/physics_v1` and `content_store/physics_v1`.

### Status Model
*   **READY**: The part manifest exists in the **Store**, AND all referenced assets exist in the **Store**.
*   **NOT_INSTALLED**: Present in Repo but not fully in Store.
*   **UNAVAILABLE**: Missing from both or invalid.

> **Anchor**: `content_system/loader.py:STATUS_READY`, `content_system/loader.py:_compute_part_status`

### Repo vs. Store
*   **Repo**: `content_repo/physics_v1` (Read-only source).
*   **Store**: `content_store/physics_v1` (Runtime execution location).
*   **Installation**: `download_part()` copies the part directory and its referenced assets from Repo to Store.

> **Anchor**: `content_system/loader.py:REPO_BASE`, `content_system/loader.py:STORE_BASE`

### Asset Resolution
*   **Text**: `read_asset_text()` prefers Store path, falls back to Repo path.
*   **Visuals**: `AssetResolver` (used by RenderKit) enforces Store-root containment. It defaults to `content_store/physics_v1`.
*   **Caching**: `AssetCache` stores SVG renderers and pixmaps keyed by path/size/tint/DPI.

> **Anchor**: `app_ui/main.py:read_asset_text`, `app_ui/labs/renderkit/assets.py:AssetResolver`, `app_ui/labs/renderkit/assets.py:AssetCache`

---

## 4. Labs Explained

Labs are plugins registered in `app_ui/labs/registry.py`.

### The LabHost Wrapper
The `LabHost` wraps the specific lab widget. It provides:
*   **Guide Panel**: Displays markdown guides (`x_extensions.guides`).
*   **Export Menu**: Policy-gated export actions.
*   **Prefs**: Toggles for Grid and Axes.
*   **Context**: Injects run context (paths, settings).

> **Anchor**: `app_ui/labs/host.py:LabHost`

### Lab Context & Prefs
*   **Storage**: `data/roaming/lab_prefs.json`.
*   **Injection Order**: `LabHost` tries `set_context`, then `set_lab_context`, then falls back to setting attributes directly.
*   **Reduced Motion**: Read from UI config and passed to labs via `MainWindow._open_lab` -> `set_reduced_motion`.

> **Anchor**: `app_ui/labs/context.py:LabContext`, `app_ui/labs/host.py:_apply_lab_context`, `app_ui/main.py:MainWindow._open_lab`, `app_ui/config.py:get_reduced_motion`

---

## 5. Rendering Explanation

Newer labs (Electric Field, Lens Ray, Vector Add) use a shared rendering library and draw their visuals with shared primitives.

*   **RenderCanvas**: A layer-driven paint surface with its own transform.
*   **Shared Primitives**: `draw_grid`, `draw_axes`, `draw_vector` (using QPainter).
*   **Math/View**: `Vec2` for math, `ViewTransform` for world-to-screen mapping.
*   **Sprites**: RenderKit sprite helpers exist (e.g., `draw_arrow_sprite`) but are optional.

> **Anchor**: `app_ui/labs/renderkit/canvas.py:RenderCanvas`, `app_ui/labs/shared/primitives.py:draw_grid`, `app_ui/labs/shared/viewport.py:ViewTransform`, `app_ui/labs/renderkit/primitives.py:draw_arrow_sprite`

---

## 6. Kernel Bridge (Gravity Lab)

The Gravity Lab uses a Rust-based kernel for simulation, with a Python fallback.

*   **Bridge**: `app_ui/kernel_bridge.py` loads `physicslab_kernel.dll`.
*   **Loading**: Tries `kernel/target/release/` then `app_ui/native/`.
*   **Fallback**: If the DLL is missing (`KernelNotAvailable`), the lab switches to `PythonGravityBackend`.
*   **Session**: `GravityKernelSession` wraps the C-types interface.

> **Anchor**: `app_ui/kernel_bridge.py:DLL_CANDIDATES`, `app_ui/labs/gravity_lab.py:GravityLabWidget._init_backend`

---

## 7. Core Center (Optional)

Core Center is an optional management backend. The UI guards imports (`CORE_CENTER_AVAILABLE`) so the app runs without it.

*   **Discovery**: Scans content and UI packs.
*   **Registry**: Saved to `data/roaming/registry.json`.
*   **Jobs**: Background threads for install/cleanup; history in `data/roaming/jobs.json`.
*   **Storage**: Allocates run directories in `data/store/runs`.
*   **Policy**: Resolves defaults + overrides from `data/roaming/policy.json`.

> **Anchor**: `core_center/bus_endpoints.py:register_core_center_endpoints`, `core_center/discovery.py:discover_components`, `core_center/registry.py:save_registry`, `core_center/job_manager.py:JOB_HISTORY_PATH`, `core_center/storage_manager.py:allocate_run_dir`, `core_center/policy_manager.py:resolve_policy`, `app_ui/main.py:CORE_CENTER_AVAILABLE`

---

## 8. Runtime Bus

An in-process message bus for decoupling components.

*   **Mechanism**: Pub/Sub + Request/Reply.
*   **Debug**: Set `PHYSICSLAB_BUS_DEBUG=1` to see traffic.
*   **Global Instance**: Accessed via `get_global_bus()` and stored in `app_ui.main.APP_BUS`.
*   **Sticky Topics**: Used for state that needs to be available to late subscribers (e.g., reports).

> **Anchor**: `runtime_bus/bus.py:RuntimeBus`, `runtime_bus/bus.py:BUS_DEBUG`, `runtime_bus/bus.py:get_global_bus`, `runtime_bus/bus.py:RuntimeBus.publish`, `runtime_bus/bus.py:RuntimeBus.subscribe`, `app_ui/main.py:APP_BUS`

---

## 9. Data Layout

| Path | Purpose | Anchor |
| :--- | :--- | :--- |
| `data/roaming/ui_config.json` | UI Pack, Reduced Motion | `app_ui/config.py:CONFIG_PATH` |
| `data/roaming/experience_profile.json` | Active Profile | `app_ui/config.py:PROFILE_PATH` |
| `data/roaming/lab_prefs.json` | Grid/Axes toggles | `app_ui/labs/prefs_store.py:PREFS_PATH` |
| `data/roaming/registry.json` | Discovery registry (modules, UI packs, labs) | `core_center/registry.py:save_registry` |
| `data/roaming/jobs.json` | Job History | `core_center/job_manager.py:JOB_HISTORY_PATH` |
| `data/store/runs/<lab>/<run>/` | Run Data | `core_center/storage_manager.py:allocate_run_dir` |
| `data/store/runs_local/` | Fallback Run Data | `app_ui/labs/host.py:_create_local_run_dir` |

---

## 10. Extension Recipes

### Add a Lab
1.  Create `app_ui/labs/<lab>.py` implementing `LabPlugin`.
2.  Register it in `app_ui/labs/registry.py`.
3.  Add a content part manifest with `x_extensions.lab.lab_id`.

> **Anchor**: `app_ui/labs/base.py:LabPlugin`, `app_ui/labs/registry.py`

### Add Content
1.  Add manifests to `content_repo/physics_v1`.
2.  Install via `content_system.download_part()` or the Module Management screen.

> **Anchor**: `content_system/loader.py:download_part`

### Add UI Pack
1.  Create `ui_repo/ui_v1/packs/<id>/ui_pack_manifest.json` and QSS files.
2.  Select it in Settings or edit `ui_config.json`.

> **Anchor**: `ui_system/manager.py:_load_manifest`

### Add Core Center Endpoint
1.  Add topic constant in `runtime_bus/topics.py`.
2.  Register handler in `core_center/bus_endpoints.py`.
3.  Call via `RuntimeBus.request(...)` in UI.

> **Anchor**: `core_center/bus_endpoints.py:register_core_center_endpoints`, `runtime_bus/bus.py:RuntimeBus.request`

---

## 11. Troubleshooting

*   **ModuleManagerScreen**: Exists but is **not wired** into the main navigation.
*   **Content Loader**: Hard-wired to `physics_v1` roots; does not validate JSON schemas.
*   **Schemas**: `part_manifest.schema.json` contains duplicate `allOf` keys.
*   **Storage Report**: Contains unreachable code in `report_text`.
*   **Missing Assets**: `content_store/physics_v1/assets/lab_viz/` is not in the repo tree.

> **Anchor**: `app_ui/main.py:ModuleManagerScreen`, `content_system/loader.py:REPO_BASE`, `schemas/part_manifest.schema.json`, `core_center/storage_report.py:report_text`, direct repo reference: `content_store/physics_v1/assets/lab_viz`

---

## 12. Verification

To verify the app runs:

```bash
python -m app_ui.main
```

*   **Auto-verify**: Imports and bytecode compilation.
*   **Manual verify**: Open labs, toggle grid/axes, check persistence.

> **Anchor**: `app_ui/main.py:main`

Verification footer:
- Handbook content derived from checkpoint: `docs/app_summary.md`
- Commit: `77b4895`
