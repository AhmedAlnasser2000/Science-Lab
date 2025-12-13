# App UI

PyQt5 front-end for PhysicsLab V1. It currently provides a Main Menu plus a Module Manager that inspects the frozen Physics content pack through the `content_system` API.

## Requirements
- Python 3.10+
- [PyQt6](https://pypi.org/project/PyQt6/) (install via `pip install PyQt6`)
- Rust toolchain (for building the kernel DLL)

## Build + Run
1. Build the Rust kernel DLL (gravity demo):
   ```
   cargo build --release --manifest-path kernel/Cargo.toml
   ```
   Result: `kernel/target/release/physicslab_kernel.dll`
2. Launch the PyQt UI:
   ```
   python -m app_ui.main
   ```

## Features
- Main Menu indicates that the Primary Mode is active and links to the Module Manager.
- Module Manager displays the Subject Module → Section → Package → Part hierarchy using `content_system.list_tree()`.
- Selecting a part shows its status (via `get_part_status`) and previews text assets when available.
- `Download` button copies missing parts into `content_store/` using `download_part`.
- `Run` button (enabled for READY gravity demo parts) reminds users that the kernel is not wired yet.
