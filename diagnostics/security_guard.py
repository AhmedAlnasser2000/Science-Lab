from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

KNOWN_CAPABILITIES = [
    "fs.read_store",
    "fs.write_store",
    "ui.render",
    "lab.run",
]


def validate_capabilities(capabilities: Iterable[str]) -> List[str]:
    unknown = [cap for cap in capabilities if cap not in KNOWN_CAPABILITIES]
    return unknown


def resolve_under_root(root: Path, rel: str) -> Path:
    rel_path = Path(rel)
    if rel_path.is_absolute():
        raise ValueError("Absolute paths are not allowed.")
    if rel.startswith(("\\\\", "//")):
        raise ValueError("UNC paths are not allowed.")
    if rel_path.drive:
        raise ValueError("Drive paths are not allowed.")
    if any(part == ".." for part in rel_path.parts):
        raise ValueError("Path traversal is not allowed.")
    resolved_root = root.resolve()
    resolved = (resolved_root / rel_path).resolve()
    try:
        resolved.relative_to(resolved_root)
    except Exception as exc:
        raise ValueError("Resolved path escapes root.") from exc
    return resolved
