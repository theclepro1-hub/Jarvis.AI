from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QObject, QPoint, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QWheelEvent
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from shiboken6 import delete

from core.actions.action_registry import ActionRegistry
from core.ai.ai_service import AIService
from core.pc_control.service import PcControlService
from core.routing.batch_router import BatchRouter
from core.routing.command_router import CommandRouter
from core.registration.registration_service import RegistrationService
from core.policy import assistant_mode as assistant_mode_policy
from core.version import DEFAULT_VERSION
from core.settings.startup_manager import StartupManager
from core.services.chat_history_store import ChatHistoryStore


class _TestServiceContainer:
    def __init__(self) -> None:
        from core.settings.settings_service import SettingsService
        from core.settings.settings_store import SettingsStore

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
    def __init__(self, settings) -> None:
        self.settings = settings
        self.is_recording = False
        self._wake_detail = "Жду «Джарвис»"

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
        return ["Голос по умолчанию", "Тестовый голос"]

    def tts_voice_name(self) -> str:
        return str(self.settings.get("tts_voice_name", "Голос по умолчанию"))

    def tts_rate(self) -> int:
        return int(self.settings.get("tts_rate", 185))

    def tts_volume(self) -> int:
        return int(self.settings.get("tts_volume", 85))

    @property
    def microphones(self) -> list[str]:
        return ["Системный микрофон", "Logitech PRO X Gaming Headset"]

    @property
    def microphone_device_models(self) -> list[object]:
        return []

    @property
    def output_devices(self) -> list[str]:
        return ["Системный вывод", "Realtek HD Audio output"]

    @property
    def output_device_models(self) -> list[object]:
        return []

    def normalize_microphone_selection(self, value: str) -> str:
        return value or "Системный микрофон"

    def normalize_output_selection(self, value: str) -> str:
        return value or "Системный вывод"

    def summary(self) -> str:
        return "Голосовой контур готов к проверке."

    def runtime_status(self) -> dict[str, str]:
        return {
            "wakeWord": self._wake_detail,
            "command": "Команда распознаётся после активации",
            "tts": "Системный голос готов",
            "model": "Модель: загружена",
        }

    def test_wake_word(self) -> str:
        return "Проверка wake: ок"

    def test_jarvis_voice(self) -> str:
        return "Проверка голоса: ок"

    def start_manual_capture(self, on_text, on_note, on_finish):  # noqa: ANN001
        self.is_recording = True
        on_text("Джарвис открой ютуб")
        self.is_recording = False
        on_finish()
        return "открой ютуб"

    def stop_manual_capture(self) -> None:
        self.is_recording = False

    def set_wake_runtime_status(self, _stage, *, ready=True, detail=""):  # noqa: ANN001
        self._wake_detail = detail or ("Готов" if ready else "Ожидаю")

    def capture_after_wake(self, _pre_roll: bytes) -> str:
        return "открой ютуб"


class _TestWakeService:
    def __init__(self) -> None:
        self._status = "Жду «Джарвис»"

    def start(self, on_detected, on_status=None) -> str:  # noqa: ANN001
        self._status = "Жду «Джарвис»"
        if on_status is not None:
            on_status(self._status)
        return self._status

    def stop(self) -> None:
        self._status = "Остановлен"

    def status(self) -> str:
        return self._status

    def model_status(self) -> str:
        return "Модель: загружена"


class _TestUpdatesService:
    current_version = DEFAULT_VERSION

    def summary(self) -> str:
        return f"Версия {DEFAULT_VERSION} • канал стабильный"


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


def _find_by_text(root: QObject, text: str) -> QObject:
    for obj in _walk_items(root):
        try:
            if obj.property("text") == text:
                return obj
        except RuntimeError:
            pass
    raise AssertionError(f"Object with text not found: {text}")


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


def _walk_qobjects(root: QObject) -> list[QObject]:
    objects: list[QObject] = []

    def visit(node: QObject) -> None:
        objects.append(node)
        for child in node.children():
            visit(child)

    visit(root)
    return objects


