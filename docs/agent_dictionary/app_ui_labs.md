# app_ui/labs Agent Map

Lab host and plugin map for quick navigation.

## host.py
- **Path:** `app_ui/labs/host.py`
- **Role:** LabHost orchestration, plugin selection, and host panel state.
- **Key symbols:** host window/screen classes and plugin routing helpers.
- **Edit-when:** lab shell behavior, host-level controls, plugin handoff.
- **NAV anchors:** file-local.
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
