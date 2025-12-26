# PhysicsLab App Summary (Code-Verified Checkpoint)

## App at a glance (verified features)
- PyQt6 desktop app using a QStackedWidget main window with multiple screens and labs (Anchor: `app_ui/main.py:MainWindow.__init__`).
- Quick Start selects the first READY lab part and opens it directly; if none are READY, it routes to Content Management with an install message (Anchor: `app_ui/main.py:MainWindow._start_physics`, `app_ui/main.py:MainWindow._find_quick_start_part`).
- Physics Content always opens the full Content Browser (Anchor: `app_ui/main.py:MainWindow._open_content_browser`, `app_ui/main.py:ContentBrowserScreen`).
- Registered labs: gravity, projectile, electric_field, lens_ray, vector_add (Anchor: `app_ui/labs/registry.py`).
- LabHost wraps lab widgets with guide panel, export menu (policy-gated), Grid/Axes toggles, and run context injection (Anchor: `app_ui/labs/host.py:LabHost`).
- Core Center is optional; UI imports are guarded and the app continues without it (Anchor: `app_ui/main.py:CORE_CENTER_AVAILABLE`).
- Runtime bus is local, in-process pub/sub + request/reply with sticky topics and optional debug logging (Anchor: `runtime_bus/bus.py:RuntimeBus`, `runtime_bus/bus.py:BUS_DEBUG`).

## High-level architecture (modules + boundaries)
- `app_ui/`: UI, navigation, labs (entry: `python -m app_ui.main`) (Anchor: `app_ui/main.py:main`).
- `content_system/`: content hierarchy loader + part installer (Anchor: `content_system/loader.py:list_tree`, `content_system/loader.py:download_part`).
- `runtime_bus/`: in-process bus types and topics (Anchor: `runtime_bus/bus.py`, `runtime_bus/messages.py`, `runtime_bus/topics.py`).
- `core_center/`: optional discovery/registry/jobs/storage/policy endpoints (Anchor: `core_center/bus_endpoints.py:register_core_center_endpoints`).
- `content_repo/physics_v1/`: canonical content pack; `content_store/physics_v1/` is the installed mirror (Anchor: `content_system/loader.py:REPO_BASE`, `content_system/loader.py:STORE_BASE`).
- `ui_system/` + `ui_repo/` + `ui_store/`: UI pack manager and QSS packs (Anchor: `ui_system/manager.py:list_packs`).
- `kernel/`: Rust DLL for gravity kernel, bridged in Python (Anchor: `app_ui/kernel_bridge.py`).

## Startup + navigation flow
- Entry: `app_ui/main.py:main` creates QApplication, applies UI pack, constructs MainWindow, and starts the event loop (Anchor: `app_ui/main.py:main`, `app_ui/main.py:apply_ui_config_styles`).
- MainWindow wires screens into a QStackedWidget and routes callbacks (Anchor: `app_ui/main.py:MainWindow.__init__`).
- Quick Start uses `ContentSystemAdapter.list_tree()` to find the first READY lab part and opens it directly (Anchor: `app_ui/main.py:MainWindow._find_quick_start_part`, `app_ui/main.py:MainWindow.open_part_by_id`).
- Physics Content always opens ContentBrowserScreen (Anchor: `app_ui/main.py:MainWindow._open_content_browser`).

## Screens and what each one does
- MainMenuScreen: Home buttons with profile gating (Anchor: `app_ui/main.py:MainMenuScreen._rebuild_buttons`).
- ContentBrowserScreen: tree view, install part, open lab or markdown preview (Anchor: `app_ui/main.py:ContentBrowserScreen.refresh_tree`, `app_ui/main.py:ContentBrowserScreen._install_selected`, `app_ui/main.py:ContentBrowserScreen._open_selected`).
- SystemHealthScreen: storage report (bus-first, direct fallback), cleanup, module install/uninstall (Explorer), job history (Explorer) (Anchor: `app_ui/main.py:SystemHealthScreen._refresh_report`, `app_ui/main.py:SystemHealthScreen._start_cleanup_job`, `app_ui/main.py:SystemHealthScreen._show_comm_report`, `app_ui/main.py:SystemHealthScreen._start_module_job`).
- ModuleManagementScreen: registry table and module install/uninstall via bus (Anchor: `app_ui/main.py:ModuleManagementScreen._refresh_registry`, `app_ui/main.py:ModuleManagementScreen._start_job`).
- ContentManagementScreen: filterable tree, status pill, module actions, double-click opens part in browser (Anchor: `app_ui/main.py:ContentManagementScreen._apply_filter`, `app_ui/main.py:ContentManagementScreen._on_item_double_clicked`, `app_ui/main.py:StatusPill`).
- SettingsDialog: UI pack selection, reduced motion, experience profile (Anchor: `app_ui/main.py:SettingsDialog._save_settings`).
- ModuleManagerScreen exists but is not wired into MainWindow navigation (Anchor: `app_ui/main.py:ModuleManagerScreen`, `app_ui/main.py:MainWindow.__init__`).

