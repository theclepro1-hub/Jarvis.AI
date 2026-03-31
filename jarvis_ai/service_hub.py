import logging
from dataclasses import dataclass
from typing import Any

from .bootstrap import ensure_httpx_proxy_compat
from .branding import APP_LOGGER_NAME
from .structured_logging import log_event

logger = logging.getLogger(APP_LOGGER_NAME)


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
    cfg = config_mgr or getattr(ctx, "config_mgr", None) or getattr(app, "config_mgr", None)
    if cfg is None:
        raise ValueError("build_service_hub requires an explicit config manager via app_context, app.config_mgr, or config_mgr")

    api_key = str(cfg.get_api_key() or "").strip()
    telegram_token = cfg.get_telegram_token()
    telegram_user_id = cfg.get_telegram_user_id()
    display_name = cfg.get_user_name()

    def _build_groq_client(cls, key):
        if not cls or not key:
            return None
        ensure_httpx_proxy_compat()
        try:
            return cls(api_key=key)
        except Exception as exc:
            log_event(
                logger,
                "bootstrap",
                "groq_client_init_failed",
                level=logging.ERROR,
                error=str(exc),
                has_api_key=bool(key),
            )
            logger.error("Groq client initialization failed: %s", exc, exc_info=True)
            return None

    return ServiceHub(
        groq_client=_build_groq_client(groq_cls, api_key),
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
