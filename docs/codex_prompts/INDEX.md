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
| 2026-01-06__V5.4i__pillars__p8_tracing_contract_p7_telemetry_opt_in.md | TBD | Make P8/P7 real: tracing span contract + deterministic span emission; telemetry strictly opt-in; pillars checks + tests |
<<<<<<< HEAD
| 2026-01-06__V5.4j__pillars__p11_pack_metadata_p12_security_boundaries.md | TBD | Make P11/P12 real: pack manifests + dependency validation; strict path containment + capabilities concept; pillars checks + tests |
| 2026-01-06__V5.4j1__pillars__add_pack_manifests_to_stores.md | TBD | Add missing pack manifests in store roots so P11 passes |
=======
>>>>>>> origin/main
| 2026-01-06__V5.4i1__system_health__pillars_worker_deleted_guard.md | TBD | Fix System Health Pillars cleanup: avoid calling deleteLater on already-deleted TaskWorker |
| 2026-01-06 — PR #18 merged: V5.4g (P1/P2/P9 checks) + V5.4g2b (QThread abort fix) |
