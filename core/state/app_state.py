from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal


class AppState(QObject):
    currentScreenChanged = Signal()
    registrationRequiredChanged = Signal()
    statusChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._current_screen = "registration"
        self._registration_required = True
        self._status = "Готов"

    def get_current_screen(self) -> str:
        return self._current_screen

    def set_current_screen(self, value: str) -> None:
        if value == self._current_screen:
            return
        self._current_screen = value
        self.currentScreenChanged.emit()

    currentScreen = Property(
        str,
        get_current_screen,
        set_current_screen,
        notify=currentScreenChanged,
    )

    def get_registration_required(self) -> bool:
        return self._registration_required

    def set_registration_required(self, value: bool) -> None:
        if value == self._registration_required:
            return
        self._registration_required = value
        self.registrationRequiredChanged.emit()

    registrationRequired = Property(
        bool,
        get_registration_required,
        set_registration_required,
        notify=registrationRequiredChanged,
    )

    def get_status(self) -> str:
        return self._status

    def set_status(self, value: str) -> None:
        if value == self._status:
            return
        self._status = value
        self.statusChanged.emit()

    status = Property(str, get_status, set_status, notify=statusChanged)
