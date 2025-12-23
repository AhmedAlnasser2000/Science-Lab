# PhysicsLab App Summary

## App at a glance (user features)
- PyQt6 desktop app with a Home menu, content browsing (Module → Section → Package → Part), and lab demos (gravity, projectile, electric field, lens ray, vector add).
- Quick Start launches the first READY lab directly; Physics Content opens the full browser.
- Labs render interactive visuals and accept profile + reduced‑motion settings; guides are shown in a left panel.
- System Health (Educator/Explorer) shows storage report and cleanup; Explorer adds module install/uninstall and job history.
- Optional Core Center adds registry, storage reporting, cleanup jobs, module install/uninstall, policy, run directories, and job history.

## High-level architecture (modules + boundaries)
- `app_ui/` — UI + navigation + labs (entry: `python -m app_ui.main`).
- `content_system/` — reads repo manifests, computes READY/NOT_INSTALLED, installs parts into store.
- `runtime_bus/` — in‑process pub/sub + request/reply with sticky topics and debug logging.
- `core_center/` — optional management: discovery/registry, storage report, cleanup, jobs, policy, run storage.
- `content_repo/physics_v1/` — canonical content pack (manifests + assets).
- `content_store/physics_v1/` — installed content/asset copies for READY status.
- `ui_system/` + `ui_repo/` + `ui_store/` — UI pack manager + QSS packs.
- `schemas/` — JSON Schemas for content manifests + runtime state (policy/registry).
- `kernel/` — Rust DLL for gravity kernel.

## Startup + navigation flow
- Entry: `app_ui/main.py` `main()`.
- App boot: creates `QApplication`, applies UI pack, constructs `MainWindow`, shows.
- `MainWindow` wires screens into a `QStackedWidget` and routes navigation callbacks.
- Quick Start (`_start_physics`) finds the first READY lab part and opens it directly; if none, routes to Content Management with install guidance.
- Physics Content always opens the Content Browser.

## Screens and what each one does
- **MainMenuScreen** — Home buttons (Quick Start, Physics Content, Module Management, Content Management, System Health, Settings, Quit) gated by profile.
- **ModuleManagerScreen** — simple tree with part status + preview + “Download/Run” for gravity demo via kernel bridge.
- **ContentBrowserScreen** — browse tree, view status/preview, install parts, open labs or markdown.
- **SettingsDialog** — choose UI pack, reduced motion, experience profile; applies pack immediately.
- **SystemHealthScreen** — storage report (bus or direct), cleanup (cache/dumps), module install/uninstall (Explorer), job history panel (Explorer), and panels for progress/completion.
- **ModuleManagementScreen** — table view for module install/uninstall via bus (uses registry).
- **ContentManagementScreen** — manager view: filterable tree, status pill, module actions, and double‑click to open content.

## Content system (install + browse + status model)
- `content_system/loader.py` builds the hierarchy and statuses from `content_repo/physics_v1` and `content_store/physics_v1`.
- Status model: `READY`, `NOT_INSTALLED`, `UNAVAILABLE`.
- `list_tree()` reads module → section → package → part manifests, computes status by verifying store manifest + referenced assets.
- `download_part(part_id)` copies the part directory and referenced assets repo → store.
- Lab metadata comes from `x_extensions.lab` in part manifests and is surfaced as `part["lab"]`.

## Labs system (plugin contract + LabHost + run context)
- Contract in `app_ui/labs/base.py`: `LabPlugin.create_widget(on_exit, get_profile)` with optional `get_export_actions` and `get_telemetry_snapshot`.
- Registry in `app_ui/labs/registry.py` (gravity, projectile, electric_field, lens_ray, vector_add).
- `LabHost` (`app_ui/labs/host.py`):
  - Wraps lab widget with guide panel + export button.
  - Requests policy via `core.policy.get.request`; falls back to defaults.
  - Requests run directory via `core.storage.allocate_run_dir.request`; else uses `data/store/runs_local`.
  - Emits telemetry (`lab.telemetry`) if policy allows and profile is Explorer.
  - Applies reduced motion and run context to labs if supported.
