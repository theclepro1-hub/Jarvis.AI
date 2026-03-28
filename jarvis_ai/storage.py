import os

import appdirs

from .branding import APP_DIR_NAME


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def app_config_dir() -> str:
    return _ensure(appdirs.user_config_dir(APP_DIR_NAME, appauthor=False))


def app_data_dir() -> str:
    return _ensure(appdirs.user_data_dir(APP_DIR_NAME, appauthor=False))


def app_log_dir() -> str:
    return _ensure(appdirs.user_log_dir(APP_DIR_NAME, appauthor=False))


def app_backup_dir() -> str:
    return _ensure(os.path.join(app_data_dir(), "backups"))


def app_export_dir() -> str:
    return _ensure(os.path.join(app_data_dir(), "exports"))


def config_path() -> str:
    return os.path.join(app_config_dir(), "config.json")


def db_path() -> str:
    return os.path.join(app_data_dir(), "jarvis_history.db")


def prompts_dir() -> str:
    return _ensure(os.path.join(app_data_dir(), "prompts"))


def fix_history_path() -> str:
    return os.path.join(app_data_dir(), "fix_history.json")


def update_status_path() -> str:
    return os.path.join(app_data_dir(), "update_status.json")


def custom_actions_path() -> str:
    return os.path.join(app_config_dir(), "custom_actions.json")


def plugin_packs_dir() -> str:
    return _ensure(os.path.join(app_config_dir(), "plugin_packs"))
