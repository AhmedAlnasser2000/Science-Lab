# app_ui/codesee Agent Dictionary

Focused navigation map for CodeSee work. This is a fast path for agents; not a full architecture spec.

## Entry points

- **Path:** `app_ui/main.py`
  - **Role:** Registers/open CodeSee embedded and window variants.
  - **Key symbols:** imports of `CodeSeeScreen`, `CodeSeeWindow`, runtime hook install.
  - **Edit-when:** Wiring CodeSee entry, startup toggles, safe mode behavior.
  - **NAV anchors:** N/A.
  - **Do-not-touch / risks:** Avoid changing public CodeSee import paths.

- **Path:** `app_ui/codesee/screen.py`
  - **Role:** Main CodeSee orchestrator (UI wiring, runtime events, lens palette integration, rendering overlays).
  - **Key symbols:** `CodeSeeScreen`, `_ensure_lens_palette*`, `_on_runtime_event`, snapshot/crash methods.
  - **Edit-when:** Most feature work that spans UI + runtime state.
  - **NAV anchors:** `[NAV-20]`, `[NAV-40]`, `[NAV-60]`, `[NAV-70]`, `[NAV-80]`, `[NAV-90]`.
  - **Do-not-touch / risks:** Keep helper re-exports used by tests/importers stable.

- **Path:** `app_ui/codesee/window.py`
  - **Role:** Detached CodeSee window wrapper and host behavior.
  - **Key symbols:** `CodeSeeWindow`.
  - **Edit-when:** Window-only behavior or embedding differences.
  - **NAV anchors:** file-local.

## Current structure map

- **Path:** `app_ui/codesee/canvas/`
  - **Role:** Graph rendering primitives.
  - **Key symbols:** `GraphScene`, `GraphView`, node/edge item painting.
  - **Edit-when:** Visual graph behavior, edge/pulse drawing, hit testing.

- **Path:** `app_ui/codesee/runtime/`
  - **Role:** Runtime event model and hub.
  - **Key symbols:** `CodeSeeRuntimeHub`, `CodeSeeEvent`, `bus_bridge`, `hooks`.
  - **Edit-when:** Event ingestion, hook safety, bus connectivity.

- **Path:** `app_ui/codesee/collectors/`
  - **Role:** Atlas graph collection from workspace/runtime sources.
  - **Key symbols:** `atlas_builder`, `CollectorContext`, collectors.
  - **Edit-when:** What appears in Atlas/graph inventory.

- **Path:** `app_ui/codesee/ui/`
  - **Role:** UI components split from screen.
  - **Key symbols:** `LensPaletteWidget` in `ui/lens_palette.py`.
  - **Edit-when:** Palette visuals, filtering, dock orientation helper.
  - **NAV anchors:** `lens_palette.py [NAV-10..NAV-40]`.

- **Path:** `app_ui/codesee/dialogs/`
  - **Role:** Dialog UIs used by `CodeSeeScreen`.
  - **Key symbols:** `CodeSeeInspectorDialog`, `CodeSeeRemovedDialog`, `open_pulse_settings`.
  - **Edit-when:** Inspector/removed/pulse-settings UX and formatting.

- **Path:** `app_ui/codesee/` (root core-ish modules)
  - **Role:** Shared models, config I/O, diagnostics, snapshot/layout utilities, lens catalog.
  - **Key symbols:** `graph_model.py`, `lenses.py`, `view_config.py`, `layout_store.py`, `snapshot_io.py`, `snapshot_index.py`, `diagnostics.py`, `diagnostics_dialog.py`, `demo_graphs.py`, `log_buffer.py`, `crash_io.py`, `expectations.py`, `badges.py`, `diff.py`, `icon_pack.py`, `harness.py`.
  - **Edit-when:** Focused logic updates not tied to canvas/runtime package internals.
  - **Do-not-touch / risks:** `crash_io.py` and `expectations.py` are used outside CodeSee.

## Where to implement common tasks

- **UI tweaks (palette/dialogs/screen):**
  - `app_ui/codesee/ui/lens_palette.py` for palette layout/filter/menu.
  - `app_ui/codesee/dialogs/*.py` for dialog text/layout.
  - `app_ui/codesee/screen.py` for orchestration and actions.

- **Runtime overlays/events:**
  - `app_ui/codesee/runtime/events.py`, `app_ui/codesee/runtime/hub.py`, `app_ui/codesee/screen.py` (`[NAV-60]`, `[NAV-70]`).

- **Snapshot/diff/crash handling:**
  - Snapshot I/O/index: `snapshot_io.py`, `snapshot_index.py`.
  - Diff logic: `diff.py`.
  - Crash load/clear badges: `crash_io.py`, `screen.py` (`[NAV-80]`, `[NAV-90E]`).

## Tests

- **Path:** `tests/test_codesee_lens_palette.py`
  - **Covers:** lens tile filtering/orientation helpers + palette integration pieces.

- **Path:** `tests/test_codesee_icon_pack.py`
  - **Covers:** icon style normalization and icon path safety.

- **Path:** `tests/test_codesee_diagnostics.py`
  - **Covers:** diagnostics snapshot/format output stability.

- **Path:** `tests/test_codesee_status_overflow.py`
  - **Covers:** status overflow/label formatting helpers.

- **Path:** `tests/test_codesee_pulse_path.py`
  - **Covers:** pulse path sampling/geometry behavior.

- **Path:** `tests/test_codesee_distance_mapping.py`
  - **Covers:** distance mapping helpers.

- **Path:** `tests/test_codesee_view_config.py`
  - **Covers:** view config persistence/sanitization for CodeSee state.
