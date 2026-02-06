# Codex Prompt Index

Definition of Done:
- Save prompt docs under `docs/codex_prompts/`.
- Append an entry to this index in the same PR.
- Update the commit hash after merge (use `TBD` until then).

| Prompt file | Commit | Notes |
| --- | --- | --- |
| V5.4/feat/2026-01-02__V5.4__pillars__harness_scaffold.md | TBD | Pillars verification harness scaffold and diagnostics provider host |
| V5.4/feat/2026-01-03__V5.4c__pillars__checks_v1.md | TBD | Add first actionable pillar checks (CI baseline + runtime data hygiene) and tighten CI compile step |
| V5.4/feat/2026-01-03__V5.4d__pillars__ui_view_and_run.md | TBD | Add Pillars UI view + run harness inside System Health |
| V5.4/feat/2026-01-03__V5.4e__pillars__ui_polish_and_hygiene.md | TBD | Pillars UI polish, filter toggle, and dev hygiene notes |
| V5.4/chore/2026-01-03__V5.4f__dev__codex_prompt_index_append.md | TBD | Codex prompt index workflow guardrails and backfill |
| V5.4/feat/2026-01-05__V5.4g__pillars__checks_v2_p1_p9_p2.md | TBD | Add real pillars checks for P1/P9 (+ optional P2) with unit tests |
| V5.4/fix/2026-01-05__V5.4g1__pillars__ui_run_freeze_quit_fix.md | TBD | Fix Pillars UI run action freeze/quit; harden harness invocation and error handling |
| V5.4/fix/2026-01-05__V5.4g2b__system_health__qthread_lifecycle_fix.md | TBD | Fix Qt abort by holding System Health Pillars QThread refs until thread.finished; safe teardown |
| V5.4/docs/2026-01-05__V5.4gR__recon__qthread_abort_across_ui_actions.md | TBD | Recon: QThread destroyed while running across UI actions (no code edits) |
| V5.4/feat/2026-01-06__V5.4h__pillars__p5_crash_capture_p6_logging_baseline.md | TBD | Make P5/P6 real: crash capture dir + safe viewer entry point; structured logging baseline; pillars checks + tests |
| V5.4/feat/2026-01-06__V5.4i__pillars__p8_tracing_contract_p7_telemetry_opt_in.md | TBD | Implemented P8/P7: tracing span contract + deterministic span emission; telemetry strictly opt-in; pillars checks + tests |
| V5.4/fix/2026-01-06__V5.4i1__system_health__pillars_worker_deleted_guard.md | TBD | Fix System Health Pillars cleanup: avoid calling deleteLater on already-deleted TaskWorker |
| V5.4/feat/2026-01-06__V5.4j__pillars__p11_pack_metadata_p12_security_boundaries.md | TBD | Implemented P11/P12: pack manifests + dependency validation; strict path containment + capabilities concept; pillars checks + tests |
| V5.4/fix/2026-01-06__V5.4j1__pillars__add_pack_manifests_to_stores.md | TBD | Add missing pack manifests in store roots so P11 passes |
| V5.4/feat/2026-01-06__V5.4k__release__packaging_pipeline_p4.md | TBD | Add Windows packaging pipeline + P4 pillar check/tests |
| V5.4/fix/2026-01-06__V5.4k1__release__build_windows_import_path_fix.md | TBD | Fix build_windows.py sys.path so app_ui imports succeed |
| V5.4/fix/2026-01-06__V5.4k2__release__pyinstaller_spec_invocation_fix.md | TBD | Fix PyInstaller spec invocation flags for release build |
| V5.4/fix/2026-01-06__V5.4k3__release__dist_cleanup_lock_hint.md | TBD | Pre-clean dist output and fail fast with a locked-folder hint |

