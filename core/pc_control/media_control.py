from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class MediaControl:
    VOLUME_DELTA = 0.10
    VOLUME_KEY_FALLBACK_STEPS = 5
    VK_VOLUME_UP = 0xAF
    VK_VOLUME_DOWN = 0xAE
    VK_VOLUME_MUTE = 0xAD
    VK_MEDIA_NEXT_TRACK = 0xB0
    VK_MEDIA_PREV_TRACK = 0xB1
    VK_MEDIA_PLAY_PAUSE = 0xB3

    def play_pause(self) -> bool:
        return self.send_key(self.VK_MEDIA_PLAY_PAUSE)

    def next_track(self) -> bool:
        return self.send_key(self.VK_MEDIA_NEXT_TRACK)

    def previous_track(self) -> bool:
        return self.send_key(self.VK_MEDIA_PREV_TRACK)

    def volume_up(self) -> bool:
        return self._change_endpoint_volume("up") or self._send_repeated_key(
            self.VK_VOLUME_UP,
            self.VOLUME_KEY_FALLBACK_STEPS,
        )

    def volume_down(self) -> bool:
        return self._change_endpoint_volume("down") or self._send_repeated_key(
            self.VK_VOLUME_DOWN,
            self.VOLUME_KEY_FALLBACK_STEPS,
        )

    def mute(self) -> bool:
        return self._change_endpoint_volume("mute") or self.send_key(self.VK_VOLUME_MUTE)

    def send_key(self, virtual_key: int) -> bool:
        if os.name != "nt":
            return False
        try:
            return self._send_input(virtual_key)
        except Exception:
            return False

    def _send_repeated_key(self, virtual_key: int, count: int) -> bool:
        if count <= 0:
            return False
        return all(self.send_key(virtual_key) for _ in range(count))

    def _send_input(self, virtual_key: int) -> bool:
        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002
        try:
            ulong_ptr = wintypes.ULONG_PTR
        except AttributeError:  # pragma: no cover - Windows type alias absent on some builds.
            ulong_ptr = ctypes.c_size_t

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ulong_ptr),
            ]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ulong_ptr),
            ]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [
                ("uMsg", wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD),
            ]

        class INPUTUNION(ctypes.Union):
            _fields_ = [
                ("mi", MOUSEINPUT),
                ("ki", KEYBDINPUT),
                ("hi", HARDWAREINPUT),
            ]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("union",)
            _fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]

        extra = ulong_ptr(0)
        inputs = (INPUT * 2)()
        inputs[0].type = INPUT_KEYBOARD
        inputs[0].ki = KEYBDINPUT(virtual_key, 0, 0, 0, extra)
        inputs[1].type = INPUT_KEYBOARD
        inputs[1].ki = KEYBDINPUT(virtual_key, 0, KEYEVENTF_KEYUP, 0, extra)

        sent = ctypes.windll.user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
        return int(sent) == 2

    def _change_endpoint_volume(self, action: str) -> bool:
        if os.name != "nt":
            return False
        try:
            return _EndpointVolumeController().apply(action)
        except Exception:
            return False


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]

    def __init__(self, value: str) -> None:
        import uuid

        parsed = uuid.UUID(value)
        data4 = (wintypes.BYTE * 8).from_buffer_copy(parsed.bytes[8:])
        super().__init__(parsed.time_low, parsed.time_mid, parsed.time_hi_version, data4)


