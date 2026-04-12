from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QObject, QPoint, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QWheelEvent
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from shiboken6 import delete

from app.app import JarvisUnityApplication
from core.actions.action_registry import ActionRegistry
from core.ai.ai_service import AIService
from core.pc_control.service import PcControlService
from core.registration.registration_service import RegistrationService
from core.routing.batch_router import BatchRouter
from core.routing.command_router import CommandRouter
from core.services.chat_history_store import ChatHistoryStore
from core.settings.settings_service import SettingsService
from core.settings.settings_store import SettingsStore
from core.settings.startup_manager import StartupManager
from core.version import DEFAULT_VERSION


class _TestServiceContainer:
    def __init__(self) -> None:
        self.settings_store = SettingsStore()
        self.chat_history = ChatHistoryStore()
        self.settings = SettingsService(self.settings_store)
        self.startup = StartupManager()
        self.settings.set("startup_enabled", self.startup.is_enabled())
        self.registration = RegistrationService(self.settings)
        self.ai = AIService(self.settings)
        self.actions = ActionRegistry(self.settings)
        self.batch_router = BatchRouter(self.actions)
        self.pc_control = PcControlService(self.actions)
        self.command_router = CommandRouter(self.actions, self.batch_router, self.ai, self.pc_control)
        self.voice = _TestVoiceService(self.settings)
        self.stt = _TestSttService()
        self.wake = _TestWakeService()
        self.updates = _TestUpdatesService()


class _TestSttService:
    def can_transcribe(self) -> bool:
        return False


class _TestVoiceService:
    def __init__(self, settings: SettingsService) -> None:
        self.settings = settings
        self.is_recording = False
        self._wake_detail = "Жду активации"

    def voice_response_enabled(self) -> bool:
        return bool(self.settings.get("voice_response_enabled", False))

    def tts_engine(self) -> str:
        return str(self.settings.get("tts_engine", "system"))

    def available_tts_engines(self) -> list[dict[str, object]]:
        return [
            {"key": "system", "title": "Системный"},
            {"key": "edge", "title": "Edge"},
        ]

    def can_route_tts_output(self) -> bool:
        return True

    def available_tts_voices(self) -> list[str]:
        return ["Выбран системный голос", "Microsoft Irina Desktop"]

    def tts_voice_name(self) -> str:
        return str(self.settings.get("tts_voice_name", "Выбран системный голос"))

    def tts_rate(self) -> int:
        return int(self.settings.get("tts_rate", 185))

    def tts_volume(self) -> int:
        return int(self.settings.get("tts_volume", 85))

    @property
    def microphones(self) -> list[str]:
        return ["Системный микрофон", "Logitech PRO X Gaming Headset"]

    @property
    def microphone_device_models(self) -> list[object]:
        return [
            _TestDevice("Системный микрофон"),
            _TestDevice("Logitech PRO X Gaming Headset"),
        ]

    @property
    def output_devices(self) -> list[str]:
        return ["Системный вывод", "Realtek HD Audio output"]

    @property
    def output_device_models(self) -> list[object]:
        return [
            _TestDevice("Системный вывод"),
            _TestDevice("Realtek HD Audio output"),
        ]

    def normalize_microphone_selection(self, value: str) -> str:
        return value or "Системный микрофон"

    def normalize_output_selection(self, value: str) -> str:
        return value or "Системный вывод"

    def summary(self) -> str:
        return "Голосовой слой готов к проверке."

    def runtime_status(self) -> dict[str, str]:
        return {
            "wakeWord": self._wake_detail,
            "command": "Распознавание готово",
            "tts": "Системный голос готов",
            "model": "Локально: готово",
        }

    def test_wake_word(self) -> str:
        return "Проверка wake: ок"

    def test_jarvis_voice(self) -> str:
        return "Проверка голоса: ок"

    def start_manual_capture(self, on_text, on_note, on_finish):  # noqa: ANN001
        self.is_recording = True
        on_text("открой музыку")
        self.is_recording = False
        on_finish()
        return "Слушаю фразу"

    def stop_manual_capture(self) -> None:
        self.is_recording = False

    def set_wake_runtime_status(self, _stage, *, ready=True, detail=""):  # noqa: ANN001
        self._wake_detail = detail or ("Готово" if ready else "Занят")

    def capture_after_wake(self, _pre_roll: bytes) -> str:
        return "открой музыку"

    def latest_wake_metrics(self) -> dict[str, object]:
        return {}

    def latest_wake_metrics_summary(self) -> str:
        return ""


