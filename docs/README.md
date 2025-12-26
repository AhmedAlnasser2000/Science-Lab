# Docs Index

This folder holds checkpoint summaries, plans, prompts, and overview notes for PhysicsLab.

## Canonical checkpoint
- `docs/app_summary.md`: current, code-verified checkpoint summary.

## Checkpoints and inputs
- `docs/checkpoints/README.md`: checkpoint conventions and workflow.
- `docs/checkpoints/history/`: archived checkpoint snapshots (date/hash in filename).
- `docs/checkpoints/inputs/`: raw input artifacts used during reconciliation.

## Reference docs
- `docs/handbook/app_handbook.md`: contributor handbook.
- `docs/overviews/`: version overviews.
- `docs/plans/`: design plans.
- `docs/prompts/`: diagram and tooling prompts.
- `docs/snapshots/`: captured repo trees or other snapshots.

## Adding a new checkpoint
1) Update `docs/app_summary.md`.
2) Copy the previous `docs/app_summary.md` into `docs/checkpoints/history/` using date + git hash.
3) Record verification commands and manual checks in the summary appendix.
