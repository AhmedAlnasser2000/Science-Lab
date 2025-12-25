from pathlib import Path
from typing import Any, Dict, Optional


def read_asset_text(asset_path: Optional[str], paths: Optional[Dict[str, Any]]) -> Optional[str]:
    if not asset_path:
        return None
    assets = (paths or {}).get("assets") or {}
    path_info = assets.get(asset_path)
    if not isinstance(path_info, dict):
        return None
    for key in ("store", "repo"):
        candidate = path_info.get(key)
        if candidate:
            candidate_path = Path(candidate)
            if candidate_path.exists():
                try:
                    return candidate_path.read_text(encoding="utf-8")
                except OSError:
                    continue
    return None
