# PhysicsLab App Summary (Code-Verified Checkpoint)

## Scope, terminology, and versioning
- UI terminology (see `docs/standard_terms.md`): Project, Pack, Block, Topic/Unit/Lesson/Activity.
- Internal IDs remain: workspace, component pack, component, module/section/package/part.
- Curriculum mapping: Topic = Module, Unit = Section, Lesson = Package, Activity = Part.
- Versioning in commits/docs uses Vx.y (milestone) and Vx.y.z (fix/refactor), not chapter numbers.
- Protected baseline tag: v4.0.0-beta.1 (do not move/remove).
- Current milestone line: V4.15f (Block Catalog + Block Sandbox templates + Block Host session persistence).

## App at a glance (verified features)
- PyQt6 desktop app using a QStackedWidget main window with profile-gated navigation (Anchor: `app_ui/main.py:MainWindow.__init__`, `app_ui/main.py:MainMenuScreen._rebuild_buttons`).
- Quick Start selects the first READY lab part and opens it directly; if none are READY, it routes to Content Management with an install message (Anchor: `app_ui/main.py:MainWindow._start_physics`, `app_ui/main.py:MainWindow._find_quick_start_part`).
- Content Browser opens parts by priority: component_id -> Block runtime, then lab_id -> LabHost, else markdown viewer (Anchor: `app_ui/main.py:ContentBrowserScreen._open_selected`, `app_ui/main.py:MainWindow.open_part_by_id`).
- Registered labs: gravity, projectile, electric_field, lens_ray, vector_add (Anchor: `app_ui/labs/registry.py:list_labs`).
- Block system: Block Catalog, Block Sandbox (templates), and Block Host with per-Project session persistence (Anchor: `app_ui/screens/block_catalog.py`, `app_ui/main.py:ComponentSandboxScreen`, `app_ui/screens/block_host.py`).
- Component runtime supports built-ins, labhost blocks, and pack-defined blocks (builtin:markdown_panel, builtin:lab_preset) (Anchor: `component_runtime/registry.py:register_lab_components`, `component_runtime/registry.py:register_pack_components`).
- Workspaces are first-class Projects; active workspace drives run locations under `data/workspaces/<id>/runs` (Anchor: `core_center/workspace_manager.py:get_active_workspace`, `core_center/storage_manager.py:_runs_root`).
- Core Center (Management Core) is optional; UI imports are guarded and runtime bus endpoints are registered if available (Anchor: `app_ui/main.py:CORE_CENTER_AVAILABLE`, `app_ui/main.py:CORE_CENTER_BUS_ENDPOINTS`).
- Runtime bus is local, in-process pub/sub + request/reply with sticky topics and optional debug logging (Anchor: `runtime_bus/bus.py:RuntimeBus`, `runtime_bus/bus.py:BUS_DEBUG`).

## High-level architecture (modules + boundaries)
- `app_ui/`: UI orchestration, screens, labs, and block screens (entry: `python -m app_ui.main`) (Anchor: `app_ui/main.py:main`).
- `content_system/`: content hierarchy loader + part installer (Anchor: `content_system/loader.py:list_tree`, `content_system/loader.py:download_part`).
- `runtime_bus/`: in-process bus types and topics (Anchor: `runtime_bus/bus.py`, `runtime_bus/messages.py`, `runtime_bus/topics.py`).
- `core_center/`: optional Management Core for discovery/registry/inventory/jobs/storage/policy/workspaces (Anchor: `core_center/bus_endpoints.py:register_core_center_endpoints`).
- `component_runtime/`: component registry, host, packs, builtins (Anchor: `component_runtime/registry.py`, `component_runtime/host.py`).
- `component_repo/component_v1/packs/` + `component_store/component_v1/packs/`: component pack source + installed mirror (Anchor: `component_runtime/packs.py:REPO_ROOT`, `component_runtime/packs.py:STORE_ROOT`).
- `content_repo/physics_v1/` + `content_store/physics_v1/`: content pack source + installed mirror (Anchor: `content_system/loader.py:REPO_BASE`, `content_system/loader.py:STORE_BASE`).
- `ui_system/` + `ui_repo/` + `ui_store/`: UI pack manager and QSS packs (Anchor: `ui_system/manager.py:list_packs`).
- `workspace_repo/templates/`: workspace template seeds (Anchor: `core_center/workspace_manager.py:TEMPLATES_ROOT`).
- `app_ui/templates/block_sandbox/`: Block Sandbox templates (Anchor: `app_ui/main.py:ComponentSandboxScreen._load_templates`).
- `kernel/`: Rust DLL for gravity kernel, bridged in Python (Anchor: `app_ui/kernel_bridge.py`).

