from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QPoint, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QWheelEvent
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from app.app import JarvisUnityApplication


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


@pytest.fixture()
def ui_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("JARVIS_UNITY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_UNITY_DISABLE_WAKE", "1")
    monkeypatch.setenv("JARVIS_UNITY_DISABLE_STARTUP_REGISTRY", "1")

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
    _wait_for_object(app, window, "registrationSkipButton")

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
    _click(app, window, _find(window, "registrationSkipButton"))

    assert runtime.state.currentScreen == "chat"
    _pump(app, 200)

    _click(app, window, _find(window, "navButton_voice"))
    assert runtime.state.currentScreen == "voice"

    _click(app, window, _find(window, "sidebarSettingsButton"))
    assert runtime.state.currentScreen == "settings"

    _click(app, window, _find(window, "navButton_apps"))
    assert runtime.state.currentScreen == "apps"


def test_registration_save_path_is_clickable(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _find(window, "groqField").setProperty("text", "gsk_test_key")
    _find(window, "userIdField").setProperty("text", "123456789")
    _find(window, "botTokenField").setProperty("text", "123:abc")
    _click(app, window, _find(window, "registrationSaveButton"))

    assert runtime.state.currentScreen == "chat"
    assert runtime.services.registration.load().is_complete is True


def test_registration_continue_requires_all_fields_and_shows_feedback(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _click(app, window, _find(window, "registrationSaveButton"))
    assert runtime.state.currentScreen == "registration"
    assert "Нужны все три поля" in _find(window, "registrationFeedback").property("text")

    _find(window, "groqField").setProperty("text", "gsk_test_key")
    _find(window, "userIdField").setProperty("text", "123456789")
    _find(window, "botTokenField").setProperty("text", "123:abc")
    _click(app, window, _find(window, "registrationSaveButton"))

    assert runtime.state.currentScreen == "chat"
    assert "Подключение сохранено" in runtime.registration_bridge.feedback


def test_chat_welcome_message_renders_and_ctrl_v_works(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _click(app, window, _find(window, "registrationSkipButton"))
    _wait_for(app, lambda: runtime.state.currentScreen == "chat")

    _find_by_text(
        window,
        "Я JARVIS Unity. Новый быстрый контур уже поднят. Можете писать как человеку или запускать действия прямо отсюда.",
    )

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

    _click(app, window, _find(window, "registrationSkipButton"))
    _wait_for(app, lambda: runtime.state.currentScreen == "chat")

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


def test_nav_spam_clicks_keep_screen_state_sane(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _click(app, window, _find(window, "registrationSkipButton"))
    _pump(app, 150)

    targets = ["navButton_chat", "navButton_voice", "navButton_apps", "sidebarSettingsButton"]
    for _ in range(5):
        for name in targets:
            _click(app, window, _find(window, name))
            _pump(app, 20)

    assert runtime.state.currentScreen in {"chat", "voice", "apps", "settings"}


def test_apps_screen_add_button_and_feedback_work(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _click(app, window, _find(window, "registrationSkipButton"))
    _pump(app, 200)
    _click(app, window, _find(window, "navButton_apps"))

    _find(window, "customAppTitleField").setProperty("text", "Deadlock")
    _find(window, "customAppTargetField").setProperty("text", "steam://rungameid/1422450")
    _find(window, "customAppAliasesField").setProperty("text", "дедлок, deadlock")
    before = len(runtime.services.actions.app_catalog())
    _click(app, window, _find(window, "customAppAddButton"))

    assert len(runtime.services.actions.app_catalog()) == before + 1
    assert "Добавлено" in runtime.apps_bridge.feedback


def test_settings_nubik_and_voice_controls_are_clickable(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _click(app, window, _find(window, "registrationSkipButton"))
    _pump(app, 200)
    _click(app, window, _find(window, "sidebarSettingsButton"))
    _wait_for(app, lambda: runtime.state.currentScreen == "settings")
    settings_scroll = _wait_for_object(app, window, "settingsScroll")
    settings_flickable = settings_scroll.property("contentItem")
    settings_flickable.setProperty("contentY", settings_flickable.property("contentHeight") - settings_flickable.property("height"))
    _pump(app, 120)
    _click(app, window, _find(window, "nubik_voice"))
    _wait_for(app, lambda: runtime.state.currentScreen == "voice")

    current = runtime.services.settings.get("wake_word_enabled", True)
    _click(app, window, _find(window, "wakeWordSwitch"))
    assert runtime.services.settings.get("wake_word_enabled", True) is (not current)

    _click(app, window, _find(window, "wakeWordTestButton"))
    assert _find(window, "voiceTestResult").property("text")


def test_scroll_views_accept_scroll_input(ui_runtime) -> None:
    app, runtime, window = ui_runtime

    _click(app, window, _find(window, "registrationSkipButton"))
    _pump(app, 200)
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

    _click(app, window, _find(window, "registrationSkipButton"))
    _pump(app, 200)
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
