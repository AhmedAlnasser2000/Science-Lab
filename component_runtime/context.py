from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class StorageRoots:
    roaming: Path
    store: Path
    runs: Path
    runs_local: Path


@dataclass
class ComponentContext:
    """Context provided to components at creation time."""

    bus: Any
    policy: Dict[str, Any]
    storage: StorageRoots
    profile: str
    reduced_motion: bool
    content_adapter: Optional[Any] = None