- Visual rendering for new labs uses `app_ui/labs/renderkit/` (RenderCanvas + primitives + SVGs).

## Runtime bus (topics + flows)
- `runtime_bus/bus.py`: in‑process pub/sub, request/reply, sticky topics, optional debug logging via `PHYSICSLAB_BUS_DEBUG=1`.
- Envelope type in `runtime_bus/messages.py`.
- Topics in `runtime_bus/topics.py` (core storage/cleanup/policy/registry, job lifecycle, content install, telemetry, runtime diagnostics).
- Request/Reply: `register_handler()` + `request()` with timeout; returns `{"ok": False, "error": ...}` on failures.

## Core Center (discovery/registry/jobs/storage/policy)
- Discovery: `core_center/discovery.py` scans `content_repo/`, `content_store/`, `ui_repo/`, `ui_store/`, and app labs registry.
- Registry: `core_center/registry.py` stores unified list at `data/roaming/registry.json`.
- Jobs: `core_center/job_manager.py` runs background threads, emits `job.*` + `content.install.*` + `core.storage.report.ready` + cleanup events, and persists job history to `data/roaming/jobs.json`.
- Storage reporting: `core_center/storage_report.py` aggregates data roots + runs + components (used by System Health).
- Policy: `core_center/policy_manager.py` loads defaults + overrides from `data/roaming/policy.json`.
- Run dirs: `core_center/storage_manager.py` allocates `data/store/runs/<lab>/<run>/run.json`, enforces retention.
- Endpoints: `core_center/bus_endpoints.py` registers handlers for storage report, cleanup, policy, registry, run dir allocation, module install/uninstall, jobs list/get.

## Data layout (what goes where)
- `data/roaming/ui_config.json` — UI pack + reduced motion.
- `data/roaming/experience_profile.json` — active profile.
- `data/roaming/policy.json` — optional policy overrides.
- `data/roaming/registry.json` — discovered modules/ui packs/labs.
- `data/roaming/jobs.json` — job history.
- `data/store/runs/<lab>/<run>/run.json` — Core Center run metadata.
- `data/store/runs_local/<lab>/<run>/run.json` — fallback run storage if Core Center/bus unavailable.
- `content_repo/physics_v1/` — canonical manifests/assets (including `assets/lab_viz/` SVGs).
- `content_store/physics_v1/` — installed assets + part manifests (READY status).

## Extension recipes (add lab/content/ui pack/core endpoint)
- **Add a lab**
  1) Create `app_ui/labs/<your_lab>.py` implementing `LabPlugin` + widget methods.
  2) Register plugin in `app_ui/labs/registry.py`.
  3) Add content part manifest with `x_extensions.lab.lab_id` and guide assets.
  4) Add assets in `content_repo/physics_v1/assets/` and copy to `content_store/physics_v1/assets/` (or install module).
- **Add content part/page**
  1) Update `module_manifest.json` → `section_manifest.json` → `package_manifest.json`.
  2) Add `parts/<part_id>/part_manifest.json` and any assets.
  3) Copy to `content_store` (or use `content_system.download_part` / Core Center module install).
- **Add UI pack**
  1) Create `ui_repo/ui_v1/packs/<id>/ui_pack_manifest.json` + `.qss` files.
  2) Set `data/roaming/ui_config.json` `active_pack_id` to your pack.
  3) Run app to auto‑apply or call `ui_system.manager` directly.
- **Add Core Center endpoint**
  1) Add topic constant in `runtime_bus/topics.py`.
  2) Register handler in `core_center/bus_endpoints.py`.
  3) Call via `bus.request(...)` in UI (typically `app_ui/main.py` screens).

