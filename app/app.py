from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer, QUrl
from PySide6.QtGui import QAction, QFontDatabase, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from core.services.service_container import ServiceContainer
from core.services.single_instance import SingleInstanceService
from core.state.app_state import AppState
from ui.bridge.app_bridge import AppBridge
from ui.bridge.apps_bridge import AppsBridge
from ui.bridge.chat_bridge import ChatBridge
from ui.bridge.registration_bridge import RegistrationBridge
from ui.bridge.settings_bridge import SettingsBridge
from ui.bridge.voice_bridge import VoiceBridge


def _boot_log(message: str) -> None:
    if os.environ.get("JARVIS_UNITY_BOOT_LOG") != "1":
        return
    try:
        start_ns = int(os.environ.get("JARVIS_UNITY_BOOT_T0_NS", "0") or "0")
        elapsed_ms = 0.0
        if start_ns > 0:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
        log_path = Path.home() / "AppData" / "Local" / "JarvisAi_Unity" / "bootstrap.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{elapsed_ms:9.2f} ms] {message}\n")
    except Exception:
        pass


def _wake_start_delay_ms() -> int:
    raw = str(os.environ.get("JARVIS_UNITY_WAKE_START_DELAY_MS", "900") or "900").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 900
    return max(250, min(value, 5000))


def _load_embedded_fonts() -> None:
    fonts_dir = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    if not fonts_dir.exists():
        return
    for font_path in fonts_dir.glob("*.ttf"):
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                _boot_log(f"app:font-loaded:{font_path.name}:{','.join(families)}")


