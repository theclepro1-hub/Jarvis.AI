from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot


class AppsBridge(QObject):
    catalogChanged = Signal()
    feedbackChanged = Signal()

    def __init__(self, services, chat_bridge) -> None:
        super().__init__()
        self.services = services
        self.chat_bridge = chat_bridge
        self._feedback = ""

    @Property("QVariantList", notify=catalogChanged)
    def catalog(self) -> list[dict[str, str]]:
        return self.services.actions.app_catalog()

    @Property(str, notify=feedbackChanged)
    def feedback(self) -> str:
        return self._feedback

    @Slot(str, str, str)
    def addCustomApp(self, title: str, target: str, aliases: str) -> None:
        if not title.strip() or not target.strip():
            self._feedback = "Нужны хотя бы название и цель запуска."
            self.feedbackChanged.emit()
            return
        self.services.actions.add_custom_app(title, target, aliases)
        self._feedback = f"Добавлено: {title.strip()}"
        self.feedbackChanged.emit()
        self.catalogChanged.emit()
        self.chat_bridge.refreshCatalog()

    @Slot(str)
    def removeCustomApp(self, app_id: str) -> None:
        self.services.actions.remove_custom_app(app_id)
        self._feedback = "Кастомное приложение удалено."
        self.feedbackChanged.emit()
        self.catalogChanged.emit()
        self.chat_bridge.refreshCatalog()
