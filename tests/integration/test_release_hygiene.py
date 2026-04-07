from __future__ import annotations

from pathlib import Path


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
        Path("docs/RELEASE_READINESS.md"),
        Path("docs/RELEASE_22.0.0.md"),
    ]:
        assert relpath.exists()


def test_build_script_keeps_expected_release_inputs() -> None:
    build_script = Path("build/build_release.ps1").read_text(encoding="utf-8")

    assert "--collect-all PySide6" in build_script
    assert "--collect-all vosk" in build_script
    assert "MODEL_DOWNLOAD" in build_script
    assert "Test-ModelSourceReady" in build_script
    assert r"assets\\models\\$modelName" in build_script
    assert '--windowed `' in build_script
    assert '--onefile `' in build_script
    assert '--icon $iconPath' in build_script