## Current limitations / TODOs found in code
- `schemas/part_manifest.schema.json` has duplicate `allOf` keys; earlier `allOf` is overwritten.
- `core_center/storage_report.py` has unreachable code after a `return` (registry summary block never runs).
- `content_system/loader.py` is hard‑wired to `physics_v1` and does not validate against schemas.
- README/UI docs show some outdated lab list references.
- Some strings show mojibake in code/doc text (e.g., `Aų`, `ƒ?`).
- `app_ui/labs/_viz_canvas.py` exists but is currently unused (renderkit is used instead).
- `content_store/physics_v1/assets/lab_viz/` is missing; arrow sprites fall back to line drawing, while other sprites (lens/charge) are skipped unless assets are installed.

## What to read next (file pointers)
- Entry + routing: `app_ui/main.py`
- Labs contract + host: `app_ui/labs/base.py`, `app_ui/labs/host.py`
- Lab visuals: `app_ui/labs/renderkit/canvas.py`, `app_ui/labs/renderkit/primitives.py`
- Content loader: `content_system/loader.py`
- Bus core: `runtime_bus/bus.py`, `runtime_bus/topics.py`
- Core Center endpoints/jobs: `core_center/bus_endpoints.py`, `core_center/job_manager.py`
- Core storage/policy: `core_center/storage_manager.py`, `core_center/storage_report.py`, `core_center/policy_manager.py`
- Content pack manifests: `content_repo/physics_v1/module_manifest.json`, `content_repo/physics_v1/sections/**/package_manifest.json`
- UI packs: `ui_system/manager.py`, `ui_repo/ui_v1/packs/*/ui_pack_manifest.json`

# Detailed Addendum (Checkpoint-ready)
## A) Kernel bridge & fallbacks (explained)

### What it does (1–2 paragraphs)
The Kernel Bridge (`app_ui/kernel_bridge.py`) is a Python module that acts as a compatibility layer between the PyQt UI and a physics simulation kernel written in Rust (`physicslab_kernel.dll`). Its primary responsibility is to load the shared library (DLL), resolve the C-style function symbols within it, and expose them to the application through a Python-native interface, `GravityKernelSession`. This session object handles the lifecycle of the simulation world, including creation, destruction, and stepping through the simulation state.

If the Rust kernel cannot be loaded for any reason, the system is designed to gracefully degrade. The Gravity Lab has an internal fallback, `PythonGravityBackend`, which provides a pure-Python implementation of the simulation. This ensures the application remains functional, albeit at a lower performance level, and provides clear visual feedback to the user about the current backend status. The Module Manager also uses the bridge to safely gate access to kernel-dependent features.

### Exact load sequence (bulleted steps, same order as fact sheet)
- The process begins with a call to `create_gravity_session()`.
- This instantiates `GravityKernelSession`, which immediately calls `_get_lib()` to find and load the kernel.
- `_get_lib()` triggers `_resolve_symbols()`, which in turn calls `_load_library()`.
- `_load_library()` attempts to find and load a DLL from a list of candidate paths, in order:
    1. `kernel/target/release/physicslab_kernel.dll`
    2. `app_ui/native/physicslab_kernel.dll`
- If a DLL is successfully loaded, `_resolve_symbols()` proceeds to bind the required C functions using `ctypes`: `pl_world_create`, `pl_world_destroy`, `pl_world_step`, `pl_world_get_state`, `pl_last_error_code`, `pl_last_error_message`.
- The Gravity Lab then wraps this functionality in its `KernelGravityBackend`.

### What users see in:
- **Module Manager (Run disabled / message box)**: If the kernel is unavailable, the "Run" button for the gravity demo is disabled. If a user somehow manages to click it, the application shows a "Kernel Error" or "Kernel Missing" message box instead of crashing.
- **Gravity lab (python-fallback label)**: When the lab fails to initialize the Rust kernel backend, it seamlessly switches to the `PythonGravityBackend`. A message is printed to the console (`Simulation fallback: ...`), and the lab UI displays a label indicating the active backend is `"python-fallback"`.

