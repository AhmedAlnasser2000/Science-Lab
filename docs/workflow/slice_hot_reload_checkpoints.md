# Slice Hot-Reload Checkpoints (Workflow)
_Last updated: 2026-02-18_

This workflow describes gate-based slice execution with local scratch tracking via `.slice_tmp/<slice_id>/`.

## Policy status
This is a permanent workflow standard for slice execution.

- Start a session at slice start.
- Maintain gate records during implementation.
- Do not commit slice changes until session/gate artifacts exist and reflect actual status.
- UI gates remain pending until user in-app confirmation.

## Finalize safety contract
- `finalize <slice_id>` is dry-run by default.
- Dry run must print:
  - `Would delete: <path>`
  - `DRY RUN (no deletion performed)`
- `finalize <slice_id> --delete` performs actual deletion.
- Delete mode must print:
  - `DELETED: <path>`

## Containment guard
Before delete mode executes, target path must resolve inside `.slice_tmp/` root.  
Path traversal and absolute-path IDs are rejected (for example `..`, `../..`, `..\\..`, `C:\\Windows`).

## Test coverage requirement
`tests/test_slice_session.py` must include:
- dry run leaves session directory intact
- `--delete` removes only the intended session directory
- malicious IDs are rejected and do not delete outside sandbox

## Reference
See `docs/handbook/slice_hot_reload_checkpoints.md` for the full gate/checkpoint contract and rollback guidance.
