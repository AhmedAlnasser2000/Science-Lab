from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

from PyQt6 import QtGui, QtSvg


DEFAULT_STORE_ROOT = Path("content_store/physics_v1")


class AssetResolver:
    """Resolves content-relative asset paths into absolute store paths."""

    def __init__(self, content_store_root: Path = DEFAULT_STORE_ROOT):
        self.content_store_root = Path(content_store_root).resolve()

    @classmethod
    def from_detail(cls, detail: Dict, fallback: Path = DEFAULT_STORE_ROOT) -> "AssetResolver":
        paths = detail.get("paths") if isinstance(detail, dict) else {}
        store_manifest = paths.get("store_manifest") if isinstance(paths, dict) else None
        if store_manifest:
            base = Path(store_manifest).resolve().parent
        else:
            base = Path(fallback).resolve()
        return cls(base)

    def resolve(self, rel_path: str) -> Optional[Path]:
        if not rel_path:
            return None
        path_obj = Path(rel_path)
        # Allow absolute paths as-is.
        if path_obj.is_absolute():
            return path_obj if path_obj.exists() else None

        # Strip optional leading module folder (e.g., physics_v1/...).
        parts = path_obj.parts
        if parts and parts[0] == self.content_store_root.name:
            path_obj = Path(*parts[1:])

        candidate = (self.content_store_root / path_obj).resolve()
        try:
            candidate.relative_to(self.content_store_root)
        except ValueError:
            return None
        return candidate if candidate.exists() else None


class AssetCache:
    """Small cache for SVG renderers and pixmaps keyed by path and DPI bucket."""

    def __init__(self):
        self._svg_renderers: Dict[Tuple[Path], QtSvg.QSvgRenderer] = {}
        self._pixmaps: Dict[Tuple, QtGui.QPixmap] = {}

    def _dpi_bucket(self, dpi_scale: float) -> float:
        # Bucket to 0.25 steps for stability.
        return round(max(0.5, dpi_scale) / 0.25) * 0.25

    def get_svg_renderer(self, path: Path) -> Optional[QtSvg.QSvgRenderer]:
        key = (Path(path).resolve(),)
        if key in self._svg_renderers:
            return self._svg_renderers[key]
        if not Path(path).exists():
            return None
        try:
            renderer = QtSvg.QSvgRenderer(str(path))
            if renderer.isValid():
                self._svg_renderers[key] = renderer
                return renderer
        except Exception:
            return None
        return None

    def get_pixmap(
        self,
        path: Path,
        size_px: Tuple[int, int],
        *,
        dpi_scale: float = 1.0,
        tint: Optional[QtGui.QColor] = None,
    ) -> Optional[QtGui.QPixmap]:
        bucket = self._dpi_bucket(dpi_scale)
        norm_path = Path(path).resolve()
        key = (norm_path, size_px, tint.rgba() if tint else None, bucket)
        cached = self._pixmaps.get(key)
        if cached:
            return QtGui.QPixmap(cached)

        if not norm_path.exists():
            return None

        try:
            if norm_path.suffix.lower() == ".svg":
                pixmap = self._render_svg_to_pixmap(norm_path, size_px, bucket, tint)
            else:
                pixmap = QtGui.QPixmap(str(norm_path))
                if tint:
                    pixmap = self._tint_pixmap(pixmap, tint)
            if pixmap and not pixmap.isNull():
                pixmap.setDevicePixelRatio(bucket)
                self._pixmaps[key] = QtGui.QPixmap(pixmap)
                return pixmap
        except Exception:
            return None
        return None

    def _render_svg_to_pixmap(
        self,
        path: Path,
        size_px: Tuple[int, int],
        dpi_scale: float,
        tint: Optional[QtGui.QColor],
    ) -> Optional[QtGui.QPixmap]:
        renderer = self.get_svg_renderer(path)
        if not renderer:
            return None
        w, h = size_px
        w = max(1, int(w * dpi_scale))
        h = max(1, int(h * dpi_scale))
        image = QtGui.QImage(w, h, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QtGui.QPainter(image)
        try:
            renderer.render(painter)
        finally:
            painter.end()
        if tint:
            image = self._tint_image(image, tint)
        pixmap = QtGui.QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(dpi_scale)
        return pixmap

    def _tint_image(self, image: QtGui.QImage, color: QtGui.QColor) -> QtGui.QImage:
        tinted = QtGui.QImage(image.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        tinted.fill(0)
        painter = QtGui.QPainter(tinted)
        try:
            painter.drawImage(0, 0, image)
            painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(tinted.rect(), color)
        finally:
            painter.end()
        return tinted

    def _tint_pixmap(self, pixmap: QtGui.QPixmap, color: QtGui.QColor) -> QtGui.QPixmap:
        image = pixmap.toImage()
        tinted = self._tint_image(image, color)
        return QtGui.QPixmap.fromImage(tinted)

