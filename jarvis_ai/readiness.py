from datetime import datetime
from typing import Dict, List

from .branding import APP_VERSION
from .voice_profiles import device_profile_kind


def build_readiness_report(app) -> Dict[str, object]:
    cfg = getattr(app, "config_mgr", None)
    checks: List[Dict[str, object]] = []

    def add(name: str, ok: bool, summary: str, fix: str = ""):
        checks.append({
            "name": name,
            "ok": bool(ok),
            "summary": str(summary or ""),
            "fix": str(fix or ""),
        })

    api_key = bool(str(cfg.get_api_key() or "").strip()) if cfg else False
    mic_name = str(getattr(app, "get_selected_microphone_name", lambda: "")() or "").strip()
    output_name = str(getattr(app, "get_selected_output_name", lambda: "")() or "").strip()
    tts_provider = str(cfg.get_tts_provider() or "pyttsx3").strip() if cfg else "pyttsx3"
    channel = str(cfg.get_release_channel() or "stable").strip() if cfg else "stable"
    listening_profile = str(cfg.get_listening_profile() or "normal").strip() if cfg else "normal"
    device_kind = device_profile_kind(mic_name)
    is_online = bool(getattr(app, "is_online", False))
    proxy_detected = bool(getattr(app, "proxy_detected", False))

    add(
        "Groq AI",
        api_key,
        "Ключ Groq настроен." if api_key else "Ключ Groq не настроен.",
        "Откройте Настройки -> ИИ и профиль и вставьте Groq API ключ." if not api_key else "",
    )
    add(
        "Интернет",
        is_online,
        "Сеть доступна." if is_online else "Сети нет или она нестабильна.",
        "Проверьте интернет, VPN/Proxy и повторите проверку готовности." if not is_online else "",
    )
    add(
        "Микрофон",
        bool(mic_name),
        mic_name if mic_name else "Микрофон не выбран.",
        "Откройте Настройки -> Аудио и выберите устройство ввода." if not mic_name else "",
    )
    add(
        "Вывод звука",
        bool(output_name),
        output_name if output_name else "Устройство вывода не выбрано.",
        "Откройте Настройки -> Аудио и выберите устройство вывода." if not output_name else "",
    )
    add(
        "TTS",
        bool(tts_provider),
        f"Провайдер голоса: {tts_provider}.",
        "Проверьте voice/TTS блок в настройках." if not tts_provider else "",
    )
    add(
        "Слышимость",
        True,
        f"Профиль: {listening_profile}; тип устройства: {device_kind}.",
        "Запустите автокалибровку и обучение слышимости, если слово активации реагирует слабо.",
    )
    add(
        "Release канал",
        channel in {"stable", "beta"},
        f"Активный канал: {channel}.",
        "Верните канал на stable для официального релиза." if channel != "stable" else "",
    )
    add(
        "Recovery",
        bool(cfg.get_auto_recovery_enabled()) if cfg else False,
        "Автовосстановление fallback-ов включено." if cfg and cfg.get_auto_recovery_enabled() else "Автовосстановление выключено.",
        "Включите auto recovery в расширенных настройках." if cfg and not cfg.get_auto_recovery_enabled() else "",
    )
    add(
        "Proxy/VPN adaptation",
        True,
        "Адаптация под VPN/Proxy активна." if proxy_detected else "Proxy/VPN не обнаружен, используется обычный сетевой профиль.",
        "",
    )

    passed = sum(1 for item in checks if item["ok"])
    total = len(checks)
    summary = f"Готовность {passed}/{total} • версия {APP_VERSION}"
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary,
        "passed": passed,
        "total": total,
        "checks": checks,
    }


def format_readiness_report(report: Dict[str, object]) -> str:
    lines = [
        f"Проверка готовности: {report.get('generated_at', '')}",
        str(report.get("summary", "")).strip(),
        "",
    ]
    for item in report.get("checks", []):
        prefix = "OK" if item.get("ok") else "FAIL"
        lines.append(f"[{prefix}] {item.get('name')}: {item.get('summary')}")
        fix = str(item.get("fix", "") or "").strip()
        if fix:
            lines.append(f"  Что сделать: {fix}")
    return "\n".join(lines).strip() + "\n"


__all__ = ["build_readiness_report", "format_readiness_report"]
