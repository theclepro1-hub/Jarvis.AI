from dataclasses import dataclass
from typing import Any

from .state import CONFIG_MGR, PROMPT_MGR, db


@dataclass
class AppContext:
    config_mgr: Any
    prompt_mgr: Any
    db: Any
    controllers: Any = None


def build_app_context(config_mgr=None, prompt_mgr=None, db_manager=None) -> AppContext:
    return AppContext(
        config_mgr=config_mgr or CONFIG_MGR,
        prompt_mgr=prompt_mgr or PROMPT_MGR,
        db=db_manager or db,
    )


__all__ = ["AppContext", "build_app_context"]
