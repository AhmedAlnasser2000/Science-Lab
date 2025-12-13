# Content System

V1 loader/resolver for PhysicsLab content using only the frozen schemas and example pack in `content_repo/physics_v1/`. It builds the Subject Module → Section → Package → Part tree, reports per-part status, and can copy parts and their assets into `content_store/physics_v1/`.

## API (importable)
- `list_tree() -> dict` — read module/section/package/part manifests from the repo and report part statuses (READY, NOT_INSTALLED, UNAVAILABLE).
- `get_part(part_id) -> dict` — return manifest plus resolved repo/store paths.
- `get_part_status(part_id) -> (status, reason)` — lightweight status lookup.
- `download_part(part_id) -> dict` — copy the part folder and referenced assets from repo to store, then return the resulting status.

## Demo
Run from repo root:
```bash
python content_system/demo_print_tree.py
```
The demo prints the tree, downloads the gravity demo part, and prints the tree again to show the status change.
