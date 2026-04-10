from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from core.actions.action_registry import ActionRegistry
from core.actions.launcher_discovery import DiscoveryRoots, LauncherDiscovery
from core.models.action_models import ActionOutcome
from core.routing.batch_router import BatchRouter
from core.routing.command_router import CommandRouter
from core.settings.settings_service import SettingsService
from core.updates.update_service import UpdateAsset, UpdateService
from core.voice.voice_service import VoiceService
from ui.bridge.voice_bridge import VoiceBridge


class FakeStore:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = {
            "theme_mode": "midnight",
            "startup_enabled": False,
            "privacy_mode": "balance",
            "ai_provider": "groq",
            "ai_model": "openai/gpt-oss-20b",
            "voice_mode": "balance",
            "command_style": "one_shot",
            "wake_word_enabled": True,
            "microphone_name": "Системный микрофон",
            "voice_output_name": "Системный вывод",
            "voice_response_enabled": False,
            "tts_engine": "system",
            "tts_voice_name": "Голос по умолчанию",
            "tts_rate": 185,
            "tts_volume": 85,
            "default_music_app": "",
            "registration": {
                "groq_api_key": "",
                "telegram_user_id": "",
                "telegram_bot_token": "",
                "skipped": False,
            },
            "custom_apps": [],
        }
        if payload:
            self.payload.update(payload)

    def load(self) -> dict:
        return self.payload.copy()

    def save(self, payload: dict) -> None:
        self.payload = payload


def make_roots(tmp_path: Path) -> DiscoveryRoots:
    return DiscoveryRoots(
        program_data=tmp_path / "ProgramData",
        app_data=tmp_path / "AppData" / "Roaming",
        local_app_data=tmp_path / "AppData" / "Local",
        program_files=tmp_path / "ProgramFiles",
        program_files_x86=tmp_path / "ProgramFilesX86",
        start_menu_all=tmp_path / "ProgramData" / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        start_menu_user=tmp_path / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    )


def test_release_gate_audio_devices_are_kind_safe_and_deduped(monkeypatch) -> None:
    devices = [
        {"name": "Microphone (Logitech PRO X Gaming Headset)", "max_input_channels": 2, "max_output_channels": 0},
        {"name": "Микрофон (Logitech PRO X Gaming Headset)", "max_input_channels": 2, "max_output_channels": 0},
        {"name": "Stereo Mix (Realtek HD Audio Stereo input)", "max_input_channels": 2, "max_output_channels": 0},
        {"name": "Line In (Realtek HD Audio Line input)", "max_input_channels": 2, "max_output_channels": 0},
        {"name": "SPDIF Out (Realtek HDA SPDIF Out)", "max_input_channels": 0, "max_output_channels": 2},
        {"name": "NVIDIA High Definition Audio", "max_input_channels": 2, "max_output_channels": 2},
        {"name": "Speakers (Realtek HD Audio)", "max_input_channels": 0, "max_output_channels": 2},
        {"name": "Microphone (USB Capture)", "max_input_channels": 0, "max_output_channels": 2},
    ]
    monkeypatch.setattr("core.voice.voice_service.sd.query_devices", lambda: devices)

    voice = VoiceService(SettingsService(FakeStore()))

    joined_inputs = "\n".join(voice.microphones).casefold()
    assert "stereo mix" not in joined_inputs
    assert "line in" not in joined_inputs
    assert "spdif" not in joined_inputs
    assert "nvidia" not in joined_inputs
    assert len(voice.microphones) == len(set(voice.microphones))

    joined_outputs = "\n".join(voice.output_devices).casefold()
    assert "microphone" not in joined_outputs
    assert "микрофон" not in joined_outputs
    assert len(voice.output_devices) == len(set(voice.output_devices))


def test_release_gate_launcher_discovery_hides_redistributables(tmp_path: Path) -> None:
    roots = make_roots(tmp_path)
    steamapps = roots.program_files_x86 / "Steam" / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_1422450.acf").write_text(
        '"AppState"\n{\n    "appid" "1422450"\n    "name" "Deadlock"\n}\n',
        encoding="utf-8",
    )
    (steamapps / "appmanifest_228980.acf").write_text(
        '"AppState"\n{\n    "appid" "228980"\n    "name" "Steamworks Common Redistributables"\n}\n',
        encoding="utf-8",
    )

    found = LauncherDiscovery(roots).discover()
    titles = {item.title for item in found}

    assert "Deadlock" in titles
    assert "Steamworks Common Redistributables" not in titles