## Content system (install + browse + status model)
- Hierarchy built from `content_repo/physics_v1` and `content_store/physics_v1` (Anchor: `content_system/loader.py:list_tree`).
- Status model: READY / NOT_INSTALLED / UNAVAILABLE (Anchor: `content_system/loader.py:STATUS_READY`, `content_system/loader.py:STATUS_NOT_INSTALLED`, `content_system/loader.py:STATUS_UNAVAILABLE`).
- READY requires store manifest + all referenced assets in content_store (Anchor: `content_system/loader.py:_compute_part_status`, `content_system/loader.py:_collect_asset_paths`).
- Lab metadata comes from `x_extensions.lab.lab_id` and is surfaced as `part["lab"]` (Anchor: `content_system/loader.py:_extract_lab_metadata`, `content_system/loader.py:get_part`).
- `download_part()` copies part directory and referenced assets from repo to store (Anchor: `content_system/loader.py:download_part`).
- ContentSystemAdapter in UI wraps content_system calls and converts exceptions into status records (Anchor: `app_ui/main.py:ContentSystemAdapter`).

## Labs system (plugins + LabHost + context)
- LabPlugin contract and optional export/telemetry hooks (Anchor: `app_ui/labs/base.py:LabPlugin`).
- Registered labs: gravity, projectile, electric_field, lens_ray, vector_add (Anchor: `app_ui/labs/registry.py`).
- LabHost provisions policy/run context, guides, export actions, telemetry, and user prefs (Anchor: `app_ui/labs/host.py:LabHost`).
- LabContext + per-lab Grid/Axes prefs stored in `data/roaming/lab_prefs.json` (Anchor: `app_ui/labs/context.py:LabContext`, `app_ui/labs/prefs_store.py:PREFS_PATH`).
- LabHost injects context via `set_context`, `set_lab_context`, or attribute fallback (Anchor: `app_ui/labs/host.py:_apply_lab_context`).
- Guides use `x_extensions.guides` keyed by profile, with store-first asset resolution (Anchor: `app_ui/main.py:MainWindow._load_lab_guide_text`, `app_ui/main.py:read_asset_text`).
- Gravity lab uses kernel backend with Python fallback (Anchor: `app_ui/labs/gravity_lab.py:KernelGravityBackend`, `app_ui/labs/gravity_lab.py:PythonGravityBackend`).
- Projectile lab is pure-Python QPainter simulation (Anchor: `app_ui/labs/projectile_lab.py:ProjectileLabWidget`, `app_ui/labs/projectile_lab.py:ProjectileCanvas`).
- Electric Field / Lens Ray / Vector Add use RenderCanvas with shared viewport and primitives (Anchor: `app_ui/labs/electric_field_lab.py`, `app_ui/labs/lens_ray_lab.py`, `app_ui/labs/vector_add_lab.py`).

## Rendering helpers (shared library)
- Vec2 math helpers (Anchor: `app_ui/labs/shared/math2d.py:Vec2`).
- World<->screen transforms (Anchor: `app_ui/labs/shared/viewport.py:ViewTransform`).
- QPainter primitives for grid/axes/vectors (Anchor: `app_ui/labs/shared/primitives.py:draw_grid`, `app_ui/labs/shared/primitives.py:draw_axes`, `app_ui/labs/shared/primitives.py:draw_vector`).
- RenderCanvas provides a layer-driven paint surface with its own transform (Anchor: `app_ui/labs/renderkit/canvas.py:RenderCanvas`).

