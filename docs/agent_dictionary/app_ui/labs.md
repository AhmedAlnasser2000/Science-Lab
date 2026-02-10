# app_ui/labs Agent Map

Lab host and plugin map for quick navigation.

## host.py
- **Path:** `app_ui/labs/host.py`
- **Role:** LabHost orchestration, plugin selection, and host panel state.
- **Key symbols:** host window/screen classes and plugin routing helpers.
- **Edit-when:** lab shell behavior, host-level controls, plugin handoff.
- **NAV anchors:** `[NAV-10]` context/policy wiring, `[NAV-20]` ctor/layout, `[NAV-30]` guide/tier gating, `[NAV-40]` export actions, `[NAV-50]` plugin lifecycle, `[NAV-90]` helpers.
- **Risks/Notes:** Central integration point for all lab plugins.

## gravity_lab.py
- **Path:** `app_ui/labs/gravity_lab.py`
- **Role:** Gravity lab plugin UI and simulation controls.
- **Edit-when:** gravity-specific controls, rendering values, output formatting.

## projectile_lab.py
- **Path:** `app_ui/labs/projectile_lab.py`
- **Role:** Projectile motion lab plugin behavior.
- **Edit-when:** projectile inputs, run controls, chart/output sections.

## electric_field_lab.py
- **Path:** `app_ui/labs/electric_field_lab.py`
- **Role:** Electric field lab plugin.
- **Edit-when:** field setup UX, simulation/render controls.

## lens_ray_lab.py
- **Path:** `app_ui/labs/lens_ray_lab.py`
- **Role:** Lens/ray optics lab plugin.
- **Edit-when:** lens parameters, ray rendering behavior, measurement displays.

## vector_add_lab.py
- **Path:** `app_ui/labs/vector_add_lab.py`
- **Role:** Vector addition lab plugin.
- **Edit-when:** vector entry controls and vector visualization behavior.

## Shared notes
- Keep plugin surface compatible with host expectations in `host.py`.
- Prefer plugin-local changes over host-wide behavior changes.

## Lab plumbing files

## base.py
- **Path:** `app_ui/labs/base.py`
- **Role:** Common base abstractions for lab plugins.
- **Key symbols:** base lab class contracts and shared interfaces.
- **Edit-when:** Shared plugin contract changes across labs.
- **NAV anchors:** file-local (no dedicated NAV index yet).
- **Risks/Notes:** Changes can affect all lab plugins.

## context.py
- **Path:** `app_ui/labs/context.py`
- **Role:** Host/plugin context object and capability wiring.
- **Key symbols:** context carrier types and helpers.
- **Edit-when:** Lab context payload changes and host-plugin integration.
- **NAV anchors:** file-local (no dedicated NAV index yet).
- **Risks/Notes:** Keep backward compatibility with existing plugins.

## registry.py
- **Path:** `app_ui/labs/registry.py`
- **Role:** Plugin registration and lookup map.
- **Key symbols:** registry declarations and plugin discovery utilities.
- **Edit-when:** Adding/removing labs or changing plugin metadata contract.
- **NAV anchors:** file-local (no dedicated NAV index yet).
- **Risks/Notes:** Incorrect registration can hide labs from the host.

## prefs_store.py
- **Path:** `app_ui/labs/prefs_store.py`
- **Role:** Per-lab preference persistence helpers.
- **Key symbols:** save/load preference utilities.
- **Edit-when:** Preference schema/path behavior changes.
- **NAV anchors:** file-local (no dedicated NAV index yet).
- **Risks/Notes:** Avoid breaking existing saved preference files.