class _TestWakeService:
    def __init__(self) -> None:
        self._status = "Жду активации"

    def start(self, _on_detected, on_status=None) -> str:  # noqa: ANN001
        self._status = "Жду активации"
        if on_status is not None:
            on_status()
        return self._status

    def stop(self) -> None:
        self._status = "Остановлено"

    def status(self) -> str:
        return self._status

    def model_status(self) -> str:
        return "Модель: готова"


class _TestUpdatesService:
    current_version = DEFAULT_VERSION

    def summary(self) -> str:
        return f"Версия {DEFAULT_VERSION} · канал стабильный"


class _TestDevice:
    def __init__(self, name: str) -> None:
        self.name = name

    def as_qml(self) -> dict[str, str | int | bool]:
        return {"name": self.name}


def _pump(app: QGuiApplication, ms: int = 80) -> None:
    app.processEvents()
    QTest.qWait(ms)
    app.processEvents()


def _wait_for(app: QGuiApplication, predicate, timeout_ms: int = 1500) -> None:
    remaining = timeout_ms
    while remaining > 0:
        if predicate():
            return
        _pump(app, 50)
        remaining -= 50
    raise AssertionError("Timed out waiting for UI condition")


def _wait_for_object(app: QGuiApplication, root: QObject, name: str, timeout_ms: int = 3000) -> QObject:
    found: dict[str, QObject | None] = {"obj": None}

    def predicate() -> bool:
        obj = root.findChild(QObject, name)
        if obj is None:
            for item in _walk_items(root):
                if item.objectName() == name:
                    obj = item
                    break
        found["obj"] = obj
        return obj is not None

    _wait_for(app, predicate, timeout_ms)
    assert found["obj"] is not None
    return found["obj"]


def _find(root: QObject, name: str) -> QObject:
    obj = root.findChild(QObject, name)
    if obj is not None:
        return obj
    for item in _walk_items(root):
        if item.objectName() == name:
            return item
    raise AssertionError(f"Object not found: {name}")


def _walk_items(root: QObject) -> list[QQuickItem]:
    items: list[QQuickItem] = []

    def visit(node: QObject) -> None:
        if isinstance(node, QQuickItem):
            items.append(node)
            for child in node.childItems():
                visit(child)

    content_item = getattr(root, "contentItem", None)
    if callable(content_item):
        root_item = content_item()
        if root_item is not None:
            visit(root_item)
            return items

    visit(root)
    return items


def _find_popup(root: QObject) -> QObject:
    for obj in _walk_items(root):
        try:
            class_name = obj.metaObject().className()
        except RuntimeError:
            continue
        if "Popup" in class_name:
            return obj
    raise AssertionError("Popup object not found")


def _click(app: QGuiApplication, window, obj: QObject) -> None:
    assert isinstance(obj, QQuickItem)
    center = obj.mapToScene(obj.boundingRect().center())
    position = QPoint(int(center.x()), int(center.y()))
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, position)
    _pump(app)


def _wheel(app: QGuiApplication, window, obj: QObject, delta_y: int) -> None:
    assert isinstance(obj, QQuickItem)
    center = obj.mapToScene(obj.boundingRect().center())
    pos = QPoint(int(center.x()), int(center.y()))
    wheel = QWheelEvent(
        center,
        window.mapToGlobal(pos),
        QPoint(0, 0),
        QPoint(0, delta_y),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.ScrollUpdate,
        False,
    )
    QGuiApplication.sendEvent(window, wheel)
    _pump(app, 120)


def _complete_registration(
    runtime,
    app: QGuiApplication,
    window,
    groq_key: str = "fake_groq_test_key",
    telegram_id: str = "123456789",
    bot_token: str = "123:abc",
) -> None:
    _find(window, "groqField").setProperty("text", groq_key)
    _find(window, "userIdField").setProperty("text", telegram_id)
    _find(window, "botTokenField").setProperty("text", bot_token)
    runtime.registration_bridge.saveRegistration(groq_key, telegram_id, bot_token)
    _pump(app, 120)


