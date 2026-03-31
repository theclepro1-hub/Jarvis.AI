from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any

from .branding import APP_LOGGER_NAME
from .structured_logging import log_event


logger = logging.getLogger(APP_LOGGER_NAME)
_HTTPX_PROXY_COMPAT_DONE = False


def _patch_proxy_kwarg(httpx_cls) -> bool:
    if httpx_cls is None:
        return False
    try:
        params = inspect.signature(httpx_cls.__init__).parameters
    except (TypeError, ValueError):
        return False
    if "proxies" in params or "proxy" not in params:
        return False
    if getattr(httpx_cls.__init__, "_jarvis_proxy_compat", False):
        return True

    original_init = httpx_cls.__init__

    def _patched_init(self, *args, **kwargs):
        if "proxies" in kwargs and "proxy" not in kwargs:
            kwargs["proxy"] = kwargs.pop("proxies")
        return original_init(self, *args, **kwargs)

    _patched_init._jarvis_proxy_compat = True
    httpx_cls.__init__ = _patched_init
    return True


def ensure_httpx_proxy_compat() -> bool:
    global _HTTPX_PROXY_COMPAT_DONE
    if _HTTPX_PROXY_COMPAT_DONE:
        return True

    try:
        import httpx
    except ImportError:
        _HTTPX_PROXY_COMPAT_DONE = True
        return False

    try:
        from httpx import _client as httpx_client
    except ImportError:
        httpx_client = None

    patched = False
    for cls in (
        getattr(httpx, "Client", None),
        getattr(httpx, "AsyncClient", None),
        getattr(httpx_client, "Client", None),
        getattr(httpx_client, "AsyncClient", None),
    ):
        try:
            patched = _patch_proxy_kwarg(cls) or patched
        except Exception as exc:
            log_event(
                logger,
                "bootstrap",
                "httpx_proxy_patch_failed",
                level=logging.WARNING,
                class_name=getattr(cls, "__name__", ""),
                error=str(exc),
            )

    if patched:
        log_event(logger, "bootstrap", "httpx_proxy_compat_enabled")
    _HTTPX_PROXY_COMPAT_DONE = True
    return patched


@dataclass(frozen=True)
class AppBootstrap:
    config_mgr: Any
    prompt_mgr: Any
    db: Any

    def build_context(self):
        from .app_context import AppContext

        return AppContext(
            config_mgr=self.config_mgr,
            prompt_mgr=self.prompt_mgr,
            db=self.db,
        )

    def prepare_runtime(self) -> None:
        ensure_httpx_proxy_compat()


__all__ = ["AppBootstrap", "ensure_httpx_proxy_compat"]
