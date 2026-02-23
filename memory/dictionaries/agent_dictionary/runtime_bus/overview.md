> Snapshot generated during slice d9 from working tree based on HEAD 55fbe3f80f21b0722c1d7ab46aa5ee467f8cb766.
> Snapshot copy for portability; source-of-truth remains under docs/ at commit 55fbe3f80f21b0722c1d7ab46aa5ee467f8cb766.

# runtime_bus Agent Map

## Path(s)
- `runtime_bus/`
- common touchpoints in `app_ui/*` and `app_ui/codesee/runtime/*`

## Role
- Message bus topics, publish/request interfaces, and runtime event transport.

## Key symbols
- Topics module(s), publish/request entrypoints, envelope/event payload contracts.

## Edit-when
- Adding/changing bus topic names.
- Adjusting request/reply timeout behavior.
- Evolving payload schema shared across app and backend modules.

## Risks/Notes
- Topic name drift causes silent integration failures.
- Keep payload changes backward-compatible or versioned.

## NAV quick jumps
- placeholder (to backfill when runtime_bus NAV anchors are added).

