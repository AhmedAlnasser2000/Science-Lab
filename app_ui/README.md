# App UI (PyQt6)

PyQt6 front-end for PhysicsLab V3. It renders the Primary Mode hierarchy, hosts lab demos, and surfaces the Diagnostics/System Health console powered by the runtime bus. Core Center integration is optional; the UI remains usable without it.

## Requirements
- Python 3.10+
- [PyQt6](https://pypi.org/project/PyQt6/) (`pip install PyQt6`)
- Rust toolchain (for building `physicslab_kernel.dll`)

## Build + Run
1. Build the Rust kernel DLL (gravity demo):
   ```bash
   cargo build --release --manifest-path kernel/Cargo.toml
   ```
   Output: `kernel/target/release/physicslab_kernel.dll`
2. Launch the UI:
   ```bash
   python -m app_ui.main
   ```

## Experience Profiles & Reduced Motion
- Profiles (`Learner`, `Educator`, `Explorer`) are stored in `data/roaming/experience_profile.json` and applied immediately when changed in Settings.
- Reduced Motion lives in `data/roaming/ui_config.json`; flipping the checkbox updates lab animations and UI hints without restarting.

## System Health / Diagnostics
- Accessible from Main Menu (Educator/Explorer). Learner profile hides it.
- Shows storage report, cache/dump cleanup, and folder shortcuts.
- Explorer-only controls trigger local module install/uninstall (repo → store) via `core.content.module.install.request` / `.uninstall.request` and render live progress/completion in a non-modal panel.
- All actions fall back gracefully when the runtime bus or Core Center is unavailable.

## Labs & LabHost
- `LabHost` wraps every lab widget with:
  - Markdown guide viewer (Learner/Educator/Explorer-specific guides from the content pack).
  - Run-directory allocation via `core.storage.allocate_run_dir.request`, storing each session under `data/store/runs/<lab>/<run>/run.json`.
  - Resolved policy from `core.policy.get.request` (or local defaults) injected into labs without importing Core Center directly.
- Current labs: gravity demo and projectile motion (both with reduced-motion support and Explorer diagnostics).

## Module / Content Browser
- Uses `content_system.list_tree()` to display the Subject Module → Section → Package → Part hierarchy.
- Each part shows status, install buttons, markdown preview, or lab launch hooks.
- Settings dialog controls UI pack selection, Reduced Motion, and profile—all applied at runtime.