def test_release_gate_quick_actions_are_curated_and_capped() -> None:
    custom_apps = [
        {
            "id": f"custom_game_{index}",
            "title": f"Game {index}",
            "aliases": [f"game {index}"],
            "kind": "uri",
            "target": f"steam://rungameid/{index}",
            "custom": True,
        }
        for index in range(10)
    ]
    custom_apps.append(
        {
            "id": "custom_redistributables",
            "title": "Steamworks Common Redistributables",
            "aliases": ["steamworks common redistributables"],
            "kind": "uri",
            "target": "steam://rungameid/228980",
            "custom": True,
        }
    )
    actions = ActionRegistry(SettingsService(FakeStore({"custom_apps": custom_apps})))

    quick_actions = actions.quick_actions()
    quick_titles = {item["title"] for item in quick_actions}

    assert len(quick_actions) <= 7
    assert quick_titles >= {"YouTube", "Браузер", "Steam", "Discord"}
    assert "Музыка" not in quick_titles
    assert all(item["title"] != "Steamworks Common Redistributables" for item in quick_actions)


def test_release_gate_music_command_uses_default_music_app() -> None:
    custom_apps = [
        {
            "id": "custom_yandex_music",
            "title": "Яндекс Музыка",
            "aliases": ["яндекс музыка", "музыка"],
            "kind": "file",
            "target": r"C:\Users\me\AppData\Local\Programs\YandexMusic\Яндекс Музыка.exe",
            "custom": True,
        }
    ]
    settings = SettingsService(
        FakeStore(
            {
                "custom_apps": custom_apps,
                "default_music_app": "custom_yandex_music",
            }
        )
    )
    actions = ActionRegistry(settings)

    found = actions.find_items("открой музыку")

    assert [item["id"] for item in found] == ["custom_yandex_music"]


def test_release_gate_wake_notes_do_not_become_chat_bubbles() -> None:
    class ChatSpy:
        def __init__(self) -> None:
            self.appended: list[str] = []

        def appendAssistantNote(self, text: str) -> None:
            self.appended.append(text)

    state = SimpleNamespace(status="")
    chat = ChatSpy()
    bridge = VoiceBridge(state=state, services=SimpleNamespace(), chat_bridge=chat)

    bridge._push_voice_note("Не расслышал команду после слова активации.")  # noqa: SLF001

    assert chat.appended == []
    assert state.status == "Не расслышал"


def test_release_gate_local_commands_do_not_call_llm() -> None:
    class Actions:
        def __init__(self) -> None:
            self.opened: list[str] = []

        def find_items(self, text: str):
            if "youtube" in text.casefold() or "ютуб" in text.casefold():
                return [{"id": "youtube", "title": "YouTube", "kind": "url", "target": "https://www.youtube.com"}]
            return []

        def open_items(self, items):
            self.opened.extend(item["id"] for item in items)
            return [ActionOutcome(True, f"Открываю {item['title']}", "") for item in items]

        def volume_up(self) -> ActionOutcome:
            return ActionOutcome(True, "Прибавляю громкость", "")

        def volume_down(self) -> ActionOutcome:
            return ActionOutcome(True, "Убавляю громкость", "")

        def volume_mute(self) -> ActionOutcome:
            return ActionOutcome(True, "Переключаю звук", "")

    class Ai:
        def generate_reply(self, *_args, **_kwargs):
            raise AssertionError("local command must not call LLM")

    actions = Actions()
    router = CommandRouter(actions, BatchRouter(actions), Ai())

    result = router.handle("открой youtube")

    assert result.kind == "local"
    assert actions.opened == ["youtube"]


def test_release_gate_updater_is_honest_about_installer_only_flow() -> None:
    service = UpdateService(settings=None, current_version="22.3.0")
    service.assets = [
        UpdateAsset(
            name="JarvisAi_Unity_22.4.1_windows_onefile.exe",
            browser_download_url="https://example.test/onefile.exe",
        ),
        UpdateAsset(
            name="JarvisAi_Unity_22.4.1_windows_portable.zip",
            browser_download_url="https://example.test/portable.zip",
        ),
    ]
    service.latest_version_value = "22.4.1"
    service.release_url_value = "https://example.test/releases/v22.4.1"
    service.update_available_value = True

    snapshot = service.status_snapshot()

    assert snapshot["can_apply"] is False
    assert snapshot["preferred_installer_asset"] == ""
    assert snapshot["manual_download_required"] is True
    assert snapshot["apply_mode"] == "manual"
    assert "только вручную" in snapshot["apply_hint"]


def test_release_gate_updater_exposes_installer_contract_when_available() -> None:
    digest = hashlib.sha256(b"installer").hexdigest()
    service = UpdateService(settings=None, current_version="22.3.0")
    service.assets = [
        UpdateAsset(
            name="JarvisAi_Unity_22.4.1_windows_installer.exe",
            browser_download_url="https://example.test/installer.exe",
            digest=f"sha256:{digest}",
        )
    ]
    service.latest_version_value = "22.4.1"
    service.release_url_value = "https://example.test/releases/v22.4.1"
    service.update_available_value = True

    snapshot = service.status_snapshot()

    assert snapshot["can_apply"] is True
    assert snapshot["preferred_installer_asset"] == "JarvisAi_Unity_22.4.1_windows_installer.exe"
    assert snapshot["manual_download_required"] is False
    assert snapshot["apply_mode"] == "installer"
    assert snapshot["installer_launch_arguments"] == ["/SP-", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"]