## Runtime bus (topics + flows)
- In-process bus with publish/subscribe/request, sticky topics, and debug output via `PHYSICSLAB_BUS_DEBUG=1` (Anchor: `runtime_bus/bus.py:RuntimeBus.publish`, `runtime_bus/bus.py:RuntimeBus.subscribe`, `runtime_bus/bus.py:BUS_DEBUG`).
- Message envelope schema (Anchor: `runtime_bus/messages.py:MessageEnvelope`).
- Topic constants (Anchor: `runtime_bus/topics.py`).
- Global bus instance via `get_global_bus()` (Anchor: `runtime_bus/bus.py:get_global_bus`, `app_ui/main.py:APP_BUS`).

## Core Center (optional; bus endpoints + jobs)
- Optional import in UI; endpoints registered when available (Anchor: `app_ui/main.py:CORE_CENTER_BUS_ENDPOINTS`, `core_center/bus_endpoints.py:register_core_center_endpoints`).
- Discovery scans content_repo/content_store/ui_repo/ui_store plus lab registry (Anchor: `core_center/discovery.py:discover_components`).
- Registry saved to `data/roaming/registry.json` (Anchor: `core_center/registry.py:save_registry`).
- Jobs run in background threads and record history in `data/roaming/jobs.json` (Anchor: `core_center/job_manager.py:create_job`, `core_center/job_manager.py:JOB_HISTORY_PATH`).
- Storage report includes runs footprint (Anchor: `core_center/storage_report.py:generate_report`, `core_center/storage_manager.py:summarize_runs`).
- Policy defaults + overrides (Anchor: `core_center/policy_manager.py:DEFAULT_POLICY`, `core_center/policy_manager.py:resolve_policy`).
- Run directories allocated in `data/store/runs/<lab>/<run>` with retention (Anchor: `core_center/storage_manager.py:allocate_run_dir`, `core_center/storage_manager.py:enforce_run_retention`).
- Endpoints: report, cleanup, policy, registry, run_dir allocation, module install/uninstall, jobs list/get (Anchor: `core_center/bus_endpoints.py:register_core_center_endpoints`).

## UI packs and theming
- Startup applies UI pack via `apply_ui_config_styles` and `ui_system.manager` (Anchor: `app_ui/main.py:apply_ui_config_styles`, `ui_system/manager.py:resolve_pack`).
- Settings dialog updates `data/roaming/ui_config.json` and re-applies the QSS (Anchor: `app_ui/main.py:SettingsDialog._save_settings`, `app_ui/config.py:save_ui_config`).
- Reduced motion is stored in ui_config and read by labs/LabHost (Anchor: `app_ui/config.py:get_reduced_motion`, `app_ui/labs/host.py:LabHost`, `app_ui/labs/*_lab.py:set_reduced_motion`).

## Data layout (runtime state + content)
- UI config: `data/roaming/ui_config.json` (Anchor: `app_ui/config.py:CONFIG_PATH`, `ui_system/manager.py:CONFIG_PATH`).
- Experience profile: `data/roaming/experience_profile.json` (Anchor: `app_ui/config.py:PROFILE_PATH`).
- Policy overrides: `data/roaming/policy.json` (Anchor: `core_center/policy_manager.py:_policy_path`).
- Registry: `data/roaming/registry.json` (Anchor: `core_center/registry.py:save_registry`).
- Job history: `data/roaming/jobs.json` (Anchor: `core_center/job_manager.py:JOB_HISTORY_PATH`).
- Lab prefs: `data/roaming/lab_prefs.json` (Anchor: `app_ui/labs/prefs_store.py:PREFS_PATH`).
- Core run dirs: `data/store/runs/<lab>/<run>/run.json` (Anchor: `core_center/storage_manager.py:allocate_run_dir`).
- Local fallback runs: `data/store/runs_local/<lab>/<run>/run.json` (Anchor: `app_ui/labs/host.py:_create_local_run_dir`).
- Content repo/store roots: `content_repo/physics_v1`, `content_store/physics_v1` (Anchor: `content_system/loader.py:REPO_BASE`, `content_system/loader.py:STORE_BASE`).
- UI pack roots: `ui_repo/ui_v1`, `ui_store/ui_v1` (Anchor: `ui_system/manager.py:list_packs`).