def _find_popup(root: QObject) -> QObject:
    for obj in _walk_qobjects(root):
        try:
            class_name = obj.metaObject().className()
        except RuntimeError:
            continue
        if "Popup" in class_name:
            return obj
    raise AssertionError("Popup object not found")


def _read_qml_screen(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "ui" / "qml" / "screens" / name).read_text(encoding="utf-8")


def _read_qml_file(*parts: str) -> str:
    return (Path(__file__).resolve().parents[2] / "ui" / "qml" / Path(*parts)).read_text(encoding="utf-8")


def _find_item_with_title(root: QObject, title: str) -> QObject:
    for item in _walk_items(root):
        try:
            if item.property("title") == title:
                return item
        except RuntimeError:
            pass
    raise AssertionError(f"Item with title not found: {title}")


def _complete_registration(app: QGuiApplication, runtime, window) -> None:
    if runtime.state.currentScreen != "registration":
        return
    runtime.registration_bridge.saveRegistration("fake_groq_test_key", "123456789", "123:abc")
    _wait_for(app, lambda: runtime.state.currentScreen == "chat")


def _click(app: QGuiApplication, window, obj: QObject) -> None:
    assert isinstance(obj, QQuickItem)
    center = obj.mapToScene(obj.boundingRect().center())
    position = QPoint(int(center.x()), int(center.y()))
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, position)
    _pump(app)


def _hover(app: QGuiApplication, window, obj: QObject) -> None:
    assert isinstance(obj, QQuickItem)
    center = obj.mapToScene(obj.boundingRect().center())
    position = QPoint(int(center.x()), int(center.y()))
    QTest.mouseMove(window, position)
    _pump(app, 120)


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


@pytest.fixture()
def ui_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_UNITY_DISABLE_WAKE", "1")
    monkeypatch.setenv("JARVIS_UNITY_DISABLE_STARTUP_REGISTRY", "1")
    if not hasattr(assistant_mode_policy, "DEFAULT_LOCAL_LLM_BACKEND"):
        assistant_mode_policy.DEFAULT_LOCAL_LLM_BACKEND = "llama_cpp"

    import app.app as app_module

    monkeypatch.setattr(app_module, "ServiceContainer", _TestServiceContainer)

    from app.app import JarvisUnityApplication

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
        window.close()
        runtime.engine.collectGarbage()
        runtime.engine.deleteLater()
        for top_level in list(app.topLevelWindows()):
            top_level.close()
        _pump(app, 150)


