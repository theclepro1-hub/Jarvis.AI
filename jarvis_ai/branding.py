APP_NAME = "JARVIS AI 2.0"
APP_VERSION = "20.0.0"
APP_DIR_NAME = "JarvisAI2"
APP_LOGGER_NAME = "JarvisAI2"
APP_USER_AGENT = f"{APP_DIR_NAME}/{APP_VERSION}"
APP_WINDOWS_APP_ID = "JarvisAI2.JARVIS"
APP_EXECUTABLE_BASENAME = "jarvis_ai_2"
APP_EXECUTABLE_NAME = f"{APP_EXECUTABLE_BASENAME}.exe"
APP_INSTALLER_NAME = "JarvisAI2_Setup.exe"
APP_RELEASE_BUNDLE_PREFIX = "JARVIS_AI_2_v"


def app_brand_name() -> str:
    return APP_NAME


def app_version_badge() -> str:
    return f"v{APP_VERSION}"


def app_title(section: str = "", with_version: bool = False) -> str:
    base = app_brand_name()
    if with_version:
        base = f"{base} {app_version_badge()}"
    if section:
        return f"{section} | {base}"
    return base


def app_dialog_title(section: str = "") -> str:
    if section:
        return f"{app_brand_name()} - {section}"
    return app_brand_name()