## Extension recipes (anchored)
- Add a lab:
  1) Create `app_ui/labs/<lab>.py` implementing LabPlugin (Anchor: `app_ui/labs/base.py:LabPlugin`).
  2) Register in `app_ui/labs/registry.py`.
  3) Add a part manifest with `x_extensions.lab.lab_id` and guides (Anchor: `content_system/loader.py:_extract_lab_metadata`, `app_ui/main.py:MainWindow._load_lab_guide_text`).
- Add a content part:
  1) Add/modify content_repo manifests (Anchor: `content_repo/physics_v1/module_manifest.json`, `content_repo/physics_v1/sections/**/package_manifest.json`).
  2) Install via `content_system.download_part()` or module install job (Anchor: `content_system/loader.py:download_part`, `core_center/job_manager.py:_handle_module_install`).
- Add a UI pack:
  1) Create `ui_repo/ui_v1/packs/<id>/ui_pack_manifest.json` + QSS files (Anchor: `ui_system/manager.py:_load_manifest`).
  2) Set `data/roaming/ui_config.json` or use Settings dialog (Anchor: `app_ui/main.py:SettingsDialog._save_settings`).
- Add a Core Center endpoint:
  1) Add topic constant (Anchor: `runtime_bus/topics.py`).
  2) Register handler in `core_center/bus_endpoints.py`.
  3) Call via `RuntimeBus.request(...)` in UI (Anchor: `runtime_bus/bus.py:RuntimeBus.request`).

## Current limitations / TODOs (verified)
- ModuleManagerScreen exists but is not routed in the main navigation (Anchor: `app_ui/main.py:ModuleManagerScreen`, `app_ui/main.py:MainWindow.__init__`).
- Content loader is hard-wired to `physics_v1` roots (Anchor: `content_system/loader.py:REPO_BASE`, `content_system/loader.py:STORE_BASE`).
- Content loader does not validate JSON against schemas (Anchor: `content_system/loader.py:_load_json`).
- `schemas/part_manifest.schema.json` contains duplicate `allOf` keys (direct file reference: `schemas/part_manifest.schema.json`).
- `core_center/storage_report.py` has unreachable code after a `return` (direct file reference: `core_center/storage_report.py:report_text`).
- `content_store/physics_v1/assets/lab_viz/` is not present in the repo tree (direct repo reference: `content_store/physics_v1/assets/lab_viz`).

## What to read next (file pointers)
- Entry + routing: `app_ui/main.py`
- Labs contract + host: `app_ui/labs/base.py`, `app_ui/labs/host.py`
- Lab visuals: `app_ui/labs/shared/*`, `app_ui/labs/renderkit/canvas.py`, `app_ui/labs/renderkit/primitives.py`
- Content loader: `content_system/loader.py`
- Bus core: `runtime_bus/bus.py`, `runtime_bus/topics.py`
- Core Center endpoints/jobs: `core_center/bus_endpoints.py`, `core_center/job_manager.py`
- Core storage/policy: `core_center/storage_manager.py`, `core_center/storage_report.py`, `core_center/policy_manager.py`
- Content manifests: `content_repo/physics_v1/module_manifest.json`, `content_repo/physics_v1/sections/**/package_manifest.json`
- UI packs: `ui_system/manager.py`, `ui_repo/ui_v1/packs/*/ui_pack_manifest.json`

## Milestones and versioning
- Versioning convention (observed in commit messages):
  - V<major>.<minor> is used for changes, improvements, and additions.
  - V<major>.<minor>.<patch> is used for fixes and refactors.
  Anchor: `git log --oneline -n 40` (see Verification Appendix).