class _EndpointVolumeController:
    VOLUME_DELTA = MediaControl.VOLUME_DELTA
    CLSCTX_ALL = 0x17
    E_RENDER = 0
    E_CONSOLE = 0
    COINIT_APARTMENTTHREADED = 0x2
    RPC_E_CHANGED_MODE = 0x80010106

    CLSID_MM_DEVICE_ENUMERATOR = _GUID("bcde0395-e52f-467c-8e3d-c4579291692e")
    IID_IMM_DEVICE_ENUMERATOR = _GUID("a95664d2-9614-4f35-a746-de8db63617e6")
    IID_IAUDIO_ENDPOINT_VOLUME = _GUID("5cdf2c82-841e-4546-9722-0cf74078229a")

    def apply(self, action: str) -> bool:
        if action not in {"up", "down", "mute"}:
            return False

        ole32 = ctypes.OleDLL("ole32")
        coinit_hr = ole32.CoInitializeEx(None, self.COINIT_APARTMENTTHREADED)
        should_uninit = coinit_hr in (0, 1)
        if coinit_hr not in (0, 1, self.RPC_E_CHANGED_MODE):
            return False

        enumerator = None
        device = None
        endpoint = None
        try:
            enumerator = self._create_device_enumerator(ole32)
            device = self._default_render_device(enumerator)
            endpoint = self._endpoint_volume(device)
            if action == "up":
                return self._change_volume_by(endpoint, self.VOLUME_DELTA)
            if action == "down":
                return self._change_volume_by(endpoint, -self.VOLUME_DELTA)
            return self._toggle_mute(endpoint)
        finally:
            for pointer in (endpoint, device, enumerator):
                if pointer:
                    self._release(pointer)
            if should_uninit:
                ole32.CoUninitialize()

    def _create_device_enumerator(self, ole32):
        enumerator = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(self.CLSID_MM_DEVICE_ENUMERATOR),
            None,
            self.CLSCTX_ALL,
            ctypes.byref(self.IID_IMM_DEVICE_ENUMERATOR),
            ctypes.byref(enumerator),
        )
        if hr != 0 or not enumerator.value:
            raise OSError("MMDeviceEnumerator is unavailable.")
        return enumerator

    def _default_render_device(self, enumerator):
        get_default = self._method(
            enumerator,
            4,
            ctypes.WINFUNCTYPE(
                ctypes.HRESULT,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_void_p),
            ),
        )
        device = ctypes.c_void_p()
        hr = get_default(enumerator, self.E_RENDER, self.E_CONSOLE, ctypes.byref(device))
        if hr != 0 or not device.value:
            raise OSError("Default render device is unavailable.")
        return device

    def _endpoint_volume(self, device):
        activate = self._method(
            device,
            3,
            ctypes.WINFUNCTYPE(
                ctypes.HRESULT,
                ctypes.c_void_p,
                ctypes.POINTER(_GUID),
                wintypes.DWORD,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            ),
        )
        endpoint = ctypes.c_void_p()
        hr = activate(
            device,
            ctypes.byref(self.IID_IAUDIO_ENDPOINT_VOLUME),
            self.CLSCTX_ALL,
            None,
            ctypes.byref(endpoint),
        )
        if hr != 0 or not endpoint.value:
            raise OSError("Endpoint volume is unavailable.")
        return endpoint

    def _change_volume_by(self, endpoint, delta: float) -> bool:
        get_volume = self._method(
            endpoint,
            9,
            ctypes.WINFUNCTYPE(
                ctypes.HRESULT,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_float),
            ),
        )
        set_volume = self._method(
            endpoint,
            7,
            ctypes.WINFUNCTYPE(
                ctypes.HRESULT,
                ctypes.c_void_p,
                ctypes.c_float,
                ctypes.c_void_p,
            ),
        )
        current = ctypes.c_float()
        if get_volume(endpoint, ctypes.byref(current)) != 0:
            return False
        next_value = min(1.0, max(0.0, float(current.value) + delta))
        return set_volume(endpoint, ctypes.c_float(next_value), None) == 0

    def _toggle_mute(self, endpoint) -> bool:
        get_mute = self._method(
            endpoint,
            15,
            ctypes.WINFUNCTYPE(
                ctypes.HRESULT,
                ctypes.c_void_p,
                ctypes.POINTER(wintypes.BOOL),
            ),
        )
        set_mute = self._method(
            endpoint,
            14,
            ctypes.WINFUNCTYPE(
                ctypes.HRESULT,
                ctypes.c_void_p,
                wintypes.BOOL,
                ctypes.c_void_p,
            ),
        )
        muted = wintypes.BOOL()
        if get_mute(endpoint, ctypes.byref(muted)) != 0:
            return False
        return set_mute(endpoint, wintypes.BOOL(not bool(muted.value)), None) == 0

    def _release(self, pointer) -> None:
        release = self._method(pointer, 2, ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p))
        release(pointer)

    def _method(self, pointer, index: int, prototype):
        vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return prototype(vtable[index])
