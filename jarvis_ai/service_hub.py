from dataclasses import dataclass
from typing import Any

from .state import CONFIG_MGR


@dataclass
class ServiceHub:
    groq_client: Any = None
    reminder_scheduler: Any = None
    telegram_bot: Any = None
    diagnostic_assistant: Any = None


def build_service_hub(
    app,
    groq_cls,
    reminder_cls,
    telegram_cls,
    diagnostic_cls,
    telegram_enabled: bool = True,
    config_mgr=None,
    context=None,
) -> ServiceHub:
    ctx = context or getattr(app, "app_context", None)
    cfg = config_mgr or getattr(ctx, "config_mgr", None) or getattr(app, "config_mgr", None) or CONFIG_MGR
    api_key = str(cfg.get_api_key() or "").strip()
    telegram_token = cfg.get_telegram_token()
    telegram_user_id = cfg.get_telegram_user_id()
    display_name = cfg.get_user_name()

    return ServiceHub(
        groq_client=groq_cls(api_key=api_key) if groq_cls and api_key else None,
        reminder_scheduler=reminder_cls(app.on_reminder) if reminder_cls else None,
        telegram_bot=telegram_cls(
            telegram_token,
            telegram_user_id,
            app.process_telegram_query,
            display_name=display_name,
        ) if telegram_cls and telegram_enabled else None,
        diagnostic_assistant=diagnostic_cls(app) if diagnostic_cls else None,
    )


__all__ = ["ServiceHub", "build_service_hub"]
