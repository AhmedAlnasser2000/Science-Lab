# UI System (V2.2 Path A)

Manages optional UI packs (QSS skins) with reduced-motion awareness. Runs standalone; not wired into app startup.

## Structure
- `ui_repo/ui_v1/packs/default/` — built-in pack with `ui_pack_manifest.json` and `default.qss`.
- `ui_store/` — placeholder for installed packs (store takes precedence when present).
- Config: `data/roaming/ui_config.json` (`active_pack_id`, `reduced_motion`).

## Functions
- `list_packs(repo_root, store_root)` → list of Pack
- `resolve_pack(pack_id, prefer_store=True)` → Pack | None
- `get_active_pack(config_path)` / `set_active_pack(config_path, pack_id)`
- `load_qss(pack)` → concatenated QSS text
- `apply_qss(app, qss_text)` → applies stylesheet safely

## Manifest Fields
`id, name, version, description, author, license, targets, min_app_version, qss_files, assets, supports_reduced_motion`

## Demo
Run from repo root:
```bash
python -m ui_system.demo_apply
```
Shows a small PyQt6 window, applies the active pack (falls back to `default`), and prints which pack was used. Exits cleanly even if folders are missing.***