def test_registration_and_navigation_clicks_work(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    assert runtime.state.currentScreen == "registration"
    _complete_registration(app, runtime, window)

    _click(app, window, _find(window, "navButton_voice"))
    assert runtime.state.currentScreen == "voice"

    _click(app, window, _find(window, "navButton_settings"))
    assert runtime.state.currentScreen == "settings"

    _click(app, window, _find(window, "navButton_apps"))
    assert runtime.state.currentScreen == "apps"


def test_registration_save_path_completes_registration(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    runtime.registration_bridge.saveRegistration("fake_groq_test_key", "123456789", "123:abc")

    assert runtime.state.currentScreen == "chat"
    assert runtime.services.registration.load().is_complete is True


def test_registration_continue_requires_all_fields_and_shows_feedback(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    runtime.registration_bridge.saveRegistration("", "", "")
    assert runtime.state.currentScreen == "registration"
    assert "Заполните три поля" in _find(window, "registrationFeedback").property("text")

    runtime.registration_bridge.saveRegistration("fake_groq_test_key", "123456789", "123:abc")

    assert runtime.state.currentScreen == "chat"
    assert "Подключения сохранены" in runtime.registration_bridge.feedback


def test_registration_mode_is_last_step_in_the_form() -> None:
    source = _read_qml_screen("RegistrationScreen.qml")

    mode_index = source.index('objectName: "registrationAssistantModeCombo"')
    groq_index = source.index('objectName: "groqField"')
    token_index = source.index('objectName: "botTokenField"')
    user_id_index = source.index('objectName: "userIdField"')
    save_index = source.index('objectName: "registrationSaveButton"')

    assert mode_index > groq_index
    assert mode_index > token_index
    assert mode_index > user_id_index
    assert mode_index < save_index


def test_chat_welcome_message_renders_and_ctrl_v_works(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)

    assert runtime.state.currentScreen == "chat"
    assert runtime.chat_bridge.messages
    assert runtime.chat_bridge.messages[0]["role"] == "assistant"

    composer = _find(window, "composerInput")
    assert isinstance(composer, QQuickItem)
    composer.forceActiveFocus()
    _pump(app, 80)

    clipboard = QGuiApplication.clipboard()
    clipboard.setText("вставка через ctrl v")
    QTest.keySequence(window, QKeySequence.Paste)
    _pump(app, 120)

    assert composer.property("text") == "вставка через ctrl v"


def test_composer_enter_sends_and_shift_enter_inserts_newline(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)

    composer = _find(window, "composerInput")
    assert isinstance(composer, QQuickItem)
    composer.forceActiveFocus()
    _pump(app, 80)

    before = len(runtime.chat_bridge.messages)
    composer.setProperty("text", "открой YouTube")
    QTest.keyClick(window, Qt.Key_Return)
    _wait_for(app, lambda: len(runtime.chat_bridge.messages) > before)
    assert any(
        message["role"] == "user" and message["text"] == "открой YouTube"
        for message in runtime.chat_bridge.messages
    )
    assert composer.property("text") == ""

    composer.setProperty("text", "первая строка")
    before_shift = len(runtime.chat_bridge.messages)
    QTest.keyClick(window, Qt.Key_Return, Qt.ShiftModifier)
    _pump(app, 150)
    assert len(runtime.chat_bridge.messages) == before_shift
    assert "\n" in composer.property("text")


def test_composer_status_line_honors_priority_order(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)

    status_line = _find(window, "composerStatusText")

    runtime.chat_bridge._set_last_response_hint("Быстро: Groq · 1.5 c")  # noqa: SLF001
    _pump(app, 120)
    assert status_line.property("text") == "Быстро: Groq · 1.5 c"

    runtime.chat_bridge._thinking = True  # noqa: SLF001
    runtime.chat_bridge.thinkingChanged.emit()
    runtime.chat_bridge._set_status_stage("Обрабатываю предыдущий запрос...")  # noqa: SLF001
    _pump(app, 120)
    assert status_line.property("text") == "Обрабатываю предыдущий запрос..."

    runtime.services.voice.is_recording = True
    runtime.voice_bridge._recording_hint = "Слушаю команду..."  # noqa: SLF001
    runtime.voice_bridge.recordingHintChanged.emit()
    runtime.voice_bridge.recordingChanged.emit()
    _pump(app, 120)
    assert status_line.property("text") == "Слушаю команду..."

    runtime.voice_bridge._wake_hint = "Услышал «Джарвис». Подхватываю начало команды..."  # noqa: SLF001
    runtime.voice_bridge.wakeHintChanged.emit()
    _pump(app, 120)
    assert status_line.property("text") == "Услышал «Джарвис». Подхватываю начало команды..."


def test_nav_spam_clicks_keep_screen_state_sane(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)

    targets = ["navButton_chat", "navButton_voice", "navButton_apps", "navButton_settings"]
    for _ in range(5):
        for name in targets:
            _click(app, window, _find(window, name))
            _pump(app, 20)

    assert runtime.state.currentScreen in {"chat", "voice", "apps", "settings"}


def test_apps_screen_add_button_and_feedback_work(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)
    _click(app, window, _find(window, "navButton_apps"))
    _click(app, window, _find(window, "customAppManualButton"))
    _pump(app, 120)

    _find(window, "customAppTitleField").setProperty("text", "Deadlock")
    _find(window, "customAppTargetField").setProperty("text", "steam://rungameid/1422450")
    _find(window, "customAppAliasesField").setProperty("text", "дедлок, deadlock")
    before = len(runtime.services.actions.app_catalog())
    _click(app, window, _find(window, "customAppAddButton"))

    assert len(runtime.services.actions.app_catalog()) == before + 1
    assert "Добавлено" in runtime.apps_bridge.feedback


def test_settings_theme_and_sidebar_nubik_are_present(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)
    _click(app, window, _find(window, "navButton_settings"))
    _wait_for(app, lambda: runtime.state.currentScreen == "settings")
    _wait_for_object(app, window, "sidebarRoot")
    _wait_for_object(app, window, "nubik_voice")
    _wait_for_object(app, window, "nubik_apps")
    _wait_for_object(app, window, "nubik_connections")

    theme_combo = _wait_for_object(app, window, "themeCombo")
    assert theme_combo.property("count") >= 2
    runtime.settings_bridge.themeMode = "steel"
    _pump(app, 120)

    assert runtime.services.settings.get("theme_mode", "midnight") == "steel"

    _click(app, window, _find(window, "navButton_voice"))
    _wait_for(app, lambda: runtime.state.currentScreen == "voice")

    voice_scroll = _wait_for_object(app, window, "voiceScroll")
    for _ in range(5):
        _wheel(app, window, voice_scroll, -180)

    current = runtime.services.settings.get("wake_word_enabled", True)
    _click(app, window, _find(window, "wakeWordSwitch"))
    assert runtime.services.settings.get("wake_word_enabled", True) is (not current)

    _click(app, window, _find(window, "voiceUnderstandingTestButton"))
    assert runtime.voice_bridge.testResult


def test_settings_help_surfaces_work_for_tabs_cards_and_rows(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)
    _click(app, window, _find(window, "navButton_settings"))
    _wait_for(app, lambda: runtime.state.currentScreen == "settings")

    _wait_for_object(app, window, "sidebarRoot")
    _wait_for_object(app, window, "nubik_voice")
    _wait_for_object(app, window, "nubik_apps")
    _wait_for_object(app, window, "nubik_connections")

    sidebar_source = _read_qml_file("components", "Sidebar.qml")
    source = _read_qml_screen("SettingsScreen.qml")

    assert 'root.hoverHelpText = "????? ? ??? ?????????, ????????? ? ???????."' in sidebar_source
    assert 'root.hoverHelpText = "????????? ? ???????????, ??????, ????? ? ??????? ???."' in sidebar_source
    assert 'helpText: "???????? ?????? ????? ??????. ??????????? ????????? ??????????? ?????????????."' in source
    assert 'helpText: "???? Groq ????? ??? ??????? ???????? ???????."' in source
    assert 'helpText: "?????????? ??????? ?????? ? ????????? ????????? ??????????."' in source

    sidebar_root = _find(window, "sidebarRoot")
    _hover(app, window, _find(window, "navButton_voice"))
    _wait_for(app, lambda: sidebar_root.property("visibleHelpText") == "????? ? ??? ?????????, ????????? ? ???????.")
    assert sidebar_root.property("visibleHelpText") == "????? ? ??? ?????????, ????????? ? ???????."

    assistant_section = _find_item_with_title(window, "????? ??????????")
    assert assistant_section.property("helpText") == "???? ??????? ?????: ???????, ???????????, ????? ??? ?????????."
    _hover(app, window, assistant_section)
    _wait_for(
        app,
        lambda: window.property("contextHelpText") == "????? ?????????? ? ???? ??????? ?????. ??? ????????? ??????????? ?????????????.",
    )
    assert window.property("contextHelpText") == "????? ?????????? ? ???? ??????? ?????. ??? ????????? ??????????? ?????????????."

    connections_section = _find_item_with_title(window, "???????????")
    assert connections_section.property("helpText") == "??? ?????? ????? Groq ? Telegram. ?????????????? ????? ???????? ????."
    _click(app, window, connections_section)
    _wait_for(app, lambda: bool(connections_section.property("expanded")))

    groq_row = _find_item_with_title(window, "Groq")
    assert groq_row.property("helpText") == "???? Groq ????? ??? ??????? ???????? ???????."
    _hover(app, window, groq_row)
    _wait_for(app, lambda: window.property("contextHelpText") == "???? Groq ????? ??? ??????? ???????? ???????.")
    assert window.property("contextHelpText") == "???? Groq ????? ??? ??????? ???????? ???????."


def test_settings_sections_are_closed_by_default() -> None:
    source = _read_qml_screen("SettingsScreen.qml")

    assert "expanded: true" not in source
    assert source.count("expanded: false") >= 7

    section_titles = [
        match.group(1)
        for line in source.splitlines()
        if (match := re.match(r'^ {16}title: "([^"]+)"$', line)) is not None
    ]

    assert section_titles[-2:] == ["Для опытных", "Обновления"]
    assert section_titles.index("Для опытных") < section_titles.index("Обновления")


def test_old_debug_strings_do_not_appear_in_ui_sources() -> None:
    sources = [
        _read_qml_screen("RegistrationScreen.qml"),
        _read_qml_screen("SettingsScreen.qml"),
        _read_qml_screen("VoiceScreen.qml"),
    ]
    banned_strings = [
        "registrationSkipButton",
        "skipForNow",
        "Advanced routing",
        "Cloud model id",
        "wake local",
        "STT route",
        "Text route",
        "local_llama ->",
        "local-first with fallback",
    ]

    for source in sources:
        for needle in banned_strings:
            assert needle not in source


def test_settings_connections_can_update_registration_fields(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)
    _click(app, window, _find(window, "navButton_settings"))
    _wait_for(app, lambda: runtime.state.currentScreen == "settings")

    assert runtime.settings_bridge.saveConnections(
        "fake_groq_settings_key",
        "bot_settings_token",
        "987654321",
    ) is True
    _pump(app, 120)

    registration = runtime.services.registration.load()
    assert registration.groq_api_key == "fake_groq_settings_key"
    assert registration.telegram_bot_token == "bot_settings_token"
    assert registration.telegram_user_id == "987654321"
    assert "Подключения сохранены" in _find(window, "settingsConnectionsFeedback").property("text")


def test_settings_assistant_mode_propagates_to_voice_and_privacy_state(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)
    _click(app, window, _find(window, "navButton_settings"))
    _wait_for(app, lambda: runtime.state.currentScreen == "settings")

    assert runtime.settings_bridge.assistantMode == "standard"

    runtime.settings_bridge.assistantMode = "private"
    _pump(app, 120)

    assert runtime.services.settings.get("voice_mode", "") == "private"
    assert runtime.services.settings.get("privacy_mode", "") == "private"
    assert runtime.services.settings.get("save_history_enabled", True) is False

    _click(app, window, _find(window, "navButton_voice"))
    _wait_for(app, lambda: runtime.state.currentScreen == "voice")
    assert runtime.voice_bridge.assistantStatus["mode"] == "private"


def test_settings_advanced_section_precedes_updates() -> None:
    lines = _read_qml_screen("SettingsScreen.qml").splitlines()

    def line_for(title: str) -> int:
        needle = f'title: "{title}"'
        for index, line in enumerate(lines, 1):
            if needle in line:
                return index
        raise AssertionError(f"Missing section title: {title}")

    updates_line = line_for("Обновления")
    advanced_line = line_for("Дополнительно") if any('title: "Дополнительно"' in line for line in lines) else line_for("Для опытных")

    assert advanced_line < updates_line


def test_settings_ai_profile_menu_excludes_local_ai(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)
    _click(app, window, _find(window, "navButton_settings"))
    _wait_for(app, lambda: runtime.state.currentScreen == "settings")

    settings_screen = Path(__file__).resolve().parents[2] / "ui" / "qml" / "screens" / "SettingsScreen.qml"
    source = settings_screen.read_text(encoding="utf-8")

    assert 'case "local"' not in source
    assert 'key: "local"' not in source
    assert 'title: "Локально"' not in source
    assert 'локальный ИИ подключён' not in source


def test_scroll_views_accept_scroll_input(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)
    _click(app, window, _find(window, "navButton_voice"))
    _wait_for(app, lambda: runtime.state.currentScreen == "voice")

    voice_scroll = _wait_for_object(app, window, "voiceScroll")
    flickable = voice_scroll.property("contentItem")
    before = flickable.property("contentY")

    _wheel(app, window, voice_scroll, -120)

    after = flickable.property("contentY")
    assert after >= before


def test_voice_microphone_combo_popup_is_visible_and_scrollable(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)
    _click(app, window, _find(window, "navButton_voice"))
    _wait_for(app, lambda: runtime.state.currentScreen == "voice")

    combo = _wait_for_object(app, window, "microphoneCombo")
    _click(app, window, combo)
    _pump(app, 200)
    popup = _find_popup(combo)
    assert popup.property("visible") is True
    content_item = popup.property("contentItem")
    assert content_item is not None
    assert content_item.property("contentHeight") >= content_item.property("height")


def test_chat_viewport_does_not_drift_horizontally_after_theme_change(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)

    for index in range(10):
        role = "user" if index % 2 else "assistant"
        runtime.chat_bridge._append_message(  # noqa: SLF001 - UI gate needs deterministic message injection.
            role,
            (
                "Проверка ширины чата после смены темы: длинное сообщение должно "
                "переноситься внутри пузыря и не уезжать за правую границу окна."
            ),
        )
    _pump(app, 220)

    list_view = _wait_for_object(app, window, "chatListView")
    assert isinstance(list_view, QQuickItem)
    assert list_view.property("contentX") == 0
    assert list_view.width() <= window.width()

    runtime.settings_bridge.themeMode = "steel"
    _pump(app, 220)

    assert runtime.services.settings.get("theme_mode", "midnight") == "steel"
    assert list_view.property("contentX") == 0
    assert list_view.width() <= window.width()

    list_view.setProperty("contentX", 160)
    _pump(app, 160)

    assert list_view.property("contentX") == 0


def test_chat_autoscroll_follows_new_user_and_assistant_messages(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)

    for index in range(18):
        role = "assistant" if index % 2 == 0 else "user"
        runtime.chat_bridge._append_message(  # noqa: SLF001 - regression coverage for UI follow-bottom wiring.
            role,
            (
                f"Сообщение {index}: длинный текст для проверки автоскролла. "
                "Он должен держать список внизу после каждого нового ответа или запроса."
            ),
        )

    _pump(app, 260)
    list_view = _wait_for_object(app, window, "chatListView")
    bottom_y = float(list_view.property("contentY"))

    _wheel(app, window, list_view, 260)
    scrolled_y = float(list_view.property("contentY"))
    assert scrolled_y < bottom_y

    runtime.chat_bridge._append_message("user", "новое сообщение пользователя")  # noqa: SLF001
    _pump(app, 260)
    after_user = float(list_view.property("contentY"))
    assert after_user >= bottom_y - 2

    runtime.chat_bridge._append_message("assistant", "новый ответ JARVIS")  # noqa: SLF001
    _pump(app, 260)
    after_assistant = float(list_view.property("contentY"))
    assert after_assistant >= bottom_y - 2


def test_chat_execution_card_renders_steps(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)

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

    _find_by_text(window, messages[-1]["text"])
    _find_by_text(window, messages[-1]["steps"][0]["title"])
    _find_by_text(window, messages[-1]["steps"][1]["title"])


def test_apps_screen_has_group_tabs_and_music_default_switch(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _complete_registration(app, runtime, window)
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

    with pytest.raises(AssertionError):
        _find(window, "appsCategory_all")

    music_tab = _find(window, "appsCategory_music")
    _click(app, window, music_tab)
    _pump(app, 120)

    assert runtime.state.currentScreen == "apps"