## Startup + navigation rules (verified)
- Entry: `app_ui/main.py:main` creates QApplication, applies UI pack, constructs MainWindow, and starts the event loop (Anchor: `app_ui/main.py:main`, `app_ui/main.py:apply_ui_config_styles`).
- Quick Start uses ContentSystemAdapter.list_tree() to find the first READY lab part (lab_id or _demo) and opens it directly (Anchor: `app_ui/main.py:MainWindow._find_quick_start_part`).
- Physics Content always opens ContentBrowserScreen (Anchor: `app_ui/main.py:MainWindow._open_content_browser`).
- Block Catalog opens the Block Catalog screen; Block Sandbox opens the Block Sandbox screen (Anchor: `app_ui/main.py:MainWindow._open_block_catalog`, `app_ui/main.py:ComponentSandboxScreen`).
- Back buttons return to the main menu; Lab Back returns to Content Browser; Esc triggers a back action when not in a lab, modal dialog, or text input (Anchor: `app_ui/main.py:MainWindow._handle_escape_back`).

## Projects, Packs, Blocks (terminology mapping)
- Project = workspace. Active Project resolves workspace paths (runs, prefs, cache, store) and is stored in `data/roaming/workspace.json` (Anchor: `core_center/workspace_manager.py:_active_path`).
- Pack = component pack installed into `component_store/component_v1/packs/` from `component_repo/component_v1/packs/` (Anchor: `component_runtime/packs.py`).
- Block = runtime component (built-in, labhost:<lab_id>, or pack-defined). Block IDs are component_id values (Anchor: `component_runtime/types.py`).
- WorkspaceComponentPolicy gates Pack/Block availability per Project; labhost blocks are always enabled (Anchor: `app_ui/ui_helpers/component_policy.py`).

## Block Catalog (Block discovery + launch)
- Collects pack manifests from the repo and installed packs from the store; shows a Pack list and a block list grouped by category (Anchor: `app_ui/screens/block_catalog.py:_collect_entries`, `app_ui/screens/block_catalog.py:_build_block_list`).
- Status rules: Enabled, Disabled by project, Not installed, Unavailable based on install state, policy, and registry presence (Anchor: `app_ui/screens/block_catalog.py:_collect_entries`).
- Built-in blocks (including labhost blocks) appear under the Built-in pack group (Anchor: `app_ui/screens/block_catalog.py:_collect_entries`).
- Action button opens the Block in the Block Host session or returns a selected block to the picker (Anchor: `app_ui/screens/block_catalog.py:_handle_open_action`).
- Optional Docs button opens a pack-provided docs asset path (Anchor: `app_ui/screens/block_catalog.py:_resolve_docs_path`, `app_ui/screens/block_catalog.py:_open_docs`).

## Block Sandbox (templates + manual selection)
- Block Sandbox is the ComponentSandboxScreen, offering Start Empty or Start from Template (Anchor: `app_ui/main.py:ComponentSandboxScreen`).
- Templates are JSON files in `app_ui/templates/block_sandbox/*.json` with `id`, `title`, `description`, `recommended_blocks`, and optional `open_first` (Anchor: `app_ui/main.py:ComponentSandboxScreen._load_templates`).
- Advanced section lists: registered blocks, labhost blocks, and pack blocks; double-click opens the selection in the Block Host (Anchor: `app_ui/main.py:ComponentSandboxScreen.refresh_components`).
- Status checks respect pack install + workspace policy before allowing open (Anchor: `app_ui/main.py:ComponentSandboxScreen._component_status`).

## Block Host (session + persistence)
- Block Host uses ComponentHost to mount component widgets and show errors without crashing the app (Anchor: `app_ui/screens/block_host.py`, `component_runtime/host.py`).
- Session state is persisted per Project in `block_host_session.json` under the workspace prefs root (Anchor: `app_ui/screens/block_host.py:_session_path`, `app_ui/screens/block_host.py:_save_session`).
- Session file includes `open_blocks`, `active_block`, `last_updated`, and a `version` number (Anchor: `app_ui/screens/block_host.py:_save_session`).
- On Project switch, Block Host refreshes registry metadata, reloads the session, and skips missing/disabled blocks with a banner (Anchor: `app_ui/screens/block_host.py:on_workspace_changed`, `app_ui/screens/block_host.py:_load_session`).
- Actions: add block, close active/others/all, activate selection; open picker uses Block Catalog in a dialog (Anchor: `app_ui/screens/block_host.py:add_block`, `app_ui/screens/block_host.py:_open_picker`).

## Component runtime and pack policy
- ComponentRegistry holds component factories; labhost blocks are registered from the lab registry (Anchor: `component_runtime/registry.py:ComponentRegistry`, `component_runtime/registry.py:register_lab_components`).
- Pack components are limited to builtin implementations: `builtin:markdown_panel` and `builtin:lab_preset` (Anchor: `component_runtime/registry.py:register_pack_components`).
- Workspace config `enabled_component_packs` controls Pack enablement; default is all available packs (Anchor: `app_ui/screens/workspace_management.py:_resolve_workspace_enabled_packs_from_config`).
- Available/installed Pack truth is derived from component_store manifests and core inventory when available (Anchor: `app_ui/main.py:MainWindow._reload_workspace_components`, `app_ui/screens/workspace_management.py:_request_inventory_snapshot`).