## Delta vs previous checkpoint
- Added: LabContext and per-lab prefs (Grid/Axes) with persistence (Anchor: `app_ui/labs/context.py`, `app_ui/labs/prefs_store.py`, `app_ui/labs/host.py:_on_prefs_changed`).
- Added: shared rendering helpers (Vec2, ViewTransform, painter primitives) (Anchor: `app_ui/labs/shared/*`).
- Modified: LabHost context injection order (tries `set_context` then `set_lab_context`) (Anchor: `app_ui/labs/host.py:_apply_lab_context`).
- Modified: Lab rendering description updated to shared primitives + RenderCanvas layers (Anchor: `app_ui/labs/electric_field_lab.py`, `app_ui/labs/lens_ray_lab.py`, `app_ui/labs/vector_add_lab.py`).
- Modified: SystemHealth description now uses job history button (jobs list) rather than runtime bus communication report (Anchor: `app_ui/main.py:SystemHealthScreen._show_comm_report`).
- Removed: claim that SVG sprites are required by current labs; current lab code does not call RenderKit sprite helpers (Anchor: `app_ui/labs/*_lab.py`, `app_ui/labs/renderkit/primitives.py`).

## Legacy / Needs manual re-verify
- ModuleManagerScreen behavior is not reachable through current navigation; if you intend to use it, wire it into MainWindow and re-verify its UI flow (Anchor: `app_ui/main.py:ModuleManagerScreen`).
- Any sprite-based lab visuals referenced by assets in `content_repo/physics_v1/assets/lab_viz/` require manual UI verification; current labs do not call RenderKit sprite helpers (Anchor: `content_repo/physics_v1/assets/lab_viz`, `app_ui/labs/renderkit/primitives.py`).

# Detailed Addendum (Checkpoint-ready)

## A) Kernel bridge and fallbacks (explained)

### What it does
The kernel bridge (`app_ui/kernel_bridge.py`) loads the Rust DLL and exposes a Python session API for the gravity simulation. The Gravity Lab uses the kernel if available; otherwise it falls back to a Python backend and reports the fallback in the UI (Anchor: `app_ui/kernel_bridge.py:GravityKernelSession`, `app_ui/labs/gravity_lab.py:GravityLabWidget._init_backend`).

ModuleManagerScreen includes a gravity-demo run preview that uses the kernel bridge, but this screen is not routed from MainWindow navigation (Anchor: `app_ui/main.py:ModuleManagerScreen._run_selected_part`, `app_ui/main.py:MainWindow.__init__`).

### Exact load sequence (ordered)
- `create_gravity_session()` -> `GravityKernelSession.__init__()` -> `_get_lib()` -> `_resolve_symbols()` -> `_load_library()` (Anchor: `app_ui/kernel_bridge.py`).
- `_load_library()` tries DLLs in order:
  1) `kernel/target/release/physicslab_kernel.dll`
  2) `app_ui/native/physicslab_kernel.dll` (Anchor: `app_ui/kernel_bridge.py:DLL_CANDIDATES`).
- When loaded, ctypes binds `pl_world_create`, `pl_world_destroy`, `pl_world_step`, `pl_world_get_state`, `pl_last_error_code`, `pl_last_error_message` (Anchor: `app_ui/kernel_bridge.py:_resolve_symbols`).

### User-visible behavior
- Gravity Lab shows `Backend: kernel` or `Backend: python-fallback` based on initialization success (Anchor: `app_ui/labs/gravity_lab.py:GravityLabWidget._init_backend`).
- If a kernel call fails during simulation, Gravity Lab shows a warning dialog and pauses (Anchor: `app_ui/labs/gravity_lab.py:GravityLabWidget._tick`).
- ModuleManagerScreen disables Run unless the kernel is available (Anchor: `app_ui/main.py:ModuleManagerScreen._show_part`).

### Failure modes and symptoms
- Missing DLL triggers `KernelNotAvailable` and switches Gravity Lab to Python backend (Anchor: `app_ui/kernel_bridge.py:KernelNotAvailable`, `app_ui/labs/gravity_lab.py:GravityLabWidget._init_backend`).
- Kernel status error raises RuntimeError with the kernel message (Anchor: `app_ui/kernel_bridge.py:_fetch_error`, `app_ui/labs/gravity_lab.py:GravityLabWidget._tick`).

### Requires manual UI verification
- Verify the gravity demo run preview in ModuleManagerScreen if you wire it into navigation.

## B) UI packs and theming lifecycle (explained)

### Startup apply flow
1) `main()` calls `apply_ui_config_styles(app)`.
2) `apply_ui_config_styles()` loads config via `ui_config.load_ui_config()`.
3) `ui_system.manager.ensure_config()` ensures config exists.
4) `resolve_pack()` prefers store root, then repo root.
5) QSS is applied via `manager.apply_qss()` and `_ensure_safe_font()` (Anchor: `app_ui/main.py:apply_ui_config_styles`, `ui_system/manager.py`).

