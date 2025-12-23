from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PyQt6 import QtWidgets

from app_ui.labs.host import LabHost

from .context import ComponentContext
from .types import ComponentKind


class LabHostComponent:
    def __init__(self, lab_id: str, display_name: str, lab_registry: Any):
        self.component_id = f"labhost:{lab_id}"
        self.display_name = f"LabHost: {display_name}"
        self.kind = ComponentKind.LAB
        self._lab_id = lab_id
        self._lab_registry = lab_registry

    def create_widget(self, ctx: ComponentContext) -> QtWidgets.QWidget:
        plugin = self._lab_registry.get_lab(self._lab_id)
        if not plugin:
            raise RuntimeError(f"Lab '{self._lab_id}' not available.")
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
        part_id, manifest, detail = self._resolve_part(ctx, self._lab_id)
        if part_id and hasattr(widget, "load_part"):
            widget.load_part(part_id, manifest, detail)
        guide_text = self._load_guide_text(manifest, detail, ctx.profile)
        return LabHost(
            self._lab_id,
            widget,
            guide_text,
            ctx.reduced_motion,
            bus=ctx.bus,
            profile=ctx.profile,
            plugin=plugin,
        )

    def dispose(self) -> None:
        return

    @staticmethod
    def _resolve_part(ctx: ComponentContext, lab_id: str) -> Tuple[Optional[str], Dict, Dict]:
        if ctx.part_id and isinstance(ctx.detail, dict):
            manifest = ctx.detail.get("manifest") or {}
            return ctx.part_id, manifest, ctx.detail
        adapter = ctx.content_adapter
        if not adapter:
            return None, {}, {}
        try:
            data = adapter.list_tree()
        except Exception:
            return None, {}, {}
        module = data.get("module") if isinstance(data, dict) else None
        if not isinstance(module, dict):
            return None, {}, {}
        part_id = None
        for section in module.get("sections", []):
            for package in section.get("packages", []):
                for part in package.get("parts", []):
                    if part.get("status") != "READY":
                        continue
                    candidate_id = part.get("part_id")
                    if not candidate_id:
                        continue
                    lab = part.get("lab")
                    lab_match = isinstance(lab, dict) and lab.get("lab_id") == lab_id
                    if lab_match or str(candidate_id).endswith("_demo"):
                        part_id = candidate_id
                        break
                if part_id:
                    break
            if part_id:
                break
        if not part_id:
            return None, {}, {}
        try:
            detail = adapter.get_part(part_id)
        except Exception:
            return part_id, {}, {}
        manifest = detail.get("manifest") or {}
        return part_id, manifest, detail

    @staticmethod
    def _load_guide_text(manifest: Dict, detail: Dict, profile: str) -> str:
        fallback = "Guide coming soon for this lab."
        if not isinstance(manifest, dict):
            return fallback
        guides = (manifest.get("x_extensions") or {}).get("guides")
        if not isinstance(guides, dict):
            return fallback
        key_map = {"Learner": "learner", "Educator": "educator", "Explorer": "explorer"}
        key = key_map.get(profile, "learner")
        asset_path = guides.get(key)
        if not asset_path:
            for alt in ("learner", "educator", "explorer"):
                asset_path = guides.get(alt)
                if asset_path:
                    break
        if not asset_path:
            asset_path = next(iter(guides.values()), None)
        if not asset_path:
            return fallback
        text = _read_asset_text(asset_path, detail.get("paths"))
        return text if text is not None else "Guide asset missing or unreadable. Reinstall the part if this persists."


def _read_asset_text(asset_path: Optional[str], paths: Optional[Dict[str, Any]]) -> Optional[str]:
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


def make_lab_component(lab_id: str, display_name: str, lab_registry: Any) -> LabHostComponent:
    return LabHostComponent(lab_id, display_name, lab_registry)
