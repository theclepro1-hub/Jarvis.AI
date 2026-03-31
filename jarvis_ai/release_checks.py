from __future__ import annotations

import json
import re
from pathlib import Path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _extract_by_regex(path: Path, pattern: str, label: str) -> str:
    match = re.search(pattern, _read_text(path), re.MULTILINE)
    if not match:
        raise ValueError(f"{label} version marker not found in {path}")
    return str(match.group(1)).strip().lstrip("v")


def _extract_json_field(path: Path, field: str) -> str:
    data = json.loads(_read_text(path))
    return str(data.get(field, "") or "").strip().lstrip("v")


def check_version_consistency(root: Path | None = None) -> tuple[str, dict[str, str]]:
    project_root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    expected = _extract_by_regex(
        project_root / "jarvis_ai" / "branding.py",
        r'APP_VERSION\s*=\s*"([^"]+)"',
        "branding",
    )
    versions = {
        "jarvis.py": _extract_by_regex(
            project_root / "jarvis.py",
            r"Assistant v([0-9][0-9.]*)",
            "jarvis",
        ),
        "jarvis_ai/branding.py": expected,
        "JarvisAI.iss": _extract_by_regex(
            project_root / "JarvisAI.iss",
            r'#define MyAppVersion "([^"]+)"',
            "inno setup",
        ),
        "README.md": _extract_by_regex(
            project_root / "README.md",
            r"- Версия:\s*`([^`]+)`",
            "readme",
        ),
        "CHANGELOG.md": _extract_by_regex(
            project_root / "CHANGELOG.md",
            r"^## \[([0-9][0-9.]*)\]",
            "changelog",
        ),
        "TASKS.md": _extract_by_regex(
            project_root / "TASKS.md",
            r"^## Цель релиза ([0-9][0-9.]*)",
            "tasks",
        ),
        "updates.json": _extract_json_field(project_root / "updates.json", "version"),
    }
    return expected, versions


def assert_version_consistency(root: Path | None = None) -> tuple[str, dict[str, str]]:
    expected, versions = check_version_consistency(root=root)
    mismatches = {path: version for path, version in versions.items() if version != expected}
    if mismatches:
        details = ", ".join(f"{path}={version}" for path, version in sorted(mismatches.items()))
        raise AssertionError(f"Version mismatch against {expected}: {details}")
    return expected, versions


__all__ = ["assert_version_consistency", "check_version_consistency"]