class JarvisUnityApplication:
    def __init__(
        self,
        qapp,
        *,
        start_minimized: bool = False,
        single_instance: SingleInstanceService | None = None,
    ) -> None:
        _boot_log("app:init:begin")
        self.qapp = qapp
        self.start_minimized = start_minimized
        self.single_instance = single_instance
        self.window = None
        self.tray_icon = None
        self._tray_menu = None
        self._close_filter = None
        self._force_quit = False
        self._background_timer = None
        self._telegram_timer = None
        self._telegram_polling = False
        self._update_timer = None
        self._update_checking = False
        _load_embedded_fonts()
        _boot_log("app:init:fonts")
        self.services = ServiceContainer()
        _boot_log("app:init:services")
        self.state = AppState()
        _boot_log("app:init:state")
        self.engine = QQmlApplicationEngine()
        _boot_log("app:init:engine")

        self.app_bridge = AppBridge(self.state, self.services)
        _boot_log("app:init:app-bridge")
        self.chat_bridge = ChatBridge(self.state, self.services, self.app_bridge)
        _boot_log("app:init:chat-bridge")
        self.apps_bridge = AppsBridge(self.services, self.chat_bridge)
        _boot_log("app:init:apps-bridge")
        self.voice_bridge = VoiceBridge(self.state, self.services, self.chat_bridge)
        _boot_log("app:init:voice-bridge")
        self.app_bridge.voice_bridge = self.voice_bridge
        self.settings_bridge = SettingsBridge(self.state, self.services, self.app_bridge, self.chat_bridge)
        _boot_log("app:init:settings-bridge")
        self.registration_bridge = RegistrationBridge(self.state, self.services, self.app_bridge)
        _boot_log("app:init:registration-bridge")

    def start(self) -> None:
        _boot_log("app:start:begin")
        self.qapp.aboutToQuit.connect(self.voice_bridge.shutdown)
        if self.single_instance is not None:
            self.single_instance.attach_show_handler(self.show_window)
            self.qapp.aboutToQuit.connect(self.single_instance.stop)

        root_context = self.engine.rootContext()
        _boot_log("app:start:root-context")
        root_context.setContextProperty("appBridge", self.app_bridge)
        root_context.setContextProperty("appsBridge", self.apps_bridge)
        root_context.setContextProperty("chatBridge", self.chat_bridge)
        root_context.setContextProperty("voiceBridge", self.voice_bridge)
        root_context.setContextProperty("settingsBridge", self.settings_bridge)
        root_context.setContextProperty("registrationBridge", self.registration_bridge)
        _boot_log("app:start:context-properties")

        app_qml = Path(__file__).resolve().parents[1] / "ui" / "qml" / "App.qml"
        _boot_log(f"app:start:load:{app_qml}")
        self.engine.load(QUrl.fromLocalFile(str(app_qml)))
        _boot_log("app:start:after-load")
        if not self.engine.rootObjects():
            raise RuntimeError("Failed to load App.qml")
        self.window = self.engine.rootObjects()[0]
        self._install_tray_mode()
        _boot_log("app:start:root-objects")
        if self.start_minimized and self._tray_enabled():
            QTimer.singleShot(0, lambda: self.hide_to_tray(show_message=False))
        self._install_background_services()
        if os.environ.get("JARVIS_UNITY_DISABLE_WAKE") != "1":
            QTimer.singleShot(_wake_start_delay_ms(), self.voice_bridge.startWakeRuntime)
            _boot_log("app:start:wake-scheduled")

    def _install_tray_mode(self) -> None:
        if self.window is not None:
            self._close_filter = _WindowCloseFilter(self)
            self.window.installEventFilter(self._close_filter)

        if not QSystemTrayIcon.isSystemTrayAvailable():
            _boot_log("app:tray:unavailable")
            return

        icon_path = Path(__file__).resolve().parents[1] / "assets" / "icons" / "jarvis_unity.ico"
        icon = QIcon(str(icon_path)) if icon_path.exists() else self.qapp.windowIcon()
        self.tray_icon = QSystemTrayIcon(icon, self.qapp)
        self.tray_icon.setToolTip("JARVIS Unity")

        menu = QMenu()
        open_action = QAction("Открыть JARVIS", menu)
        open_action.triggered.connect(self.show_window)
        hide_action = QAction("Свернуть в трей", menu)
        hide_action.triggered.connect(lambda: self.hide_to_tray(show_message=False))
        quit_action = QAction("Выход", menu)
        quit_action.triggered.connect(self.quit_application)
        menu.addAction(open_action)
        menu.addAction(hide_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self._tray_menu = menu
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._handle_tray_activated)
        self.tray_icon.show()
        _boot_log("app:tray:ready")

    def _tray_enabled(self) -> bool:
        return bool(self.services.settings.get("minimize_to_tray_enabled", True)) and self.tray_icon is not None

    def should_hide_close_to_tray(self) -> bool:
        return not self._force_quit and self._tray_enabled()

    def hide_to_tray(self, *, show_message: bool) -> None:
        if self.window is None or not self._tray_enabled():
            return
        self.window.hide()
        if show_message and self.tray_icon is not None:
            self.tray_icon.showMessage(
                "JARVIS Unity",
                "JARVIS продолжает работать в трее.",
                QSystemTrayIcon.MessageIcon.Information,
                1800,
            )

    def show_window(self) -> None:
        if self.window is None:
            return
        try:
            self.window.showNormal()
        except Exception:
            pass
        self.window.show()
        self.window.raise_()
        self.window.requestActivate()

    def quit_application(self) -> None:
        self._force_quit = True
        if self.tray_icon is not None:
            self.tray_icon.hide()
        if self.single_instance is not None:
            self.single_instance.stop()
        self.qapp.quit()

    def _handle_tray_activated(self, reason) -> None:
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self.show_window()

    def _install_background_services(self) -> None:
        self._background_timer = QTimer()
        self._background_timer.setInterval(1000)
        self._background_timer.timeout.connect(self._fire_due_reminders)
        self._background_timer.start()
        self._telegram_timer = QTimer()
        self._telegram_timer.setInterval(self._telegram_poll_interval_ms())
        self._telegram_timer.timeout.connect(self._poll_telegram_async)
        self._telegram_timer.start()
        QTimer.singleShot(250, self._poll_telegram_async)
        QTimer.singleShot(1000, self._fire_due_reminders)
        self._update_timer = QTimer()
        self._update_timer.setInterval(self._update_check_interval_ms())
        self._update_timer.timeout.connect(self._check_updates_async)
        self._update_timer.start()
        QTimer.singleShot(2500, self._check_updates_async)

    def _tick_background_services(self) -> None:
        self._fire_due_reminders()
        self._poll_telegram_async()

    def _telegram_poll_interval_ms(self) -> int:
        telegram = getattr(self.services, "telegram", None)
        if telegram is None or not hasattr(telegram, "poll_interval_ms"):
            return 1000
        return max(750, int(telegram.poll_interval_ms()))

    def _fire_due_reminders(self) -> None:
        reminders = getattr(self.services, "reminders", None)
        if reminders is None:
            return

        def notify(record) -> None:  # noqa: ANN001
            message = f"Напоминание: {record.text}"
            self.chat_bridge.appendAssistantNote(message)
            self._send_telegram_note_async(record, message)

        try:
            reminders.fire_due(notify)
        except Exception as exc:  # noqa: BLE001
            _boot_log(f"app:reminders:tick-failed:{exc!r}")

    def _send_telegram_note_async(self, record, message: str) -> None:  # noqa: ANN001
        telegram = getattr(self.services, "telegram", None)
        if telegram is not None and hasattr(telegram, "refresh_configuration"):
            telegram.refresh_configuration()
        if telegram is None or not hasattr(telegram, "send_message"):
            return
        if hasattr(telegram, "is_configured") and not telegram.is_configured():
            return
        chat_id = str(getattr(record, "telegram_chat_id", "") or "").strip()
        if not chat_id and hasattr(telegram, "telegram_user_id"):
            chat_id = str(telegram.telegram_user_id()).strip()
        if not chat_id:
            return

        def worker() -> None:
            try:
                telegram.send_message(chat_id, message)
            except Exception as exc:  # noqa: BLE001
                _boot_log(f"app:telegram:reminder-send-failed:{exc!r}")

        threading.Thread(target=worker, daemon=True).start()

    def _poll_telegram_async(self) -> None:
        telegram = getattr(self.services, "telegram", None)
        if telegram is None:
            return
        if hasattr(telegram, "refresh_configuration"):
            telegram.refresh_configuration()
        if hasattr(telegram, "is_configured") and not telegram.is_configured():
            return
        if getattr(telegram, "transport", None) is None:
            return
        if hasattr(telegram, "can_poll_now") and not telegram.can_poll_now():
            return
        if self._telegram_polling:
            return
        self._telegram_polling = True

        def worker() -> None:
            try:
                try:
                    telegram.poll_once(async_dispatch=True)
                except TypeError:
                    telegram.poll_once()
            except Exception as exc:  # noqa: BLE001
                _boot_log(f"app:telegram:poll-failed:{exc!r}")
            finally:
                self._telegram_polling = False

        threading.Thread(target=worker, daemon=True).start()

    def _update_check_interval_ms(self) -> int:
        return 6 * 60 * 60 * 1000

    def _check_updates_async(self) -> None:
        updates = getattr(self.services, "updates", None)
        if updates is None or not hasattr(updates, "check_now"):
            return
        if self._update_checking:
            return
        self._update_checking = True

        def worker() -> None:
            try:
                updates.check_now()
            except Exception as exc:  # noqa: BLE001
                _boot_log(f"app:updates:check-failed:{exc!r}")
            finally:
                self._update_checking = False
                if hasattr(self, "settings_bridge") and hasattr(self.settings_bridge, "updateSummaryChanged"):
                    self.settings_bridge.updateSummaryChanged.emit()

        threading.Thread(target=worker, daemon=True).start()


class _WindowCloseFilter(QObject):
    def __init__(self, runtime: JarvisUnityApplication) -> None:
        super().__init__()
        self.runtime = runtime

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Close and self.runtime.should_hide_close_to_tray():
            event.ignore()
            self.runtime.hide_to_tray(show_message=True)
            return True
        return super().eventFilter(watched, event)
