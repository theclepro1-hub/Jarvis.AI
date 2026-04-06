from __future__ import annotations

from openai import OpenAI


SYSTEM_PROMPT = """
Ты JARVIS Unity.
Отвечай быстро, умно и по делу.
Если пользователь просит бытовое действие или компьютерную команду, не болтай лишнего.
Если не хватает данных, задай короткий вопрос.
Тон: спокойный, взрослый, уверенный.
""".strip()


class AIService:
    def __init__(self, settings_service) -> None:
        self.settings = settings_service

    def generate_reply(self, user_text: str, history: list[dict[str, str]] | None = None) -> str:
        registration = self.settings.get_registration()
        api_key = registration.get("groq_api_key", "").strip()
        if not api_key:
            return self._fallback_reply(user_text)

        try:
            client = OpenAI(
                api_key=api_key,
                base_url="https://api.groq.com/openai/v1",
            )
            response = client.responses.create(
                model=self.settings.get("ai_model", "openai/gpt-oss-20b"),
                input=self._build_prompt(user_text, history or []),
            )
            if getattr(response, "output_text", ""):
                return response.output_text.strip()
        except Exception:
            return self._fallback_reply(user_text)
        return self._fallback_reply(user_text)

    def _build_prompt(self, user_text: str, history: list[dict[str, str]]) -> str:
        condensed_history = "\n".join(
            f"{item['role']}: {item['text']}" for item in history[-6:] if item["role"] != "system"
        )
        return f"{SYSTEM_PROMPT}\n\nКонтекст:\n{condensed_history}\n\nПользователь: {user_text}"

    def _fallback_reply(self, user_text: str) -> str:
        lower = user_text.lower()
        if "кто ты" in lower:
            return "Я JARVIS Unity. Новый тихий desktop-ассистент, собранный вокруг диалога, голоса и быстрых действий."
        if "настрой" in lower or "регистрац" in lower:
            return "Откройте регистрацию или настройки. Я проведу по ключам Groq и Telegram без лишних экранов."
        return "Понял. Я пока работаю в базовом режиме без подключённого Groq API, но уже могу вести диалог и выполнять локальные действия."
