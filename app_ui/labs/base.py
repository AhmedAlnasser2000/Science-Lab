from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Iterable, Protocol

from PyQt6 import QtWidgets


class LabWidget(Protocol):
    def load_part(self, part_id: str, manifest: dict, detail: dict) -> None:  # pragma: no cover - interface
        ...

    def set_profile(self, profile: str) -> None:  # pragma: no cover - interface
        ...

    def stop_simulation(self) -> None:  # pragma: no cover - interface
        ...


class LabPlugin(ABC):
    id: str
    title: str

    def supports_profiles(self) -> Iterable[str]:
        return ("Learner", "Educator", "Explorer")

    @abstractmethod
    def create_widget(
        self,
        on_exit: Callable[[], None],
        get_profile: Callable[[], str],
    ) -> LabWidget | QtWidgets.QWidget:
        ...
