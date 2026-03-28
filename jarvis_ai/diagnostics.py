import json
import logging
import os
import sys
from datetime import datetime

from .branding import APP_LOGGER_NAME
from .runtime import resource_path
from .storage import fix_history_path

logger = logging.getLogger(APP_LOGGER_NAME)


def _short_exc(exc: Exception) -> str:
    msg = str(exc).strip()
    return f"{type(exc).__name__}: {msg[:180]}" if msg else type(exc).__name__

# =========================================================
# DIAGNOSTIC ASSISTANT (ИИ-диагностика и автоисправление)
# =========================================================
class DiagnosticAssistant:
    def __init__(self, parent_app):
        self.parent = parent_app
        self.history_file = fix_history_path()
        self.load_history()
        
    def load_history(self):
        self.history = []
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception:
                self.history = []
                
    def save_history(self):
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Save fix history error: {e}")
            
    def analyze_code(self):
        """Анализирует текущий код (файл jarvis.py) и возвращает предложения"""
        runtime_findings = self.analyze_runtime_only()
        source_candidates = []
        try:
            source_candidates.append(os.path.abspath(sys.argv[0]))
        except Exception:
            pass
        try:
            source_candidates.append(os.path.abspath(__file__))
        except Exception:
            pass
        if getattr(sys, "frozen", False):
            try:
                source_candidates.append(resource_path("jarvis.py"))
                source_candidates.append(resource_path("Jarvis.py"))
            except Exception:
                pass

        current_file = ""
        for candidate in source_candidates:
            c = str(candidate or "").strip()
            if c.lower().endswith(".py") and os.path.exists(c):
                current_file = c
                break

        if not current_file:
            if getattr(sys, "frozen", False):
                notes = ["Режим exe/installer: выполнена внутренняя диагностика без анализа исходника."]
            else:
                notes = ["Исходник недоступен для чтения. Выполнена внутренняя диагностика."]
            notes.extend(runtime_findings)
            return notes

        try:
            with open(current_file, "r", encoding="utf-8") as f:
                code = f.read()
        except Exception as e:
            notes = [f"Ошибка чтения файла: {e}", "Показаны результаты внутренней диагностики:"]
            notes.extend(runtime_findings)
            return notes

        suggestions = []
        
        if "def listen_task" in code:
            if "_mic_listen_lock" not in code:
                suggestions.append("Отсутствует блокировка _mic_listen_lock в listen_task, что может приводить к зависаниям.")
        if "speaking_lock" not in code:
            suggestions.append("Рекомендуется добавить блокировку speaking_lock для TTS.")
        if "self.recognizer.energy_threshold" in code and "1700" in code:
            pass  # убрано: "Порог энергии распознавания (1700) может быть занижен при шумном окружении."
        if "self.groq_client" in code and "self.groq_client = None" in code and "CONFIG['api_key']" not in code:
            suggestions.append("API ключ Groq не проверяется при инициализации.")
            
        if not suggestions:
            suggestions.append("Код выглядит корректно. Видимых проблем не обнаружено.")

        if runtime_findings:
            suggestions.append("Результаты внутренней диагностики:")
            suggestions.extend(runtime_findings)

        return suggestions

    def analyze_runtime_only(self):
        findings = []
        try:
            runtime_findings = self.parent.run_internal_diagnostics()
            findings.extend(runtime_findings)
        except Exception as e:
            findings.append(f"Ошибка внутренней диагностики: {_short_exc(e)}")
        if not findings:
            findings.append("Внутренняя диагностика: критичных ошибок не найдено.")
        return findings
    
    def apply_fix(self, fix_description):
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "fix": fix_description,
            "applied": True
        })
        self.save_history()
        return f"Исправление '{fix_description}' записано в историю. Для применения изменений перезапустите приложение."
    
    def get_history(self):
        return self.history

__all__ = ["DiagnosticAssistant"]