## Management Core (optional behavior)
- Core Center endpoints serve discovery, inventory, jobs, runs, workspaces, policy, and cleanup (Anchor: `core_center/bus_endpoints.py:register_core_center_endpoints`).
- UI requests policy and inventory over the runtime bus; falls back to defaults when bus is unavailable (Anchor: `app_ui/main.py:_build_component_context`, `app_ui/screens/workspace_management.py:_request_inventory_snapshot`).

## Workspace/project data layout (runtime state + content)
- UI config: `data/roaming/ui_config.json` (Anchor: `app_ui/config.py:CONFIG_PATH`).
- Experience profile: `data/roaming/experience_profile.json` (Anchor: `app_ui/config.py:PROFILE_PATH`).
- Policy overrides: `data/roaming/policy.json` (Anchor: `core_center/policy_manager.py:_policy_path`).
- Registry + jobs: `data/roaming/registry.json`, `data/roaming/jobs.json` (Anchor: `core_center/registry.py`, `core_center/job_manager.py:JOB_HISTORY_PATH`).
- Active Project selector: `data/roaming/workspace.json` (Anchor: `core_center/workspace_manager.py:_active_path`).
- Workspace roots: `data/workspaces/<id>/{runs,runs_local,cache,store,prefs}` (Anchor: `core_center/workspace_manager.py:_ensure_workspace_dirs`).
- Workspace prefs (Project-scoped): `data/workspaces/<id>/prefs/{workspace_config.json,lab_prefs.json,policy_overrides.json,pins.json,block_host_session.json}` (Anchor: `core_center/workspace_manager.py:TEMPLATE_SEED_FILES`, `app_ui/screens/block_host.py:_session_path`).
- Runs: `data/workspaces/<id>/runs/<lab>/<run>/run.json` (Anchor: `core_center/storage_manager.py:allocate_run_dir`).
- Local fallback runs: `data/workspaces/<id>/runs_local/<lab>/<run>/run.json` (Anchor: `app_ui/labs/host.py:_create_local_run_dir`).
- Content repo/store: `content_repo/physics_v1`, `content_store/physics_v1` (Anchor: `content_system/loader.py:REPO_BASE`, `content_system/loader.py:STORE_BASE`).
- UI packs: `ui_repo/ui_v1`, `ui_store/ui_v1` (Anchor: `ui_system/manager.py:list_packs`).
- Component packs: `component_repo/component_v1/packs`, `component_store/component_v1/packs` (Anchor: `component_runtime/packs.py:REPO_ROOT`, `component_runtime/packs.py:STORE_ROOT`).

## Known limitations / TODOs (verified)
- ModuleManagerScreen exists but is not routed in the main navigation (Anchor: `app_ui/main.py:ModuleManagerScreen`, `app_ui/main.py:MainWindow.__init__`).
- Content loader is hard-wired to physics_v1 roots and does not validate JSON against schemas (Anchor: `content_system/loader.py:REPO_BASE`, `content_system/loader.py:_load_json`).
- `schemas/part_manifest.schema.json` contains duplicate `allOf` keys (Anchor: `schemas/part_manifest.schema.json`).
- `core_center/storage_report.py` has unreachable code after a return in report_text (Anchor: `core_center/storage_report.py:report_text`).
- Workspace templates seed prefs into workspaces, but policy + lab prefs still read from data/roaming (Anchor: `core_center/workspace_manager.py:_apply_template`, `core_center/policy_manager.py:_policy_path`, `app_ui/labs/prefs_store.py:PREFS_PATH`).
- Lab prefs are global (not workspace-scoped) (Anchor: `app_ui/labs/prefs_store.py:PREFS_PATH`).
- Component packs support only builtin implementations; no arbitrary code loading (Anchor: `component_runtime/registry.py:register_pack_components`).

## Verification Appendix
Timestamp: 2025-12-27T09:42:38.213677+00:00
Commit: 6c8ecc8

Commands run:
- `git rev-parse --short HEAD` -> `6c8ecc8`
- `git log --oneline -n 10`
- `python -m compileall app_ui content_system core_center component_runtime runtime_bus ui_system schemas diagnostics` -> OK

Manual UI verification checklist:
- Launch app: `python -m app_ui.main`.
- Home: open Block Catalog, confirm Pack list + Block details + Docs button behavior.
- Block Sandbox: Start Empty and Start from Template; confirm template list from `app_ui/templates/block_sandbox/`.
- Block Host: add blocks, close active/others/all, switch active block, quit and relaunch to confirm session restore.
- Content Browser: open a READY lab part and a markdown part.
- Labs: gravity, projectile, electric_field, lens_ray, vector_add rendering and interactions.
- System Health: Overview/Runs/Maintenance/Modules/Jobs tabs; run delete/prune.
- Workspace Management: list/create/switch/delete Projects, template list loads, pack toggles persist.
