# Checkpoints

A checkpoint is a code-verified snapshot of the app's documented behavior at a specific commit.

## Canonical summary
- Current summary: `docs/app_summary.md`.
- Previous summary pointer: `docs/checkpoints/app_summary_previous.md`.

## History naming
- Format: `app_summary_<YYYY-MM-DD>_<commit>.md`.
- Optional suffixes (e.g., `_old`, `_pre_edit`, `_previous`) are retained for legacy duplicates; content is unchanged.

## Inputs naming
- Format: `app_summary_input_<YYYY-MM-DD>_<commit>_<label>.md`.
- Inputs are raw artifacts used during reconciliation, not canonical checkpoints.

## Create the next checkpoint
1) Update `docs/app_summary.md` with the new verified state and appendix.
2) Move the previous `docs/app_summary.md` into `docs/checkpoints/history/` using the naming format above.
3) Update `docs/checkpoints/app_summary_previous.md` to point at the new history entry.
4) Record the verification commands and manual checks in the appendix.