### Failure modes & symptoms
- **Kernel DLL Not Found**: The most common failure is `KernelNotAvailable`, which is raised if `_load_library` cannot find the DLL at any of its candidate locations. This triggers the fallback behavior described above.
- **Kernel Function Error**: If the DLL is loaded but an internal kernel function returns an error (e.g., a non-zero status code or a null handle), the `kernel_bridge` catches this, fetches the specific error message from the kernel, and raises a generic `RuntimeError`. The Gravity Lab catches this error during its `_tick` cycle and displays a "Simulation error: ..." message in the UI.

### Troubleshooting checklist (5–8 bullets)
- Verify that `kernel/target/release/physicslab_kernel.dll` exists. If not, build the Rust kernel (`cargo build --release` in the `kernel` directory).
- Check the console output for a `Simulation fallback: ...` message, which confirms the Python backend is in use and provides the original exception.
- Confirm the "Run" button in the Module Manager is enabled. If disabled, it's a clear sign the kernel is not being detected on startup.
- Look for `RuntimeError` messages in the console, which indicate the kernel loaded but failed during execution.
- Ensure the Rust kernel project compiles without errors and that all required functions are exported correctly.
- Check permissions for the directory containing the DLL to ensure the application can read and execute it.
 

### UNKNOWN (if any)
- There is no known kernel usage outside of the gravity lab and the Module Manager's run preview.

## B) UI packs & theming lifecycle (explained)

### Startup apply flow
The application applies a UI theme at startup before the main window is shown.
1. The main entry point (`app_ui.main.main()`) calls `apply_ui_config_styles()`.
2. This function loads the UI configuration from `data/roaming/ui_config.json`.
3. It then calls `ui_system.manager.ensure_config()` to resolve the active UI pack, searching first in the `ui_store/ui_v1` directory (for installed packs) and falling back to `ui_repo/ui_v1`.
4. If a valid pack is found, its QSS (Qt Style Sheets) content is loaded via `manager.load_qss` and applied to the global `QApplication` instance. A safe font is also ensured.
5. If the specified pack is not found, a message is printed to the console, and the application may proceed with a default or no theme.

### Runtime switching flow (Settings)
Users can change the active UI theme at runtime through the Settings dialog.
1. The dialog is populated with a list of available packs discovered by `ui_system.manager.list_packs`.
2. When the user makes a selection and saves, `SettingsDialog._save_settings` is called.
3. This function updates `data/roaming/ui_config.json` with the new `active_pack_id` and other settings like `reduced_motion`.
4. It immediately calls `apply_ui_config_styles(app)` again to apply the newly selected theme to the running application.

### How reduced_motion is used (labs/LabHost)
The `reduced_motion` setting is a global flag that helps create a more accessible experience by disabling or reducing animations.
- The value of this boolean flag is stored in `data/roaming/ui_config.json` and read by `app_ui/config.py:get_reduced_motion()`.
- Various lab widgets and the `LabHost` container read this setting to conditionally adjust timers, disable animations, or alter other motion-related behaviors.

### Note about supports_reduced_motion not enforced
The UI pack manifest includes a field named `supports_reduced_motion`. While the `ui_system` parses this field, there is no logic in the theme application path that checks or enforces it. The `reduced_motion` setting is handled independently by the lab widgets themselves, not by the QSS stylings.

### Troubleshooting checklist
- Check the contents of `data/roaming/ui_config.json` to see which `active_pack_id` is set.
- Verify that the corresponding theme pack folder exists in either `ui_store/ui_v1/packs/` (preferred) or `ui_repo/ui_v1/packs/`.
- Look for console messages at startup that might indicate a pack failed to load.
- Ensure the pack's `.qss` file is correctly formatted and contains valid Qt Style Sheet syntax.
- If styles are not applying correctly, check for syntax errors or invalid selectors in the QSS file.
- If runtime switching fails, confirm the Settings dialog has the correct permissions to write to `ui_config.json`.