| Prompt file | Commit | Notes |
| --- | --- | --- |
| V5.5/V5.5a/feat/2026-01-07__V5.5a__codesee__edge_following_pulses.md | TBD | CodeSee pulses follow edge paths for rendering and animation |
| V5.5/V5.5a/feat/2026-01-07__V5.5a1__codesee__distance_based_pulse_speed.md | TBD | Distance-based pulse speed along edge paths |
| V5.5/V5.5b/feat/2026-01-11__V5.5b1__codesee__context_sticky_highlight_and_badge_overflow.md | TBD | Context-sticky highlight and compressed status badges with overflow menu |
| V5.5/V5.5b/fix/2026-01-12__V5.5b1__codesee__badge_overflow_pill_fix.md | 20b4673 | Fix badge overflow pill + clipping + aggregated dropdown counts |
| V5.5/V5.5b/fix/2026-01-12__V5.5b1__codesee__badges_dedup_ellipsis_overflow_priority.md | TBD | Dedup badges, overflow priority, ellipsis hint |
| V5.5/V5.5b/fix/2026-01-12__V5.5b1.1__codesee__overflow_pill_label_bugfix.md | 85fac3 | Fix overflow pill label and error badge correctness |
| V5.5/V5.5b/patch/2026-01-12__V5.5b1.1__codesee__dropdown_breakdown_before_legend__patch.md | 2202c17 | Ensure dropdown breakdown appears before legend |
| V5.5b1.2 (uncommitted in github because i forgot and went to 5.5b.3 directly) | TBD | Uncommitted work: dropdown totals shown per type (active vs session) |
| V5.5/V5.5b/feat/2026-01-17__V5.5b1.3__codesee__totals_semantics_active_vs_occurrences.md | 1238492 | Clarify totals: active now vs session occurrences |
| V5.5/V5.5c/chore/2026-01-19__V5.5c__versioning__auto_git_version.md | TBD | Derive app_version from latest git milestone and enforce in Pillar P1 |
| V5.5/V5.5c/docs/2026-01-19__V5.5c__lens_palette_box_design_reference.md | TBD | Lens palette box design reference |
| V5.5/V5.5c/feat/2026-01-19__V5.5c1__codesee__lens_palette_launcher.md | TBD | Floating lens palette launcher with pin + persistence |
| V5.5/V5.5c/fix/2026-01-19__V5.5c1__codesee__lens_palette_selection_fix.md | TBD | Fix lens palette selection wiring and add diagnostics |
| V5.5/V5.5c/feat/2026-01-19__V5.5c2__codesee__lens_palette_box_ui.md | TBD | Box-style lens palette UI with search + tile grid using reference design |
| V5.5/V5.5c/fix/2026-01-20__V5.5c3__codesee__lens_palette_pinned_layout_and_more.md | TBD | Fix pinned palette layout so tiles render; wire More/Less expansion |
| V5.5/V5.5c/fix/2026-01-20__V5.5c4__codesee__lens_palette_tiles_render_and_search.md | TBD | Ensure lens palette tiles render and search shows results or empty state |
| V5.5/V5.5c/fix/2026-01-20__V5.5c5__codesee__lens_palette_build_from_combo_and_status_line.md | TBD | Lens palette builds from combo inventory; status line + search filtering; never-blank grid |
| V5.5/V5.5c/patch/2026-01-20__V5.5c6__codesee__lens_palette_rebuild_from_scratch.md | TBD | Rebuild lens palette from scratch with combo-driven tiles and always-visible status |
| V5.5/V5.5c/patch/2026-01-20__V5.5c7__codesee__icon_pack_style_recursion_and_palette_growth.md | TBD | Fix icon style normalization to stop Path recursion; prevent palette refresh loop/growth |
| V5.5/V5.5c/patch/2026-01-20__V5.5c8__codesee__stability_recursion_and_palette_resize.md | TBD | CodeSee stability hotfix: safe mode + hook reentrancy guard + palette resize safeguards |
| V5.5/V5.5c/chore/2026-01-20__V5.5c9__codesee__cleanup_palette_debug_and_keep_safety_guards.md | TBD | Reduce CodeSee debug spam while keeping safety guards |
| V5.5/V5.5c/feat/2026-01-20__V5.5c10__codesee__floating_resizable_lens_palette_dockwidget.md | TBD | Make Lens Palette floatable/resizable via QDockWidget with persisted dock state |
| V5.5/V5.5c/fix/2026-01-21__V5.5c10.1__codesee__dockwidget_drag_float_and_multi_dock_areas.md | TBD | Restore drag-to-float and dock-anywhere behavior for Lens Palette |
| V5.5/V5.5c/feat/2026-01-21__V5.5c11__codesee__more_menu_codesee_diagnostics.md | TBD | Add CodeSee-scoped diagnostics dialog from lens palette More menu |
| V5.5/V5.5c/fix/2026-01-21__V5.5c11.1__codesee__dockwidget_height_resize_wm_destroy.md | TBD | Fix docked height resize stability and avoid WM_DESTROY spam during palette resizing |
| V5.5/V5.5c/docs/2026-01-26__V5.5c12__docs__docs_and_milestones_organization.md | TBD | Docs taxonomy + milestones organization plan |
| V5.5/V5.5c/chore/2026-02-03__V5.5c13__codesee__screen_py_declutter_split.md | TBD | Split CodeSee screen.py into focused modules (lens palette + dialogs) without behavior changes |
| V5.5/V5.5c/chore/2026-02-04__V5.5c13__codesee__nav_annotations_v2.md | TBD | Add NAV annotations to CodeSee modules (screen, palette, dialogs) |
| V5.5/V5.5c/chore/2026-02-06__V5.5c13.1__codesee__agent_dictionary_and_declutter.md | TBD | Add agent dictionary docs and declutter plan for codesee subpackages |
