from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Property, Signal, Slot


class AppsBridge(QObject):
    catalogChanged = Signal()
    feedbackChanged = Signal()
    discoveredChanged = Signal()
    scanResultChanged = Signal()
    defaultMusicAppChanged = Signal()
    pinnedCommandsChanged = Signal()
    scanBusyChanged = Signal()
    _scanFinished = Signal(object)
    _scanFailed = Signal(str)

    def __init__(self, services, chat_bridge) -> None:
        super().__init__()
        self.services = services
        self.chat_bridge = chat_bridge
        self._feedback = ""
        self._discovered: list[dict[str, str]] = []
        self._scan_result: dict[str, object] = {}
        self._scan_busy = False
        self._scan_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="apps-scan")
        self._scanFinished.connect(self._apply_scan_result)
        self._scanFailed.connect(self._apply_scan_failure)

    @Property("QVariantList", notify=catalogChanged)
    def catalog(self) -> list[dict[str, str]]:
        return self.services.actions.app_catalog()

    @Property("QVariantList", notify=discoveredChanged)
    def discovered(self) -> list[dict[str, str]]:
        return self._discovered

    @Property("QVariantMap", notify=scanResultChanged)
    def scanResult(self) -> dict[str, object]:
        return self._scan_result

    @Property(bool, notify=scanBusyChanged)
    def scanBusy(self) -> bool:
        return self._scan_busy

    @Property(str, notify=feedbackChanged)
    def feedback(self) -> str:
        return self._feedback

    @Property(str, notify=defaultMusicAppChanged)
    def defaultMusicAppId(self) -> str:
        return str(self.services.settings.get("default_music_app", "")).strip()

    @Slot()
    def prewarm(self) -> None:
        try:
            self.services.actions.app_catalog()
        except Exception:
            return
        try:
            self.services.actions.pinned_commands()
        except Exception:
            pass

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

    @Slot(str, str, str, str)
    def updateCustomApp(self, app_id: str, title: str, target: str, aliases: str) -> None:
        if not title.strip() or not target.strip():
            self._feedback = "Нужны хотя бы название и цель запуска."
            self.feedbackChanged.emit()
            return
        if not self.services.actions.update_custom_app(app_id, title, target, aliases):
            self._feedback = "Не удалось изменить приложение."
            self.feedbackChanged.emit()
            return
        self._feedback = f"Изменено: {title.strip()}"
        self.feedbackChanged.emit()
        self.catalogChanged.emit()
        self.chat_bridge.refreshCatalog()

    @Slot(str)
    def removeCustomApp(self, app_id: str) -> None:
        self.services.actions.remove_custom_app(app_id)
        self._feedback = "Пользовательское приложение удалено."
        self.feedbackChanged.emit()
        self.catalogChanged.emit()
        self.chat_bridge.refreshCatalog()

    @Slot(str)
    def launchApp(self, app_id: str) -> None:
        outcome = self.services.actions.test_item(app_id)
        self._feedback = outcome.title if outcome.success else outcome.detail
        self.feedbackChanged.emit()

    @Slot()
    def scanApplications(self) -> None:
        if self._scan_busy:
            return
        self._set_scan_busy(True)
        self._feedback = "Ищу приложения и ярлыки. Это может занять несколько секунд."
        self.feedbackChanged.emit()

        def worker() -> None:
            try:
                result = self.services.actions.scan_and_import_apps()
            except Exception as exc:  # noqa: BLE001
                self._scanFailed.emit(type(exc).__name__)
                return
            self._scanFinished.emit(dict(result))

        self._scan_pool.submit(worker)

    @Slot(str)
    def importDiscoveredApp(self, candidate_id: str) -> None:
        candidate = next((item for item in self._discovered if item.get("id") == candidate_id), None)
        if not candidate:
            self._feedback = "Кандидат не найден. Запустите поиск ещё раз."
            self.feedbackChanged.emit()
            return
        if not self.services.actions.import_discovered_app(candidate):
            self._feedback = "Это приложение уже добавлено или найденный путь пустой."
            self.feedbackChanged.emit()
            return
        self._discovered = [item for item in self._discovered if item.get("id") != candidate_id]
        self._feedback = f"Добавлено: {candidate.get('title', 'приложение')}"
        self.feedbackChanged.emit()
        self.discoveredChanged.emit()
        self.catalogChanged.emit()
        self.chat_bridge.refreshCatalog()

    @Slot(str)
    def setDefaultMusicApp(self, app_id: str) -> None:
        if not self.services.actions.set_default_music_app(app_id):
            self._feedback = "Выберите приложение из категории музыки."
            self.feedbackChanged.emit()
            return
        self._feedback = "Основное музыкальное приложение сохранено."
        self.feedbackChanged.emit()
        self.defaultMusicAppChanged.emit()
        self.catalogChanged.emit()
        self.chat_bridge.refreshCatalog()

    @Slot(str)
    def togglePinnedCommand(self, app_id: str) -> None:
        item_id = str(app_id or "").strip()
        if not item_id:
            return
        catalog = self.services.actions.app_catalog()
        current = next((item for item in catalog if str(item.get("id", "")) == item_id), None)
        if current is None:
            self._feedback = "Команда не найдена."
            self.feedbackChanged.emit()
            return
        if bool(current.get("isPinned", False)):
            self.services.actions.unpin_command(item_id)
            self._feedback = f"Откреплено: {current.get('title', item_id)}"
        else:
            self.services.actions.pin_command(item_id)
            self._feedback = f"Закреплено: {current.get('title', item_id)}"
        self.feedbackChanged.emit()
        self.pinnedCommandsChanged.emit()
        self.catalogChanged.emit()
        self.chat_bridge.refreshCatalog()

    @Slot(str, result=str)
    def targetFromFileUrl(self, file_url: str) -> str:
        from core.actions.launcher_discovery import target_from_file_url

        return target_from_file_url(file_url)

    def _set_scan_busy(self, value: bool) -> None:
        busy = bool(value)
        if self._scan_busy == busy:
            return
        self._scan_busy = busy
        self.scanBusyChanged.emit()

    @Slot(object)
    def _apply_scan_result(self, result: object) -> None:
        payload = dict(result) if isinstance(result, dict) else {}
        review = payload.get("review", [])
        self._discovered = review if isinstance(review, list) else []
        self._scan_result = payload
        self._feedback = str(payload.get("summary") or "Новых безопасных приложений не найдено.")
        self._set_scan_busy(False)
        self.feedbackChanged.emit()
        self.discoveredChanged.emit()
        self.scanResultChanged.emit()
        self.catalogChanged.emit()
        self.chat_bridge.refreshCatalog()

    @Slot(str)
    def _apply_scan_failure(self, error_name: str) -> None:
        self._set_scan_busy(False)
        self._feedback = f"Не удалось обновить список приложений: {error_name}"
        self.feedbackChanged.emit()