### UNKNOWN
- There is no explicit logic that checks the `Pack.supports_reduced_motion` flag when applying a theme's QSS.

## C) Navigation mental model (explained)

### Home button → intent mapping:
The main menu provides several navigation options, each with a distinct purpose:
- **Quick Start**: Attempts to find the first available, ready-to-run lab demo and launches it directly, bypassing the content browser for immediate engagement. If no labs are ready, it redirects the user to the Content Management screen.
- **Physics Content**: Always opens the `ContentBrowserScreen`, allowing users to explore the full hierarchy of available modules, sections, and content parts.
- **Module Management**: Opens the `ModuleManagementScreen`, which provides a high-level view for installing or uninstalling entire content modules.
- **Content Management**: Opens the `ContentManagementScreen`, a more detailed manager view for browsing content, viewing status, and triggering actions.
- **System Health**: Opens the `SystemHealthScreen` for diagnostics, storage reports, and cleanup tasks.

### Quick Start selection rules (what qualifies as the “first READY lab part”)
The "Quick Start" logic is defined in `_find_quick_start_part()`. It scans the content tree for the very first item that meets the following criteria:
- The content part must have a status of `READY`.
- The part's metadata must indicate it is a lab. This is determined by checking for a `lab_id` in its manifest (`part["lab"]["lab_id"]`) or if the `part_id` string ends with `_demo`.

### Back behavior expectations (especially Lab Back → Content Browser)
The "Back" button behavior is consistent and context-aware, but it's important to note it does not always return to the previous screen in a linear history.
- From any top-level screen opened from the main menu (Content Browser, System Health, etc.), the "Back" button returns the user to the `MainMenuScreen`.
- From within a lab screen, the "Back" button (which triggers the `on_exit` callback) is specifically wired to take the user back to the `ContentBrowserScreen`. This allows them to easily select another piece of content within the same context, rather than being sent all the way back to the home screen.

### UNKNOWN
- The application does not persist or remember the "last opened part" between sessions. Quick Start will always find the first available lab based on the default tree order.

## D) Asset pipeline & RenderKit resolution (explained)

### Repo vs Store assets: what “READY” implies
Assets originate in the `content_repo`, which serves as the canonical source of truth. However, for a content part to be considered `READY` for use, all of its associated assets (guides, images, SVGs) must be successfully copied into the `content_store`. The runtime, particularly the RenderKit for labs, operates exclusively on the assumption that assets exist in the `content_store`.

### How AssetResolver chooses base root
The `AssetResolver` is responsible for locating assets on disk for the RenderKit. It determines the correct root directory to search from using the following logic:
1. It first checks if a `store_manifest` path is available in the content part's details. If so, it uses that manifest's parent directory as the base root.
2. If that is not available, it falls back to a hardcoded default: `content_store/physics_v1`.

When resolving a relative path, it may also strip a leading module folder (e.g., `physics_v1/`) to correctly locate the asset within the determined root. Crucially, it validates that the final resolved path is a child of the content store root; it will not load assets from other locations.

### Caching behavior (what’s cached + why)
To optimize performance and reduce redundant file I/O and processing, the RenderKit uses an `AssetCache`. This in-memory cache stores computationally expensive results. Specifically, it caches:
- **SVG Renderers**: Parsed and prepared SVG rendering objects.
- **Pixmaps**: Rendered bitmap images (pixmaps) generated from SVGs.
The cache key is a composite of the asset's file path, target size (width/height), tint color, and the screen's DPI bucket. This ensures that differently styled or sized versions of the same SVG are cached separately, preventing incorrect rendering.

