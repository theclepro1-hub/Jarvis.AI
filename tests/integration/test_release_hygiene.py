from __future__ import annotations

import tomllib
from pathlib import Path

from core.app_identity import (
    WINDOWS_APP_DISPLAY_NAME,
    WINDOWS_APP_USER_MODEL_ID,
    WINDOWS_EXECUTABLE_NAME,
    WINDOWS_INSTANCE_MUTEX,
    WINDOWS_INSTANCE_SERVER,
    WINDOWS_SETUP_MUTEX,
)
from core.services.single_instance import SingleInstanceService
from core.updates.update_service import UpdateService
from core.version import DEFAULT_VERSION, DISPLAY_VERSION, UPDATE_VERSION
from tools.release_metadata import render_installer_script


def test_gitignore_covers_release_and_runtime_temp_artifacts() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    expected_patterns = [
        "build/pyinstaller/",
        "build/pyinstaller_onefile/",
        "build/release/",
        "build/model_cache/",
        "build/ui_probe/",
        "build/ui_probe2/",
        "build/ui_probe3/",
        "build/*probe*/",
        "build/*pass*/",
        "build/*review*/",
        "build/*verify*/",
        "build/*fix*/",
        "build/*audit*/",
        "build/*data/",
        "build/*data*/",
        "build/*runtime*/",
        "build/smoke_runtime/",
        "dist_onefile/",
        "JarvisAi_Unity.spec",
    ]

    for pattern in expected_patterns:
        assert pattern in gitignore


def test_release_docs_exist() -> None:
    for relpath in [
        Path("docs/SECURITY.md"),
        Path("docs/AI_NETWORK.md"),
        Path("docs/RELEASE_READINESS.md"),
        Path(f"docs/RELEASE_{DEFAULT_VERSION}.md"),
    ]:
        assert relpath.exists()


def test_project_version_is_sourced_from_core_version() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    update_service = UpdateService()

    assert DEFAULT_VERSION == DISPLAY_VERSION == update_service.current_version
    assert update_service.status_snapshot()["current_update_version"] == UPDATE_VERSION
    assert project.get("dynamic", []) == ["version"]
    assert pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "core.version.DEFAULT_VERSION"


def test_build_script_keeps_expected_release_inputs() -> None:
    build_script = Path("build/build_release.ps1").read_text(encoding="utf-8")

    assert not Path("JarvisAi_Unity.spec").exists()
    assert "--collect-all vosk" not in build_script
    assert "win32com.client" in build_script
    assert "pythoncom" in build_script
    assert "LOCAL_STT_MODEL_PREWARM" in build_script
    assert "Resolve-LocalSTTModelPath" in build_script
    assert "Patch-PyInstallerSpec" in build_script
    assert "pyi-makespec.exe" in build_script
    assert "Write-ZipArchive" in build_script
    assert "load_faster_whisper_model" in build_script
    assert "preseed_faster_whisper_model" in build_script
    assert "resolve_local_faster_whisper_model" in build_script
    assert "QtQuick" in build_script
    assert "designer" in build_script
    assert "Write-ChecksumFile" in build_script
    assert "Assert-ChecksumFile" in build_script
    assert "Get-FileHash" in build_script
    assert "Compress-Archive -Path $portableDistPath" not in build_script
    assert r"assets\\models\\faster-whisper" in build_script
    assert "release_metadata.py" in build_script
    assert 'Assert-NativeSuccess -Step "Installer metadata render"' in build_script
    assert "alphacephei.com/vosk" not in build_script
    assert "vosk-model-small-ru-0.22" not in build_script
    assert '"--collect-all", "faster_whisper"' in build_script
    assert '"--windowed"' in build_script
    assert '--onefile' in build_script
    assert '"--icon", $iconPath' in build_script
    assert '"--version-file", $versionInfoFile' in build_script
    assert "RELEASE_VERSION $version" in build_script
    assert "SetupMutex=JarvisAi_Unity_setup_mutex" in build_script


def test_installer_metadata_matches_runtime_identity() -> None:
    bootstrap = Path("app/bootstrap.py").read_text(encoding="utf-8")
    current_version = DEFAULT_VERSION

    installer_script = render_installer_script(
        version=current_version,
        release_dir=r"C:\JarvisAi_Unity\build\release",
        icon_path=r"C:\JarvisAi_Unity\assets\icons\jarvis_unity.ico",
        portable_dist_path=r"C:\JarvisAi_Unity\dist\JarvisAi_Unity",
    )

    assert current_version == DEFAULT_VERSION
    assert f"AppVersion={current_version}" in installer_script
    assert f"AppVerName={WINDOWS_APP_DISPLAY_NAME} {current_version}" in installer_script
    assert f"VersionInfoProductVersion={current_version}" in installer_script
    assert f"VersionInfoTextVersion={current_version}" in installer_script
    assert f"UninstallDisplayName={WINDOWS_APP_DISPLAY_NAME}" in installer_script
    assert f'AppUserModelID: "{WINDOWS_APP_USER_MODEL_ID}"' in installer_script
    assert f"AppMutex={WINDOWS_INSTANCE_MUTEX}" in installer_script
    assert f"SetupMutex={WINDOWS_SETUP_MUTEX}" in installer_script
    assert f"CloseApplicationsFilter={WINDOWS_EXECUTABLE_NAME}" in installer_script
    assert 'Type: filesandordirs; Name: "{app}"' in installer_script
    assert "from core.app_identity import WINDOWS_APP_DISPLAY_NAME, WINDOWS_APP_USER_MODEL_ID, WINDOWS_APP_VERSION" in bootstrap
    assert "QGuiApplication.setApplicationVersion(WINDOWS_APP_VERSION)" in bootstrap


def test_single_instance_identity_is_versionless() -> None:
    assert WINDOWS_INSTANCE_SERVER == "JarvisAi_Unity_instance"
    assert "22" not in WINDOWS_INSTANCE_MUTEX
    assert "22" not in WINDOWS_SETUP_MUTEX
    assert SingleInstanceService().server_name == WINDOWS_INSTANCE_SERVER


def test_startup_modules_keep_heavy_imports_lazy() -> None:
    app_py = Path("app/app.py").read_text(encoding="utf-8")
    chat_bridge_py = Path("ui/bridge/chat_bridge.py").read_text(encoding="utf-8")
    app_lines = set(app_py.splitlines())
    chat_bridge_lines = set(chat_bridge_py.splitlines())

    assert "from core.services.service_container import ServiceContainer" not in app_lines
    assert "from PySide6.QtGui import QAction, QFontDatabase, QIcon" not in app_lines
    assert "from PySide6.QtQml import QQmlApplicationEngine" not in app_lines
    assert "from PySide6.QtWidgets import QMenu, QSystemTrayIcon" not in app_lines
    assert "from core.ai.reply_text import SUPPORTED_AI_MODES, sanitize_ai_reply_text" not in chat_bridge_lines
    assert "from core.policy.assistant_mode import resolve_assistant_mode" not in chat_bridge_lines


def test_owned_startup_files_have_no_stale_22x_tails() -> None:
    owned_text = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in [
            "app/app.py",
            "ui/bridge/chat_bridge.py",
            "tests/unit/test_app_bridge.py",
        ]
    )

    assert "22." not in owned_text
