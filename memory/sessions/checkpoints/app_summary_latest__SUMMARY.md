# App Summary Checkpoint (Summary)

> Snapshot generated during slice d9 from working tree based on HEAD 55fbe3f80f21b0722c1d7ab46aa5ee467f8cb766.

- Dossier source: `memory/sessions/checkpoints/app_summary_latest__DOSSIER.md`
- Verify baseline commit quickly: `git rev-parse --short HEAD`

## Top truths (with verification anchors)
1. App entrypoint is `python -m app_ui.main` and MainWindow bootstraps navigation.
- Verify: `rg -n "def main\(|class MainWindow" app_ui/main.py`

2. Quick Start opens first READY lab part, otherwise routes to content management fallback.
- Verify: `rg -n "_start_physics|_find_quick_start_part" app_ui/main.py`

3. Content open path priority is component runtime then labhost then markdown.
- Verify: `rg -n "open_part_by_id|_open_selected" app_ui/main.py`

4. Runtime bus is in-process pub/sub plus request/reply.
- Verify: `rg -n "class RuntimeBus" runtime_bus/bus.py`

5. Core Center is optional and UI paths are guarded when absent.
- Verify: `rg -n "CORE_CENTER_AVAILABLE|register_core_center_endpoints" app_ui/main.py core_center/bus_endpoints.py`

6. Workspace project roots live under `data/workspaces/<id>/...`.
- Verify: `rg -n "_ensure_workspace_dirs|runs_root|workspace" core_center/workspace_manager.py core_center/storage_manager.py`

7. Block Host persists per-project session state.
- Verify: `rg -n "block_host_session|_save_session|_load_session" app_ui/screens/block_host.py`

8. Current known limitations are tracked in the app summary dossier appendix.
- Verify: open `memory/sessions/checkpoints/app_summary_latest__DOSSIER.md`