### Missing-asset behavior (what still draws vs silently missing sprites)
The system has varying behaviors when an asset is missing:
- **Text Assets**: If `read_asset_text()` fails to find a guide or other text file, it returns `None`. The UI catches this and typically displays a message like "Asset file not found" or "Asset not available yet."
- **Arrow Sprites**: The `draw_arrow_sprite()` primitive has a built-in fallback. If it fails to load and draw the corresponding SVG sprite from disk, it will proceed to draw a simple, procedurally generated line with an arrowhead. The object is still visible, just in a lower-fidelity form.
- **Other Sprites (Lens, Charge)**: Most other sprite-drawing functions (e.g., for lenses or electric charges) do not have an explicit drawing fallback. If the `draw_svg_sprite()` call returns `False` (indicating a missing or invalid asset), the function simply does nothing. The sprite will be silently missing from the scene without causing a crash or displaying an error.

### Troubleshooting checklist
- To debug a `READY` part with missing assets, first verify that all its assets listed in the manifest exist within the `content_store/physics_v1/` directory.
- If an asset is missing in a lab, check the console for any error messages. Note that RenderKit may fail silently.
- For a missing SVG sprite, confirm the file exists at the expected path inside `content_store`.
- If an arrow sprite appears as a basic line-and-head, it's a definitive sign its SVG asset is missing or failed to load.
- If a lens or charge sprite is missing, it is highly likely its SVG asset is unavailable, as there is no visual fallback.
- Confirm the asset paths referenced in `part_manifest.json` are correct relative to the content root.

### UNKNOWN
- The RenderKit's `AssetResolver` does not resolve assets from `content_repo` directly; it is strictly limited to the `content_store`.
- There is no explicit logging within the RenderKit itself when an asset lookup fails; it just returns `False`.

# Fact Sheet Addendum (Ground Truth Only)

## A) Kernel bridge & fallbacks (FACTS ONLY)

Key files:
- `app_ui/kernel_bridge.py`: `DLL_CANDIDATES`, `_load_library`, `_resolve_symbols`, `_get_lib`, `_fetch_error`, `GravityKernelSession`, `create_gravity_session`, `run_gravity_demo`, `KernelNotAvailable`
- `app_ui/labs/gravity_lab.py`: `KernelGravityBackend`, `PythonGravityBackend`, `GravityLabWidget._init_backend`, `GravityLabWidget._tick`
- `app_ui/main.py`: `ModuleManagerScreen._show_part`, `ModuleManagerScreen._run_selected_part`

Load sequence (step-by-step):
1) `create_gravity_session()` -> `GravityKernelSession.__init__()` -> `_get_lib()` -> `_resolve_symbols()` -> `_load_library()` in `app_ui/kernel_bridge.py`.
2) `_load_library()` checks DLL candidates in order:
   - `kernel/target/release/physicslab_kernel.dll`
   - `app_ui/native/physicslab_kernel.dll`
3) If a DLL is found, ctypes symbols are bound in `_resolve_symbols()` for `pl_world_create`, `pl_world_destroy`, `pl_world_step`, `pl_world_get_state`, `pl_last_error_code`, `pl_last_error_message`.
4) Gravity lab uses `KernelGravityBackend` to wrap `GravityKernelSession` (`app_ui/labs/gravity_lab.py`).

Fallback behavior:
- If DLL is missing, `_load_library()` raises `KernelNotAvailable("Kernel DLL not found. Build the Rust kernel then try again.")`.
- In `GravityLabWidget._init_backend`, exceptions when creating the kernel backend fall back to `PythonGravityBackend` and set `backend_name = "python-fallback"`; message printed: `Simulation fallback: <exc>`.
- In `ModuleManagerScreen`, the Run button is disabled unless `kernel_bridge.ensure_kernel_available()` succeeds. If kernel is missing, clicking Run shows a warning (Kernel Error / Kernel Missing) and does not crash.

Failure modes + user-visible effects:
- `KernelNotAvailable`:
  - Module Manager: Run disabled; if attempted, shows `Kernel Error` or `Kernel Missing` message box (`app_ui/main.py`).
  - Gravity lab: falls back to Python backend with `Backend: python-fallback` label (`app_ui/labs/gravity_lab.py`).
