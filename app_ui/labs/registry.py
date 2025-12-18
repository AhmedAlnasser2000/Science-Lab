from __future__ import annotations

from typing import Dict, Optional

from .gravity_lab import GravityLabPlugin
from .projectile_lab import ProjectileLabPlugin
from .electric_field_lab import ElectricFieldLabPlugin
from .lens_ray_lab import LensRayLabPlugin
from .vector_add_lab import VectorAddLabPlugin
from .base import LabPlugin

_REGISTRY: Dict[str, LabPlugin] = {}


def _register(plugin: LabPlugin) -> None:
    _REGISTRY[plugin.id] = plugin


_register(GravityLabPlugin())
_register(ProjectileLabPlugin())
_register(ElectricFieldLabPlugin())
_register(LensRayLabPlugin())
_register(VectorAddLabPlugin())


def get_lab(lab_id: str) -> Optional[LabPlugin]:
    return _REGISTRY.get(lab_id)


def list_labs() -> Dict[str, LabPlugin]:
    return dict(_REGISTRY)