@pytest.fixture()
def ui_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_UNITY_DISABLE_WAKE", "1")
    monkeypatch.setenv("JARVIS_UNITY_DISABLE_STARTUP_REGISTRY", "1")
    monkeypatch.setattr("app.app.ServiceContainer", _TestServiceContainer)

    existing = QCoreApplication.instance()
    if existing is not None and not isinstance(existing, QGuiApplication):
        existing.quit()
        delete(existing)
    app = QGuiApplication.instance() or QGuiApplication([])
    for top_level in list(app.topLevelWindows()):
        top_level.close()
    _pump(app, 80)
    runtime = JarvisUnityApplication(app)
    runtime.start()
    window = runtime.engine.rootObjects()[0]
    window.setWidth(1260)
    window.setHeight(720)
    _pump(app, 120)
    _wait_for_object(app, window, "screenLoader")
    _wait_for_object(app, window, "registrationSaveButton")

    try:
        yield app, runtime, window
    finally:
        runtime.voice_bridge.shutdown()
        runtime.settings_bridge.shutdown()
        window.close()
        runtime.engine.collectGarbage()
        runtime.engine.deleteLater()
        for top_level in list(app.topLevelWindows()):
            top_level.close()
        _pump(app, 150)


def test_registration_requires_all_fields_and_save_path_works(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    runtime.registration_bridge.saveRegistration("", "", "")
    _pump(app, 120)
    assert runtime.state.currentScreen == "registration"
    assert "Нужны три поля" in _find(window, "registrationFeedback").property("text")

    assert _find(window, "registrationSaveButton") is not None

    _complete_registration(runtime, app, window)
    _wait_for(app, lambda: runtime.state.currentScreen == "chat")
    assert runtime.services.registration.load().is_complete is True
    assert "Подключение сохранено" in runtime.registration_bridge.feedback


def test_private_registration_can_continue_without_groq(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    runtime.settings_bridge.assistantMode = "private"
    _pump(app, 120)

    groq_field = _find(window, "groqField")
    assert groq_field.property("visible") is False

    runtime.registration_bridge.saveRegistration("", "123456789", "123:abc")
    _pump(app, 120)

    _wait_for(app, lambda: runtime.state.currentScreen == "chat")
    assert runtime.services.registration.is_complete(runtime.services.registration.load()) is True
    assert "Подключение сохранено" in runtime.registration_bridge.feedback


def test_navigation_after_registration(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(runtime, app, window)
    _wait_for(app, lambda: runtime.state.currentScreen == "chat")

    _click(app, window, _find(window, "navButton_voice"))
    assert runtime.state.currentScreen == "voice"

    _click(app, window, _find(window, "navButton_settings"))
    assert runtime.state.currentScreen == "settings"

    _click(app, window, _find(window, "navButton_apps"))
    assert runtime.state.currentScreen == "apps"


def test_chat_welcome_message_and_paste_work(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(runtime, app, window)
    _wait_for(app, lambda: runtime.state.currentScreen == "chat")
    assert runtime.chat_bridge.messages[0]["role"] == "assistant"

    composer = _find(window, "composerInput")
    assert isinstance(composer, QQuickItem)
    composer.forceActiveFocus()
    _pump(app, 80)

    clipboard = QGuiApplication.clipboard()
    clipboard.setText("проверка буфера ctrl v")
    QTest.keySequence(window, QKeySequence.Paste)
    _pump(app, 120)

    assert composer.property("text") == "проверка буфера ctrl v"


def test_voice_controls_and_result_work(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(runtime, app, window)
    _click(app, window, _find(window, "navButton_voice"))
    _wait_for(app, lambda: runtime.state.currentScreen == "voice")

    voice_scroll = _wait_for_object(app, window, "voiceScroll")
    for _ in range(4):
        _wheel(app, window, voice_scroll, -180)

    current = runtime.services.settings.get("wake_word_enabled", True)
    runtime.voice_bridge.setWakeWordEnabled(not current)
    _pump(app, 120)
    assert runtime.services.settings.get("wake_word_enabled", True) is (not current)

    _click(app, window, _find(window, "voiceUnderstandingTestButton"))
    assert _find(window, "voiceTestResult").property("text")


def test_apps_screen_add_button_and_feedback_work(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(runtime, app, window)
    _click(app, window, _find(window, "navButton_apps"))
    _click(app, window, _find(window, "customAppManualButton"))
    _pump(app, 120)

    _find(window, "customAppTitleField").setProperty("text", "Deadlock")
    _find(window, "customAppTargetField").setProperty("text", "steam://rungameid/1422450")
    _find(window, "customAppAliasesField").setProperty("text", "дедлок, deadlock")
    before = len(runtime.services.actions.app_catalog())
    _click(app, window, _find(window, "customAppAddButton"))

    assert len(runtime.services.actions.app_catalog()) == before + 1
    assert runtime.apps_bridge.feedback


def test_settings_theme_and_nubik_are_present(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(runtime, app, window)
    _click(app, window, _find(window, "navButton_settings"))
    _wait_for(app, lambda: runtime.state.currentScreen == "settings")
    _wait_for_object(app, window, "sidebarNubikImage")

    theme_combo = _wait_for_object(app, window, "themeCombo")
    assert theme_combo.property("count") >= 2
    runtime.settings_bridge.themeMode = "steel"
    _pump(app, 120)

    assert runtime.services.settings.get("theme_mode", "midnight") == "steel"


def test_settings_connections_can_update_registration_fields(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(runtime, app, window)
    _click(app, window, _find(window, "navButton_settings"))
    _wait_for(app, lambda: runtime.state.currentScreen == "settings")

    assert runtime.settings_bridge.saveConnections(
        "fake_groq_settings_key",
        runtime.settings_bridge.cerebrasApiKey,
        runtime.settings_bridge.geminiApiKey,
        runtime.settings_bridge.openrouterApiKey,
        "bot_settings_token",
        "987654321",
    ) is True
    _pump(app, 120)

    registration = runtime.services.registration.load()
    assert registration.groq_api_key == "fake_groq_settings_key"
    assert registration.telegram_bot_token == "bot_settings_token"
    assert registration.telegram_user_id == "987654321"
    assert "Подключения сохранены" in _find(window, "settingsConnectionsFeedback").property("text")


def test_settings_sections_start_collapsed_and_updates_last(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(runtime, app, window)
    _click(app, window, _find(window, "navButton_settings"))
    _wait_for(app, lambda: runtime.state.currentScreen == "settings")

    settings_screen = Path(__file__).resolve().parents[2] / "ui" / "qml" / "screens" / "SettingsScreen.qml"
    registration_screen = Path(__file__).resolve().parents[2] / "ui" / "qml" / "screens" / "RegistrationScreen.qml"
    source = settings_screen.read_text(encoding="utf-8")
    registration_source = registration_screen.read_text(encoding="utf-8")

    for section_name in [
        'objectName: "settingsSection_connections"',
        'objectName: "settingsSection_assistantMode"',
        'objectName: "settingsSection_voiceSystem"',
        'objectName: "settingsSection_historyData"',
        'objectName: "settingsSection_theme"',
        'objectName: "settingsSection_updates"',
        'objectName: "settingsSection_advanced"',
    ]:
        assert section_name in source

    assert source.count("expanded: false") >= 7
    assert source.index('title: "Обновления"') > source.index('title: "Внешний вид"')
    assert source.index('title: "Для опытных"') < source.index('title: "Обновления"')
    assert 'registrationSkipButton' not in registration_source
    assert "Advanced routing" not in source
    assert "Cloud model id" not in source
    assert "Text route" not in source
    assert "STT route" not in source
    assert "wake local" not in source
    assert "local_llama ->" not in source


def test_apps_screen_has_group_tabs_and_music_default_switch(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(runtime, app, window)
    _click(app, window, _find(window, "navButton_apps"))
    _wait_for(app, lambda: runtime.state.currentScreen == "apps")

    for tab_name in [
        "appsCategory_music",
        "appsCategory_steam",
        "appsCategory_launcher",
        "appsCategory_web",
        "appsCategory_app",
    ]:
        assert _find(window, tab_name) is not None

    music_tab = _find(window, "appsCategory_music")
    _click(app, window, music_tab)
    _pump(app, 120)

    assert runtime.state.currentScreen == "apps"


def test_chat_execution_card_renders_steps_and_clear_works(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(runtime, app, window)
    _wait_for(app, lambda: runtime.state.currentScreen == "chat")

    runtime.chat_bridge.appendExecutionResult(
        "Выполняю 2 действия: Музыка, YouTube",
        [
            {"title": "Музыка", "status": "готово"},
            {"title": "YouTube", "status": "в очереди"},
        ],
    )
    _pump(app, 300)

    messages = runtime.chat_bridge.messages
    assert messages[-1]["type"] == "execution"
    assert messages[-1]["steps"][0]["title"] == "Музыка"
    assert messages[-1]["steps"][1]["status"] == "в очереди"

    _click(app, window, _find(window, "clearChatButton"))
    _pump(app, 160)

    assert len(runtime.chat_bridge.messages) == 1
    assert runtime.chat_bridge.messages[0]["role"] == "assistant"


def test_voice_microphone_combo_has_items(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(runtime, app, window)
    _click(app, window, _find(window, "navButton_voice"))
    _wait_for(app, lambda: runtime.state.currentScreen == "voice")

    combo = _wait_for_object(app, window, "microphoneCombo")
    assert combo.property("count") >= 1
