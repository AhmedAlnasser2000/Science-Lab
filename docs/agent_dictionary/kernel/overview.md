# kernel Agent Map

## Path(s)
- `kernel/` (native/runtime kernel)
- app touchpoints: `app_ui/kernel_bridge.py`, lab plugins under `app_ui/labs/*`

## Role
- Physics/runtime native kernel and exposed ABI consumed by app UI bridge.

## Key symbols
- Exported ABI symbols, world/session lifecycle functions, error retrieval contracts.

## Edit-when
- Adding/changing ABI function signatures.
- Updating bridge compatibility with new kernel symbols.
- Adjusting kernel packaging/load paths.

## Risks/Notes
- ABI mismatches can fail at runtime with opaque errors.
- Keep bridge and kernel symbol contracts synchronized.

## NAV quick jumps
- `app_ui/kernel_bridge.py [placeholder -> NAV-20 ABI symbol binding]`
