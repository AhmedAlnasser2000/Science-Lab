# Codex Prompt Index

Definition of Done:
- Save prompt docs under `docs/codex_prompts/`.
- Append an entry to this index in the same PR.
- Update the commit hash after merge (use `TBD` until then).

| Prompt file | Commit | Notes |
| --- | --- | --- |
| 2026-01-02__V5.4__pillars__harness_scaffold.md | TBD | Pillars verification harness scaffold and diagnostics provider host |
| 2026-01-03__V5.4c__pillars__checks_v1.md | TBD | Add first actionable pillar checks (CI baseline + runtime data hygiene) and tighten CI compile step |
| 2026-01-03__V5.4d__pillars__ui_view_and_run.md | TBD | Add Pillars UI view + run harness inside System Health |
| 2026-01-03__V5.4e__pillars__ui_polish_and_hygiene.md | TBD | Pillars UI polish, filter toggle, and dev hygiene notes |
| 2026-01-03__V5.4f__dev__codex_prompt_index_append.md | TBD | Codex prompt index workflow guardrails and backfill |
| 2026-01-05__V5.4g__pillars__checks_v2_p1_p9_p2.md | TBD | Add real pillars checks for P1/P9 (+ optional P2) with unit tests |
| 2026-01-05__V5.4g1__pillars__ui_run_freeze_quit_fix.md | TBD | Fix Pillars UI run action freeze/quit; harden harness invocation and error handling |
| 2026-01-05__V5.4g2b__system_health__qthread_lifecycle_fix.md | TBD | Fix Qt abort by holding System Health Pillars QThread refs until thread.finished; safe teardown |
| 2026-01-06__V5.4h__pillars__p5_crash_capture_p6_logging_baseline.md | TBD | Make P5/P6 real: crash capture dir + safe viewer entry point; structured logging baseline; pillars checks + tests |
| 2026-01-06__V5.4i__pillars__p8_tracing_contract_p7_telemetry_opt_in.md | TBD | Implemented P8/P7: tracing span contract + deterministic span emission; telemetry strictly opt-in; pillars checks + tests |
| 2026-01-06__V5.4j__pillars__p11_pack_metadata_p12_security_boundaries.md | TBD | Implemented P11/P12: pack manifests + dependency validation; strict path containment + capabilities concept; pillars checks + tests |
| 2026-01-06__V5.4j1__pillars__add_pack_manifests_to_stores.md | TBD | Add missing pack manifests in store roots so P11 passes |
| 2026-01-06__V5.4k__release__packaging_pipeline_p4.md | TBD | Add Windows packaging pipeline + P4 pillar check/tests |
| 2026-01-06__V5.4k1__release__build_windows_import_path_fix.md | TBD | Fix build_windows.py sys.path so app_ui imports succeed |
| 2026-01-06__V5.4k2__release__pyinstaller_spec_invocation_fix.md | TBD | Fix PyInstaller spec invocation flags for release build |
| 2026-01-06__V5.4k3__release__dist_cleanup_lock_hint.md | TBD | Pre-clean dist output and fail fast with a locked-folder hint |
| 2026-01-06__V5.4i1__system_health__pillars_worker_deleted_guard.md | TBD | Fix System Health Pillars cleanup: avoid calling deleteLater on already-deleted TaskWorker |

| Prompt file | Commit | Notes |
| --- | --- | --- |
| V5.5/2026-01-07__V5.5a__codesee__edge_following_pulses.md | TBD | CodeSee pulses follow edge paths for rendering and animation |
| V5.5/2026-01-07__V5.5b__codesee__node_activity_visibility_and_screen_context.md | TBD | Node activity visibility + minimal screen-context tracking in CodeSee |
| V5.5/2026-01-11__V5.5b1__codesee__context_sticky_highlight_and_badge_overflow.md | TBD | Context-sticky highlight and compressed status badges with overflow menu |
| V5.5/2026-01-12__V5.5b1__codesee__badge_overflow_pill_fix.md | TBD | Fix badge overflow pill + clipping + aggregated dropdown counts |
