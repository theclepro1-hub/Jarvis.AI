from __future__ import annotations

from pathlib import Path

from core.updates.update_service import UpdateService


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
    ]

    for pattern in expected_patterns:
        assert pattern in gitignore


def test_release_docs_exist() -> None:
    for relpath in [
        Path("docs/SECURITY.md"),
        Path("docs/AI_NETWORK.md"),
        Path("docs/RELEASE_READINESS.md"),
        Path("docs/RELEASE_22.4.0.md"),
    ]:
        assert relpath.exists()


def test_build_script_keeps_expected_release_inputs() -> None:
    build_script = Path("build/build_release.ps1").read_text(encoding="utf-8")

    assert "--collect-all vosk" in build_script
    assert "--hidden-import win32com.client" in build_script
    assert "--hidden-import pythoncom" in build_script
    assert "MODEL_DOWNLOAD" in build_script
    assert "Test-ModelSourceReady" in build_script
    assert "Invoke-RetryDownload" in build_script
    assert "Write-ChecksumFile" in build_script
    assert "Assert-ChecksumFile" in build_script
    assert "Get-FileHash" in build_script
    assert r"assets\\models\\$modelName" in build_script
    assert "am\\final.mdl" in build_script
    assert "conf\\model.conf" in build_script
    assert "graph\\Gr.fst" in build_script
    assert "ivector\\final.ie" in build_script
    assert '--windowed `' in build_script
    assert '--onefile `' in build_script
    assert '--icon $iconPath' in build_script
    assert '--version-file $versionInfoFile' in build_script
    assert "RELEASE_VERSION $version" in build_script
    assert 'AppUserModelID: "theclepro1.JarvisAiUnity"' in build_script
    assert "UninstallDisplayIcon={app}\\JarvisAi_Unity.exe" in build_script
    assert "UninstallDisplayName=JARVIS Unity" in build_script
    assert "CloseApplications=yes" in build_script
    assert "CloseApplicationsFilter=JarvisAi_Unity.exe" in build_script
    assert "SetupMutex=JarvisAi_Unity_22_setup_mutex" in build_script
    assert "VersionInfoTextVersion=$version" in build_script
    assert 'Type: filesandordirs; Name: "{app}"' in build_script


def test_installer_metadata_matches_runtime_identity() -> None:
    installer_script = Path("build/installer/JarvisAi_Unity.iss").read_text(encoding="utf-8")
    bootstrap = Path("app/bootstrap.py").read_text(encoding="utf-8")
    current_version = UpdateService().current_version

    assert f"AppVersion={current_version}" in installer_script
    assert f"AppVerName=JARVIS Unity {current_version}" in installer_script
    assert f"VersionInfoProductVersion={current_version}" in installer_script
    assert f"VersionInfoTextVersion={current_version}" in installer_script
    assert "UninstallDisplayName=JARVIS Unity" in installer_script
    assert "AppId={{5E8E34A2-7D82-4B23-8B6A-2D12F795C2A9}}" in installer_script
    assert 'AppUserModelID: "theclepro1.JarvisAiUnity"' in installer_script
    assert "AppMutex=JarvisAi_Unity_22_instance_mutex" in installer_script
    assert "SetupMutex=JarvisAi_Unity_22_setup_mutex" in installer_script
    assert "CloseApplicationsFilter=JarvisAi_Unity.exe" in installer_script
    assert 'Type: filesandordirs; Name: "{app}"' in installer_script
    assert "AppUserModelID" in installer_script
    assert 'WINDOWS_APP_USER_MODEL_ID = "theclepro1.JarvisAiUnity"' in bootstrap
    assert 'WINDOWS_APP_DISPLAY_NAME = "JARVIS Unity"' in bootstrap
    assert "QGuiApplication.setApplicationVersion(WINDOWS_APP_VERSION)" in bootstrap
