from __future__ import annotations

import re
from typing import Callable

import sounddevice as sd

from core.voice.voice_models import AudioDevice, AudioEndpoint


class AudioDeviceService:
    DEFAULT_INPUT_LABEL = "Системный микрофон"
    DEFAULT_OUTPUT_LABEL = "Системный вывод"

    INPUT_BLOCKLIST = (
        "@system32",
        "\\drivers\\",
        "input (@",
        "driver dump",
        "system capture",
        "stereo mix",
        "стерео микшер",
        "line in",
        "лин. вход",
        "loopback",
        "mapper",
        "primary driver",
        "первичный драйвер",
        "первичный звуковой драйвер",
        "драйвер записи звука",
        "переназначение звуковых устр",
        "spdif",
        "s/pdif",
        "digital audio",
        "nvidia high definition",
        "hdmi",
    )
    OUTPUT_BLOCKLIST = (
        "@system32",
        "\\drivers\\",
        "input (@",
        "microphone",
        "mic input",
        "микрофон",
        "stereo mix",
        "стерео микшер",
        "line in",
        "лин. вход",
        "spdif",
        "s/pdif",
        "digital audio",
        "digital output",
        "realtek digital output",
        "nvidia high definition audio",
        "nvidia high definition",
        "переназначение звуковых устр",
        "loopback",
        "mapper",
        "primary driver",
        "первичный драйвер",
        "первичный звуковой драйвер",
        "драйвер записи звука",
    )

    def __init__(
        self,
        query_devices: Callable[[], list[dict]] | None = None,
        query_hostapis: Callable[[], list[dict]] | None = None,
        default_device_getter: Callable[[], object] | None = None,
    ) -> None:
        self._query_devices = query_devices or sd.query_devices
        self._query_hostapis = query_hostapis or sd.query_hostapis
        self._default_device_getter = default_device_getter or (lambda: sd.default.device)
        self._input_lookup: dict[str, str] = {}
        self._output_lookup: dict[str, str] = {}
        self._input_models = self._build_grouped_models("input")
        self._output_models = self._build_grouped_models("output")
        self.microphones = [device.name for device in self._input_models]
        self.output_devices = [device.name for device in self._output_models]

    @property
    def microphone_models(self) -> list[AudioDevice]:
        return list(self._input_models)

    @property
    def output_models(self) -> list[AudioDevice]:
        return list(self._output_models)

    def normalize_microphone_selection(self, value: str) -> str:
        return self._normalize_device_selection(value, self.DEFAULT_INPUT_LABEL, self._input_lookup)

    def normalize_output_selection(self, value: str) -> str:
        return self._normalize_device_selection(value, self.DEFAULT_OUTPUT_LABEL, self._output_lookup)

    def resolve_input_device(self, value: str | None = None) -> int | None:
        selected = self.normalize_microphone_selection(
            value or self.DEFAULT_INPUT_LABEL,
        )
        return self._resolve_device_index(selected, "max_input_channels")

    def resolve_output_device(self, value: str | None = None) -> int | None:
        selected = self.normalize_output_selection(value or self.DEFAULT_OUTPUT_LABEL)
        return self._resolve_device_index(selected, "max_output_channels")

    def _build_grouped_models(self, kind: str) -> list[AudioDevice]:
        channels_key = "max_input_channels" if kind == "input" else "max_output_channels"
        default_label = self.DEFAULT_INPUT_LABEL if kind == "input" else self.DEFAULT_OUTPUT_LABEL
        blocklist = self.INPUT_BLOCKLIST if kind == "input" else self.OUTPUT_BLOCKLIST
        lookup_attr = "_input_lookup" if kind == "input" else "_output_lookup"

        try:
            raw_devices = list(self._query_devices() or [])
        except Exception:
            raw_devices = []

        hostapis = self._hostapi_names()
        default_input_index, default_output_index = self._default_device_indices()
        default_index = default_input_index if kind == "input" else default_output_index

        groups: dict[str, dict[str, object]] = {}
        lookup: dict[str, str] = {
            default_label.casefold(): default_label,
            self._device_key(default_label): default_label,
        }

        for index, raw_device in enumerate(raw_devices):
            channels = int(raw_device.get(channels_key, 0) or 0)
            if channels <= 0:
                continue

            raw_name = str(raw_device.get("name", "")).strip()
            if not raw_name or self._is_blocked_endpoint(raw_name, blocklist):
                continue

            display_name = self._friendly_device_name(self._device_display_name(raw_name))
            if not display_name:
                continue
            family_name = self._friendly_device_name(self._device_family_name(raw_name))
            grouped_name = family_name or display_name

            group_key = self._device_family_key(raw_name) or self._device_key(display_name)
            if not group_key:
                continue

            canonical_key = self._find_duplicate_device_key(group_key, groups) or group_key

            hostapi_index = raw_device.get("hostapi")
            hostapi = hostapis.get(int(hostapi_index), "") if isinstance(hostapi_index, int) else ""
            endpoint = AudioEndpoint(
                id=f"{kind}:{index}",
                name=grouped_name,
                raw_name=raw_name,
                index=index,
                channels=channels,
                isDefault=index == default_index,
                hostapi=hostapi or "system",
            )

            group = groups.setdefault(
                canonical_key,
                {
                    "best_name": grouped_name,
                    "best_score": self._device_score(grouped_name),
                    "hostapi": hostapi or "system",
                    "endpoints": [],
                    "default": False,
                },
            )
            group["endpoints"].append(endpoint)
            if endpoint.isDefault:
                group["default"] = True
            score = self._device_score(grouped_name)
            if score > int(group["best_score"]):
                group["best_name"] = grouped_name
                group["best_score"] = score
                group["hostapi"] = hostapi or "system"

        ordered: list[AudioDevice] = [self._default_device(kind)]
        for group_key, data in sorted(
            groups.items(),
            key=lambda item: (not bool(item[1]["default"]), str(item[1]["best_name"]).casefold()),
        ):
            endpoints = tuple(sorted(data["endpoints"], key=lambda endpoint: (not endpoint.isDefault, endpoint.name.casefold())))  # type: ignore[arg-type]
            preferred = self._preferred_endpoint(endpoints)
            display_name = str(data["best_name"])
            device = AudioDevice(
                id=group_key,
                name=display_name,
                kind=kind,
                hostapi=str(data["hostapi"]),
                channels=max((endpoint.channels for endpoint in endpoints), default=0),
                isDefault=bool(data["default"]),
                isUsable=True,
                roles=(kind,),
                inputEndpoints=endpoints if kind == "input" else (),
                outputEndpoints=endpoints if kind == "output" else (),
                preferredInputEndpointId=preferred.id if kind == "input" and preferred else "",
                preferredOutputEndpointId=preferred.id if kind == "output" and preferred else "",
            )
            ordered.append(device)

        for device in ordered:
            if device.isDefault:
                lookup[device.name.casefold()] = default_label
                lookup[self._device_key(device.name)] = default_label
                continue
            preferred_raw_name = self._preferred_raw_name(device)
            lookup[device.name.casefold()] = preferred_raw_name
            lookup[self._device_key(device.name)] = preferred_raw_name
            lookup[preferred_raw_name.casefold()] = preferred_raw_name

        setattr(self, lookup_attr, lookup)
        return ordered

    def _default_device(self, kind: str) -> AudioDevice:
        default_label = self.DEFAULT_INPUT_LABEL if kind == "input" else self.DEFAULT_OUTPUT_LABEL
        return AudioDevice(
            id="system_default",
            name=default_label,
            kind=kind,
            hostapi="system",
            channels=0,
            isDefault=True,
            isUsable=True,
        )

    def _preferred_endpoint(self, endpoints: tuple[AudioEndpoint, ...]) -> AudioEndpoint | None:
        if not endpoints:
            return None
        for endpoint in endpoints:
            if endpoint.isDefault:
                return endpoint
        return max(endpoints, key=lambda endpoint: (self._device_score(endpoint.name), endpoint.channels))

    def _preferred_raw_name(self, device: AudioDevice) -> str:
        endpoints = device.inputEndpoints or device.outputEndpoints
        preferred = self._preferred_endpoint(endpoints)
        if preferred is not None:
            return preferred.raw_name
        return device.name

    def _normalize_device_selection(self, value: str, default_label: str, lookup: dict[str, str]) -> str:
        if not value:
            return default_label
        if value == default_label:
            return value

        raw_name = lookup.get(value.casefold()) or lookup.get(self._device_key(value))
        if raw_name is None:
            normalized = self._device_display_name(value)
            return normalized or default_label

        normalized = self._device_display_name(raw_name)
        return normalized or default_label

    def _resolve_device_index(self, selected: str, channels_key: str) -> int | None:
        if not selected or selected in {self.DEFAULT_INPUT_LABEL, self.DEFAULT_OUTPUT_LABEL}:
            return None

        try:
            raw_devices = list(self._query_devices() or [])
        except Exception:
            return None

        selected_key = self._device_key(selected)
        for index, raw_device in enumerate(raw_devices):
            if int(raw_device.get(channels_key, 0) or 0) <= 0:
                continue
            raw_name = str(raw_device.get("name", "")).strip()
            if not raw_name:
                continue
            candidate = self._device_display_name(raw_name)
            if self._device_key(candidate) == selected_key or raw_name.casefold() == selected.casefold():
                return index
        return None

    def _hostapi_names(self) -> dict[int, str]:
        try:
            return {index: str(api.get("name", "")) for index, api in enumerate(self._query_hostapis())}
        except Exception:
            return {}

    def _default_device_indices(self) -> tuple[int | None, int | None]:
        try:
            default = self._default_device_getter()
        except Exception:
            return None, None
        if isinstance(default, (list, tuple)) and len(default) >= 2:
            return self._safe_device_index(default[0]), self._safe_device_index(default[1])
        return None, None

    def _safe_device_index(self, value) -> int | None:
        try:
            index = int(value)
        except (TypeError, ValueError):
            return None
        return index if index >= 0 else None

    def _device_display_name(self, raw_name: str) -> str:
        cleaned = raw_name.strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(
            r"^(microphone|микрофон|speakers|speaker|динамики|наушники|гарнитура|гарнитуры|headphones|input|output)\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^-\s*", "", cleaned)
        cleaned = re.sub(r"\s*@system32.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*\(@.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*-\s*(input|capture|render|output).*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+(input|output|capture|render)$", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip("()[]{} -")
        if cleaned.startswith("@"):
            return ""
        if len(cleaned) > 72:
            cleaned = cleaned[:72].rstrip()
        return cleaned

    def _friendly_device_name(self, name: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(name or "").strip())
        if not cleaned:
            return ""
        lowered = cleaned.casefold()
        if "g435" in lowered:
            return "G435"
        if "pro x" in lowered:
            return "Logitech PRO X"
        if "realtek hd audio" in lowered:
            if any(marker in lowered for marker in ("mic", "microphone", "input", "микрофон")):
                return "Realtek HD Audio Mic"
            return "Realtek HD Audio"
        cleaned = re.sub(r"\s+(wireless\s+)?gaming\s+headset$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+headset$", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def _device_key(self, raw_name: str) -> str:
        cleaned = raw_name.casefold()
        if "g435" in cleaned:
            return "g435"
        if "pro x" in cleaned:
            return "logitech pro x"
        cleaned = re.sub(r"\(.*?\)", " ", cleaned)
        cleaned = re.sub(r"[^0-9a-zа-яё]+", " ", cleaned)
        cleaned = re.sub(
            r"\b(microphone|микрофон|input|output|speaker|speakers|динамики|headphones|"
            r"наушники|гарнитура|гарнитуры|headset|primary|driver|system|системный|по|умолчанию|audio|hd)\b",
            " ",
            cleaned,
        )
        cleaned = re.sub(r"\bgamin\b", "gaming", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _device_family_key(self, raw_name: str) -> str:
        matches = re.findall(r"\(([^()]*)\)", raw_name)
        for candidate in reversed(matches):
            key = self._device_key(candidate)
            if len(key) >= 4:
                return key
        return ""

    def _device_family_name(self, raw_name: str) -> str:
        matches = re.findall(r"\(([^()]*)\)", raw_name)
        for candidate in reversed(matches):
            cleaned = re.sub(r"\s+", " ", candidate).strip("()[]{} -")
            if len(self._device_key(cleaned)) >= 4:
                return cleaned
        cleaned = self._device_display_name(raw_name)
        return cleaned

    def _find_duplicate_device_key(self, key: str, existing: dict[str, AudioDevice]) -> str | None:
        for current_key in existing:
            if key == current_key:
                return current_key
            if len(key) >= 8 and len(current_key) >= 8 and (
                key.startswith(current_key) or current_key.startswith(key)
            ):
                return current_key
        return None

    def _device_score(self, label: str) -> int:
        score = len(label)
        lowered = label.casefold()
        if lowered.endswith(("gami", "gamin")):
            score -= 30
        if "(" in label or ")" in label:
            score -= 5
        return score

    def _is_blocked_endpoint(self, raw_name: str, blocklist: tuple[str, ...]) -> bool:
        lowered = raw_name.casefold()
        if raw_name.count("(") != raw_name.count(")"):
            return True
        return any(marker in lowered for marker in blocklist) or lowered.startswith("@system32")
