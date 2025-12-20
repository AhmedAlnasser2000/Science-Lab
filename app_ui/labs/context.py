from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class LabUserPrefs:
    """User-controlled display preferences for a lab."""

    show_grid: bool = True
    show_axes: bool = True


@dataclass
class LabContext:
    """Runtime context passed from LabHost to lab widgets."""

    lab_id: str
    profile: str
    reduced_motion: bool
    run_id: Optional[str]
    run_dir: Optional[str]
    policy: Dict[str, Any] = field(default_factory=dict)
    user_prefs: LabUserPrefs = field(default_factory=LabUserPrefs)
