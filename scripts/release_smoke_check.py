#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
RELEASE_DIR = ROOT / "release"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    manifest_path = RELEASE_DIR / "manifest.json"
    updates_path = RELEASE_DIR / "updates.json"
    version_hint = ""
    if updates_path.exists():
        try:
            version_hint = str(json.loads(updates_path.read_text(encoding="utf-8-sig")).get("version", "") or "").strip()
        except Exception:
            version_hint = ""
    portable_name = f"JARVIS_AI_2_portable_v{version_hint}.zip" if version_hint else "JARVIS_AI_2_portable.zip"
    required = [
        RELEASE_DIR / "jarvis_ai_2.exe",
        RELEASE_DIR / "JarvisAI2_Setup.exe",
        RELEASE_DIR / portable_name,
        RELEASE_DIR / "CHANGELOG.md",
        RELEASE_DIR / "CRASH_TEST_REPORT.txt",
        RELEASE_DIR / "RELEASE_NOTES.md",
        manifest_path,
        updates_path,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print("Missing release files:")
        for item in missing:
            print(f"- {item}")
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    updates = json.loads(updates_path.read_text(encoding="utf-8-sig"))
    version = str(updates.get("version", "") or "").strip()
    if not version:
        print("updates.json version is missing")
        return 1
    if str(manifest.get("version", "") or "").strip() != version:
        print("manifest.json version does not match updates.json")
        return 1

    file_map = manifest.get("files", {})
    for name in ("jarvis_ai_2.exe", "JarvisAI2_Setup.exe", portable_name, "updates.json", "CHANGELOG.md", "RELEASE_NOTES.md"):
        entry = file_map.get(name)
        if not isinstance(entry, dict):
            print(f"manifest.json missing file entry: {name}")
            return 1
        path = RELEASE_DIR / entry.get("path", name)
        if not path.exists():
            print(f"manifest file path missing: {path}")
            return 1
        expected_sha = str(entry.get("sha256", "") or "").strip().lower()
        actual_sha = sha256(path).lower()
        if expected_sha != actual_sha:
            print(f"sha256 mismatch for {name}")
            return 1

    print("Release smoke check: OK")
    print(f"Version: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