- Kernel function errors (non-zero status or handle == 0):
  - `kernel_bridge` raises `RuntimeError(_fetch_error(...))`.
  - Gravity lab `_tick` catches and shows `Simulation error: ...` (`app_ui/labs/gravity_lab.py`).

Notes / UNKNOWN:
- UNKNOWN: There is no kernel usage outside the gravity lab and Module Manager run preview (based on current grep results).

## B) UI packs & theming lifecycle (FACTS ONLY)

Key files:
- `ui_system/manager.py`: `Pack`, `list_packs`, `resolve_pack`, `load_qss`, `apply_qss`, `ensure_config`, `CONFIG_PATH`
- `app_ui/main.py`: `apply_ui_config_styles`, `_ensure_safe_font`, `SettingsDialog._populate_fields`, `SettingsDialog._save_settings`
- `app_ui/config.py`: `load_ui_config`, `save_ui_config`, `get_reduced_motion`, `CONFIG_PATH`

Startup apply path:
1) `app_ui.main.main()` calls `apply_ui_config_styles(app)` before creating `MainWindow`.
2) `apply_ui_config_styles()` loads config via `ui_config.load_ui_config()` (`data/roaming/ui_config.json`).
3) It calls `ui_system.manager.ensure_config()` and resolves the pack from:
   - repo: `ui_repo/ui_v1`
   - store: `ui_store/ui_v1` (preferred)
4) If pack is found, it loads QSS (`manager.load_qss`) and applies via `manager.apply_qss(app, qss)`, then `_ensure_safe_font`.
5) If no pack is found, it falls back to default pack or disables pack with a console message.

Runtime switching (if any):
- Settings dialog (`SettingsDialog._save_settings`) updates `ui_config.json` (active_pack_id, reduced_motion) and calls `apply_ui_config_styles(app)` to apply immediately.

reduced_motion interactions:
- `app_ui/config.py:get_reduced_motion()` reads `data/roaming/ui_config.json`.
- Reduced motion is used in lab widgets and `LabHost` to adjust timers/behavior (see `app_ui/labs/host.py` and lab widgets).
- UI pack manifest field `supports_reduced_motion` is parsed in `ui_system/manager.py` but not used by the apply path.

Notes / UNKNOWN:
- UNKNOWN: There is no explicit logic that checks `Pack.supports_reduced_motion` when applying QSS.

## C) Navigation mental model (FACTS ONLY)

Home buttons -> actual targets:
- Quick Start -> `MainWindow._start_physics()` -> `MainWindow._find_quick_start_part()` -> `MainWindow.open_part_by_id(part_id)`
  - If READY lab part is found, opens lab directly via `_open_lab`.
  - If no READY lab part, routes to Content Management with status "Install a module to begin."
- Physics Content -> `MainWindow._open_content_browser()` -> shows `ContentBrowserScreen`.
- Module Management -> `MainWindow._open_module_management()` -> shows `ModuleManagementScreen`.
- Content Management -> `MainWindow._open_content_management()` -> shows `ContentManagementScreen`.
- System Health / Storage -> `MainWindow._open_diagnostics()` -> shows `SystemHealthScreen`.
- Settings -> `MainWindow._open_settings()` -> `SettingsDialog`.

Quick Start -> exact behavior:
- `_find_quick_start_part()` scans `ContentSystemAdapter.list_tree()` for the first READY part with `lab_id` (from `part["lab"]["lab_id"]`) or `part_id` ending in `_demo` (`app_ui/main.py`).
- `open_part_by_id()` resolves lab_id using:
  - `detail["lab"]["lab_id"]`
  - `manifest["x_extensions"]["lab"]["lab_id"]`
  - `behavior.preset == "gravity-demo"|"projectile-demo"`
  - `part_id == "gravity_demo"|"projectile_demo"`
