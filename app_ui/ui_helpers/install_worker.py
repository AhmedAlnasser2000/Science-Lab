from typing import Any, Callable

from PyQt6 import QtCore


class InstallWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(object)
    error = QtCore.pyqtSignal(str)

    def __init__(self, func_or_adapter: Any, part_id: str):
        super().__init__()
        self._adapter = func_or_adapter
        self._part_id = part_id

    @QtCore.pyqtSlot()
    def run(self):
        try:
            result = self._adapter.download_part(self._part_id)
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - defensive
            self.error.emit(str(exc))