### Runtime switching flow (Settings)
- `SettingsDialog._save_settings` updates ui_config and re-applies the theme immediately (Anchor: `app_ui/main.py:SettingsDialog._save_settings`).

### Reduced motion usage
- `get_reduced_motion()` reads ui_config and labs/LabHost use the flag to adjust timers/behavior (Anchor: `app_ui/config.py:get_reduced_motion`, `app_ui/labs/host.py:LabHost`, `app_ui/labs/*_lab.py:set_reduced_motion`).

### Note about supports_reduced_motion
- `supports_reduced_motion` is parsed in `ui_system/manager.py` but not enforced during apply (Anchor: `ui_system/manager.py:_load_manifest`, `app_ui/main.py:apply_ui_config_styles`).

## C) Navigation mental model (explained)

### Home button mapping
- Quick Start -> `MainWindow._start_physics()` -> `MainWindow._find_quick_start_part()` -> `MainWindow.open_part_by_id()`.
- Physics Content -> `MainWindow._open_content_browser()`.
- Module Management -> `MainWindow._open_module_management()`.
- Content Management -> `MainWindow._open_content_management()`.
- System Health / Storage -> `MainWindow._open_diagnostics()`.
- Settings -> `MainWindow._open_settings()`.

### Quick Start selection rules
- Selects first READY part with lab_id or part_id ending `_demo` (Anchor: `app_ui/main.py:MainWindow._find_quick_start_part`).

### Back behavior
- Screen Back buttons return to MainMenuScreen.
- Lab Back returns to ContentBrowserScreen.

## D) Asset pipeline and RenderKit resolution (explained)

### Repo vs Store assets and READY status
- READY status requires assets in `content_store/physics_v1` (Anchor: `content_system/loader.py:_compute_part_status`).
- Text assets are resolved by `read_asset_text()` with store-first fallback to repo (Anchor: `app_ui/main.py:read_asset_text`).

### AssetResolver root choice
- `AssetResolver.from_detail()` uses `detail.paths.store_manifest` or defaults to `content_store/physics_v1` (Anchor: `app_ui/labs/renderkit/assets.py:AssetResolver.from_detail`).
- `AssetResolver.resolve()` enforces store-root containment and strips optional leading module folder (Anchor: `app_ui/labs/renderkit/assets.py:AssetResolver.resolve`).

### Caching behavior
- `AssetCache` caches SVG renderers and pixmaps keyed by path/size/tint/DPI bucket (Anchor: `app_ui/labs/renderkit/assets.py:AssetCache`).

### Missing-asset behavior
- `read_asset_text()` returns None if asset missing; Content Browser shows a warning (Anchor: `app_ui/main.py:ContentBrowserScreen._open_selected`).
- RenderKit sprite helpers return False when missing; arrow sprite has a line fallback if invoked (Anchor: `app_ui/labs/renderkit/primitives.py:draw_arrow_sprite`).
- Current lab code does not call RenderKit sprite helpers; labs use shared primitives (Anchor: `app_ui/labs/electric_field_lab.py`, `app_ui/labs/lens_ray_lab.py`, `app_ui/labs/vector_add_lab.py`).

# Fact Sheet Addendum (Ground Truth Only)

## A) Kernel bridge and fallbacks (FACTS ONLY)

Key files:
- `app_ui/kernel_bridge.py`: `DLL_CANDIDATES`, `_load_library`, `_resolve_symbols`, `_get_lib`, `_fetch_error`, `GravityKernelSession`, `create_gravity_session`, `run_gravity_demo`, `KernelNotAvailable`.
- `app_ui/labs/gravity_lab.py`: `KernelGravityBackend`, `PythonGravityBackend`, `GravityLabWidget._init_backend`, `GravityLabWidget._tick`.
- `app_ui/main.py`: `ModuleManagerScreen._show_part`, `ModuleManagerScreen._run_selected_part` (note: ModuleManagerScreen is not routed).

