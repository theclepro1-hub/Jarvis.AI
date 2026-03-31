from __future__ import annotations

from typing import Dict, List

from .audio_devices import list_input_device_entries_safe, list_output_device_entries_safe
from .audio_runtime import describe_ffmpeg_runtime, ffmpeg_runtime_status
from .custom_actions import load_custom_action_entries


def _item(status: str, title: str, detail: str, fix: str = "") -> Dict[str, str]:
    return {
        "status": str(status or "info").strip().lower(),
        "title": str(title or "").strip(),
        "detail": str(detail or "").strip(),
        "fix": str(fix or "").strip(),
    }


def run_environment_doctor(app) -> List[Dict[str, str]]:
    cfg = app._cfg()
    items: List[Dict[str, str]] = []

    api_key = str(cfg.get_api_key() or "").strip()
    if api_key:
        items.append(_item("ok", "Ключ Groq", "Ключ Groq задан."))
    else:
        items.append(_item("error", "Ключ Groq", "Ключ Groq не задан.", "Откройте раздел ИИ и профиль и вставьте актуальный ключ Groq API."))

    telegram_token = str(cfg.get_telegram_token() or "").strip()
    telegram_user_id = int(cfg.get_telegram_user_id() or 0)
    if telegram_token and telegram_user_id:
        items.append(_item("ok", "Telegram", "Токен бота и ID пользователя заполнены."))
    elif telegram_token or telegram_user_id:
        items.append(_item("warn", "Telegram", "Telegram настроен частично.", "Либо заполните токен и ID пользователя вместе, либо очистите оба поля."))
    else:
        items.append(_item("info", "Telegram", "Telegram не настроен. Это нормально, если удалённое управление не нужно."))

    input_devices = list_input_device_entries_safe()
    selected_mic = str(getattr(app, "get_selected_microphone_name", lambda: cfg.get_mic_device_name())() or "").strip()
    if input_devices:
        if selected_mic:
            items.append(_item("ok", "Микрофон", f"Найдено устройств ввода: {len(input_devices)}. Выбран: {selected_mic}."))
        else:
            items.append(_item("warn", "Микрофон", f"Найдено устройств ввода: {len(input_devices)}, но микрофон не выбран.", "Нажмите Авто-микрофон в главном окне или откройте Центр голоса."))
    else:
        items.append(_item("error", "Микрофон", "Устройства ввода не найдены.", "Проверьте подключение микрофона и разрешения Windows на доступ к нему."))

    output_devices = list_output_device_entries_safe()
    selected_output = str(cfg.get_output_device_name() or "").strip()
    if output_devices:
        if selected_output:
            items.append(_item("ok", "Аудиовывод", f"Найдено устройств вывода: {len(output_devices)}. Выбрано: {selected_output}."))
        else:
            items.append(_item("warn", "Аудиовывод", f"Найдено устройств вывода: {len(output_devices)}, но устройство не выбрано.", "Откройте ИИ и профиль и выберите устройство вывода для TTS."))
    else:
        items.append(_item("warn", "Аудиовывод", "Системные устройства вывода не обнаружены.", "Проверьте аудиодрайверы и подключение колонок/наушников."))

    provider = str(cfg.get_tts_provider() or "pyttsx3").strip().lower()
    if hasattr(app, "_tts_provider_ready_details"):
        ready, reason = app._tts_provider_ready_details(provider)
    else:
        ready, reason = True, ""
    if ready:
        items.append(_item("ok", "Озвучка", f"Провайдер озвучки готов: {provider}."))
    else:
        items.append(_item("error", "Озвучка", f"Провайдер озвучки {provider} не готов: {reason or 'нет деталей'}", "Переключитесь на pyttsx3 или заполните недостающие ключи или зависимости."))

    ffmpeg_info = ffmpeg_runtime_status()
    has_ffmpeg = bool(ffmpeg_info.get("has_ffmpeg"))
    has_ffplay = bool(ffmpeg_info.get("has_ffplay"))
    runtime_label = describe_ffmpeg_runtime(ffmpeg_info)
    if has_ffmpeg and has_ffplay:
        items.append(_item("ok", "ffmpeg", f"Доступны инструменты: {runtime_label}."))
    elif has_ffmpeg or has_ffplay:
        items.append(_item("warn", "ffmpeg", f"Найден не весь набор ffmpeg: {runtime_label}.", "Добавьте полный ffmpeg в PATH, чтобы Edge-TTS, Doctor и аудиопроверки работали стабильнее."))
    else:
        items.append(_item("warn", "ffmpeg", "ffmpeg не найден в PATH.", "Установите ffmpeg и ffplay, затем перезапустите JARVIS. Без них онлайн-озвучка и часть диагностических проверок будут ограничены."))

    try:
        online = bool(app.check_internet())
    except Exception:
        online = False
    if online:
        items.append(_item("ok", "Сеть", "Сетевое подключение доступно."))
    else:
        items.append(_item("warn", "Сеть", "Сеть сейчас недоступна или нестабильна.", "Проверьте интернет, DNS и VPN/Proxy."))

    custom_actions = load_custom_action_entries()
    if custom_actions:
        items.append(_item("ok", "Пользовательские действия", f"Загружено действий из манифеста: {len(custom_actions)} шт."))
    else:
        items.append(_item("info", "Пользовательские действия", "Пользовательские действия пока не настроены.", "Добавьте действия в визуальном редакторе или через custom_actions.json."))

    if getattr(app, "proxy_detected", False):
        items.append(_item("info", "Proxy/VPN", "В окружении обнаружен proxy/VPN.", "Если JARVIS периодически уходит в оффлайн, временно отключите proxy/VPN и повторите проверку."))

    return items


def doctor_summary(items: List[Dict[str, str]]) -> str:
    error_count = sum(1 for item in items if item.get("status") == "error")
    warn_count = sum(1 for item in items if item.get("status") == "warn")
    ok_count = sum(1 for item in items if item.get("status") == "ok")
    return f"Проверка среды: ок {ok_count} • предупреждений {warn_count} • ошибок {error_count}"


def render_doctor_report(items: List[Dict[str, str]]) -> str:
    rows = [doctor_summary(items), ""]
    for index, item in enumerate(items, 1):
        status = str(item.get("status") or "info").upper()
        rows.append(f"{index}. [{status}] {item.get('title', '')}")
        rows.append(str(item.get("detail", "")).strip())
        fix = str(item.get("fix", "")).strip()
        if fix:
            rows.append("Что сделать: " + fix)
        rows.append("")
    return "\n".join(rows).strip()


__all__ = ["doctor_summary", "render_doctor_report", "run_environment_doctor"]
