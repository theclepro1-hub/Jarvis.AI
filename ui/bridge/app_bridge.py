from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot

from core.version import DEFAULT_VERSION


class AppBridge(QObject):
    currentScreenChanged = Signal()
    navigationItemsChanged = Signal()
    statusChanged = Signal()
    registrationRequiredChanged = Signal()

    def __init__(self, state, services) -> None:
        super().__init__()
        self.state = state
        self.services = services
        self._navigation_items = [
            {"id": "chat", "title": "Чат"},
            {"id": "voice", "title": "Голос"},
            {"id": "apps", "title": "Приложения"},
            {"id": "settings", "title": "Настройки"},
        ]
        registration = self.services.registration.load()
        if registration.is_complete or registration.skipped:
            self.state.registrationRequired = False
            self.state.currentScreen = "chat"
        else:
            self.state.registrationRequired = True
            self.state.currentScreen = "registration"

        self.state.currentScreenChanged.connect(self.currentScreenChanged.emit)
        self.state.statusChanged.connect(self.statusChanged.emit)
        self.state.registrationRequiredChanged.connect(self.registrationRequiredChanged.emit)
        self._version = DEFAULT_VERSION

    @Property(str, notify=currentScreenChanged)
    def currentScreen(self) -> str:
        return self.state.currentScreen

    @Property("QVariantList", notify=navigationItemsChanged)
    def navigationItems(self) -> list[dict[str, str]]:
        return self._navigation_items

    @Property(str, constant=True)
    def version(self) -> str:
        return self._version

    @Property(str, notify=statusChanged)
    def assistantStatus(self) -> str:
        return self.state.status

    @Property(bool, notify=registrationRequiredChanged)
    def registrationRequired(self) -> bool:
        return self.state.registrationRequired

    @Slot(str)
    def navigate(self, screen: str) -> None:
        if self.state.registrationRequired and screen not in {"registration", "settings"}:
            return
        self.state.currentScreen = screen

    @Slot()
    def openSettings(self) -> None:
        self.navigate("settings")

    @Slot()
    def finishRegistration(self) -> None:
        self.state.registrationRequired = False
        self.state.currentScreen = "chat"

    @Slot()
    def restartRegistration(self) -> None:
        self.state.registrationRequired = True
        self.state.currentScreen = "registration"