Load sequence:
1) `create_gravity_session()` -> `GravityKernelSession.__init__()` -> `_get_lib()` -> `_resolve_symbols()` -> `_load_library()`.
2) `_load_library()` checks DLL candidates in order (see `DLL_CANDIDATES`).
3) `_resolve_symbols()` binds `pl_world_create`, `pl_world_destroy`, `pl_world_step`, `pl_world_get_state`, `pl_last_error_code`, `pl_last_error_message`.

Fallback behavior:
- Missing DLL raises `KernelNotAvailable`; GravityLabWidget falls back to Python backend and prints `Simulation fallback: ...`.
- Kernel errors during stepping show a warning and stop the timer (`GravityLabWidget._tick`).

## B) UI packs and theming lifecycle (FACTS ONLY)

Key files:
- `ui_system/manager.py`: `Pack`, `list_packs`, `resolve_pack`, `load_qss`, `apply_qss`, `ensure_config`, `CONFIG_PATH`.
- `app_ui/main.py`: `apply_ui_config_styles`, `_ensure_safe_font`, `SettingsDialog._save_settings`.
- `app_ui/config.py`: `load_ui_config`, `save_ui_config`, `get_reduced_motion`, `CONFIG_PATH`.

Startup apply path:
- `main()` -> `apply_ui_config_styles()` -> `manager.ensure_config()` -> `resolve_pack()` (store-first) -> `load_qss()` -> `apply_qss()`.

Runtime switching:
- `SettingsDialog._save_settings` updates ui_config and re-applies the theme.

Reduced motion:
- `get_reduced_motion()` reads ui_config; labs/LabHost use the flag.

## C) Navigation mental model (FACTS ONLY)

Home buttons -> targets:
- Quick Start -> `MainWindow._start_physics()` -> `MainWindow._find_quick_start_part()` -> `MainWindow.open_part_by_id()`.
- Physics Content -> `MainWindow._open_content_browser()`.
- Module Management -> `MainWindow._open_module_management()`.
- Content Management -> `MainWindow._open_content_management()`.
- System Health / Storage -> `MainWindow._open_diagnostics()`.
- Settings -> `MainWindow._open_settings()`.

Quick Start behavior:
- Selects first READY part with lab_id or part_id ending `_demo`.

Back behavior:
- Screen Back buttons return to MainMenuScreen.
- Lab Back returns to ContentBrowserScreen.

## D) Asset pipeline and RenderKit resolution (FACTS ONLY)

Where assets originate:
- `content_repo/physics_v1/assets/...` (paths referenced in part manifests).

Runtime asset expectations:
- READY requires store assets at `content_store/physics_v1/<asset_path>`.

Resolution:
- `read_asset_text()` prefers store path then repo path (for text assets).
- `AssetResolver.from_detail()` uses store_manifest parent or default store root.
- `AssetResolver.resolve()` enforces store-root containment.

Caching:
- `AssetCache` caches SVG renderers and pixmaps keyed by path/size/tint/DPI bucket.

# Verification Appendix

Timestamp: 2025-12-22T20:29:20.0948346+03:00
Commit: 77b4895

Commands run:
- `git rev-parse --short HEAD` -> `77b4895`
- `git log --oneline -n 40` -> see terminal output (captured during verification)
- `python -m py_compile app_ui/**/*.py` -> FAILED (`[Errno 22] Invalid argument: 'app_ui/**/*.py'`)
- `python -m py_compile (Get-ChildItem -Recurse -Filter *.py app_ui | ForEach-Object { $_.FullName })` -> OK
- `python -c "import app_ui.main; print('import ok')"` -> `import ok`

Manual run command:
- `python -m app_ui.main`

Auto-verified vs manual:
- Auto: imports + bytecode compilation (see commands above).
- Manual required: UI behavior and rendering (see checklist below).

Manual UI verification checklist:
- Launch the app: `python -m app_ui.main`.
- Open each lab (gravity, projectile, electric_field, lens_ray, vector_add) and confirm it renders and responds.
- Toggle Grid/Axes in LabHost for electric_field, lens_ray, vector_add and confirm persistence (`data/roaming/lab_prefs.json`).
- Content Browser: install a part and open a lab and a markdown part.
- System Health: refresh report, run cleanup, view job history (Explorer profile).
- Module Management + Content Management: module install/uninstall jobs update status and panels.