- If `lab_id` and status READY -> `_open_lab(...)`, otherwise fallback to Content Browser.

Back behavior notes:
- Content Browser Back button calls `on_back`, which is `MainWindow._show_main_menu()`.
- System Health Back button calls `on_back`, also `MainWindow._show_main_menu()`.
- Module Management Back button calls `on_back` (main menu).
- Content Management Back button calls `on_back` (main menu).
- Lab screens: each lab widget has a Back button that calls `on_exit` passed from `MainWindow._open_lab`, which is `MainWindow._show_content_browser()`.

Notes / UNKNOWN:
- UNKNOWN: No "last opened part" persistence is present in `app_ui/main.py`.

## D) Asset pipeline & RenderKit resolution (FACTS ONLY)

Where assets originate (repo paths):
- `content_repo/physics_v1/assets/...` (e.g., `content_repo/physics_v1/assets/lab_viz/*.svg` from filesystem listing).
- Part manifests reference assets via `content.asset_path` and `x_extensions.guides` (see `content_system/loader.py:_collect_asset_paths`).

Where assets must exist at runtime (store paths):
- Runtime asset resolution for labs uses `content_store/physics_v1` as the root (`app_ui/labs/renderkit/assets.py:DEFAULT_STORE_ROOT`).
- `content_system._compute_part_status` requires assets to exist in `content_store/physics_v1/<asset_path>` for READY status.

How resolution works (resolver inputs, root assumptions):
- `content_system.get_part()` returns `paths.assets[asset] = {"repo": "...", "store": "..."}`.
- `read_asset_text()` in `app_ui/main.py` prefers store path then repo path for text assets.
- RenderKit `AssetResolver.from_detail(detail, fallback)` uses:
  - `detail["paths"]["store_manifest"]` (if present) -> base is that manifest's parent
  - else falls back to `content_store/physics_v1`
- `AssetResolver.resolve(rel_path)`:
  - Accepts absolute paths if they exist
  - Strips leading module folder (`physics_v1/...`) if present
  - Ensures resolved path is under content_store root; returns `None` if not or if missing.

Caching behavior:
- `AssetCache` caches SVG renderers and pixmaps keyed by path + size + tint + DPI bucket (`app_ui/labs/renderkit/assets.py`).

Missing-asset fallback behavior:
- `read_asset_text()` returns `None` if file is missing/unreadable; Content Browser shows "Asset file not found" or "Asset not available yet."
- `primitives.draw_svg_sprite()` returns `False` if asset is missing or invalid.
- `primitives.draw_arrow_sprite()` uses `draw_svg_sprite()` and falls back to drawing a simple line + arrow head if sprite render fails.
- Other sprite calls (e.g., lens or charge sprites) do not add explicit fallback beyond "sprite not drawn" when `draw_svg_sprite()` returns `False`.

Notes / UNKNOWN:
- UNKNOWN: RenderKit does not resolve assets from `content_repo` directly; only store paths are used in `AssetResolver`.
- UNKNOWN: There is no explicit logging in RenderKit when assets are missing (only returns `False`).

## Verification Appendix

Last Verified: 2025-12-19T21:04:28.0439913+03:00

Git Commit: de3aaa0

Commands run:
- `python -c "import app_ui.main; print('import ok')"`
- `python -c "from app_ui.labs import registry; print('labs:', sorted(registry.list_labs().keys()))"`
- `python -m core_center.demo_report`
- `python -m content_system.demo_print_tree`
- `git rev-parse --short HEAD`

Corrections in this pass:
- Updated System Health descriptions to reflect Explorer-only job history and module install/uninstall.
- Clarified RenderKit sprite fallback behavior when `content_store/physics_v1/assets/lab_viz/` is missing.
- Removed subjective wording ("high-performance") and a non-evidenced offline availability claim.
- Removed a speculative crash/ABI troubleshooting bullet.
