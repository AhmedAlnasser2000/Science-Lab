from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from PyQt6 import QtCore, QtWidgets

_STATE_PATH = Path("data/roaming/window_state.json")


class WindowStateStore:
    def __init__(self) -> None:
        self._data = self._load_state()

    def _load_state(self) -> Dict:
        if not _STATE_PATH.exists():
            return {}
        try:
            data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _save_state(self) -> None:
        try:
            _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _STATE_PATH.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception:
            return

    def save_geometry(self, window: QtWidgets.QWidget, key: str) -> None:
        if not key:
            return
        blob = window.saveGeometry()
        encoded = bytes(blob.toBase64()).decode("ascii")
        self._data[key] = encoded
        self._save_state()

    def restore_geometry(self, window: QtWidgets.QWidget, key: str) -> None:
        encoded = self._data.get(key)
        if not isinstance(encoded, str) or not encoded:
            return
        try:
            data = QtCore.QByteArray.fromBase64(encoded.encode("ascii"))
            if data:
                window.restoreGeometry(data)
        except Exception:
            return


_STORE = WindowStateStore()


def save_geometry(window: QtWidgets.QWidget, key: str) -> None:
    _STORE.save_geometry(window, key)


def restore_geometry(window: QtWidgets.QWidget, key: str) -> None:
    _STORE.restore_geometry(window, key)
