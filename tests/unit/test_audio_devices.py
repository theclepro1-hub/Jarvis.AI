from __future__ import annotations

import pytest

from core.voice.audio_device_service import AudioDeviceService


class FakeAudioBackend:
    def __init__(self, devices: list[dict], hostapis: list[dict] | None = None, default=(0, 1)) -> None:
        self.devices = devices
        self.hostapis = hostapis or [{"name": "Windows WASAPI"}]
        self.default = default


def test_audio_device_service_groups_physical_devices_and_hides_duplicates():
    backend = FakeAudioBackend(
        devices=[
            {"name": "Microphone (Logitech PRO X Gaming Headset)", "max_input_channels": 2, "hostapi": 0},
            {"name": "Микрофон (Logitech PRO X Gaming Headset)", "max_input_channels": 2, "hostapi": 0},
            {"name": "Stereo Mix (Realtek HD Audio Stereo input)", "max_input_channels": 2, "hostapi": 0},
            {"name": "Line In (Realtek HD Audio Line input)", "max_input_channels": 2, "hostapi": 0},
            {"name": "Headphones (G435 Wireless Gaming Headset)", "max_output_channels": 2, "hostapi": 0},
            {"name": "Microphone (G435 Wireless Gaming Headset)", "max_output_channels": 2, "hostapi": 0},
            {"name": "SPDIF Out (Realtek HDA SPDIF Out)", "max_output_channels": 2, "hostapi": 0},
        ]
    )
    service = AudioDeviceService(
        query_devices=lambda: backend.devices,
        query_hostapis=lambda: backend.hostapis,
        default_device_getter=lambda: backend.default,
    )

    assert service.microphones[0] == "Системный микрофон"
    assert service.output_devices[0] == "Системный вывод"
    assert len(service.microphone_models) >= 2
    assert len(service.output_models) >= 2

    microphone_names = "\n".join(service.microphones).casefold()
    output_names = "\n".join(service.output_devices).casefold()
    assert "stereo mix" not in microphone_names
    assert "line in" not in microphone_names
    assert "spdif" not in output_names
    assert "microphone" not in output_names
    assert len(service.microphones) == len(set(service.microphones))
    assert len(service.output_devices) == len(set(service.output_devices))

    grouped_input = service.microphone_models[1]
    grouped_qml = grouped_input.as_grouped_qml()
    assert grouped_qml["displayName"] == "Logitech PRO X"
    assert len(grouped_input.inputEndpoints) == 2
    assert grouped_input.inputEndpoints[0].isDefault is True or grouped_input.inputEndpoints[1].isDefault is True


def test_audio_device_service_raises_when_saved_microphone_disappears():
    backend = FakeAudioBackend(
        devices=[
            {"name": "Microphone (Logitech PRO X Gaming Headset)", "max_input_channels": 2, "hostapi": 0},
        ]
    )
    service = AudioDeviceService(
        query_devices=lambda: backend.devices,
        query_hostapis=lambda: backend.hostapis,
        default_device_getter=lambda: backend.default,
    )

    with pytest.raises(LookupError, match='Выбранный микрофон "Missing Mic" недоступен'):
        service.resolve_input_device("Missing Mic")
