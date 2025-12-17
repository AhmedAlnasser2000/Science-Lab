from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Iterable, Optional, Protocol

from PyQt6 import QtWidgets


class LabWidget(Protocol):
    def load_part(self, part_id: str, manifest: dict, detail: dict) -> None:  # pragma: no cover - interface
        ...

    def set_profile(self, profile: str) -> None:  # pragma: no cover - interface
        ...

    def stop_simulation(self) -> None:  # pragma: no cover - interface
        ...

    def set_reduced_motion(self, value: bool) -> None:  # pragma: no cover - interface
        ...


class LabPlugin(ABC):
    id: str
    title: str

    def supports_profiles(self) -> Iterable[str]:
        return ("Learner", "Educator", "Explorer")

    def get_export_actions(self, context: dict) -> Iterable[dict]:
        """Optional export actions. Default: none."""
        return ()

    def get_telemetry_snapshot(self, context: dict) -> Optional[dict]:
        """Optional telemetry snapshot. Default: no telemetry."""
        return None

    @abstractmethod
    def create_widget(
        self,
        on_exit: Callable[[], None],
        get_profile: Callable[[], str],
    ) -> LabWidget | QtWidgets.QWidget:
        ...
