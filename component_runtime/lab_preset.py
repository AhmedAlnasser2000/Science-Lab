from __future__ import annotations

from pathlib import Path
from typing import Dict

from PyQt6 import QtWidgets

from app_ui.labs import registry as lab_registry
from app_ui.labs.host import LabHost

from .context import ComponentContext
from .types import ComponentKind


class LabPresetLauncherComponent:
    def __init__(
        self,
        component_id: str,
        display_name: str,
        kind: ComponentKind,
        pack_root: Path,
        params: Dict,
    ) -> None:
        self.component_id = component_id
        self.display_name = display_name
        self.kind = kind
        self._pack_root = Path(pack_root).resolve()
        self._params = params or {}

    def create_widget(self, ctx: ComponentContext) -> QtWidgets.QWidget:
        lab_id = self._params.get("lab_id")
        if not isinstance(lab_id, str) or not lab_id.strip():
            raise RuntimeError("lab_id missing for lab preset component")
        plugin = lab_registry.get_lab(lab_id)
        if not plugin:
            raise RuntimeError(f"Lab '{lab_id}' not available")
        widget = plugin.create_widget(lambda: None, lambda: ctx.profile)
        if not isinstance(widget, QtWidgets.QWidget):
            raise TypeError("Lab widgets must extend QWidget")
        if hasattr(widget, "set_profile"):
            widget.set_profile(ctx.profile)
        if hasattr(widget, "set_reduced_motion"):
            try:
                widget.set_reduced_motion(ctx.reduced_motion)
            except Exception:
                pass
        manifest, detail = self._build_manifest_and_detail(lab_id)
        if hasattr(widget, "load_part"):
            widget.load_part(f"{lab_id}_preset", manifest, detail)
        guide_text = "Guide coming soon for this lab preset."
        return LabHost(
            lab_id,
            widget,
            guide_text,
            ctx.reduced_motion,
            bus=ctx.bus,
            profile=ctx.profile,
            plugin=plugin,
        )

    def dispose(self) -> None:
        return

    def _build_manifest_and_detail(self, lab_id: str) -> tuple[Dict, Dict]:
        manifest: Dict = {}
        params = self._params.get("parameters")
        if isinstance(params, dict):
            manifest["behavior"] = {"parameters": dict(params)}
        detail = {
            "paths": {
                "store_manifest": str(self._pack_root / "component_pack_manifest.json"),
            }
        }
        return manifest, detail
