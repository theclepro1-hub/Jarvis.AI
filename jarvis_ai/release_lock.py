import json
import os
from typing import Dict, List


def _read_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _file_contains(path: str, marker: str) -> bool:
    return bool(marker and marker in _read_text(path))


def run_release_lock(project_root: str, version: str, exe_name: str, installer_name: str) -> Dict[str, object]:
    root = os.path.abspath(project_root or ".")
    checks: List[Dict[str, object]] = []

    def add(label: str, ok: bool, detail: str = ""):
        checks.append({"label": label, "ok": bool(ok), "detail": str(detail or "")})

    branding_path = os.path.join(root, "jarvis_ai", "branding.py")
    iss_path = os.path.join(root, "JarvisAI.iss")
    changelog_path = os.path.join(root, "CHANGELOG.md")
    readme_path = os.path.join(root, "README.md")
    updates_path = os.path.join(root, "updates.json")
    build_script = os.path.join(root, "build_release.ps1")
    publish_dir = os.path.join(root, "publish_tools")
    bundle_script = os.path.join(publish_dir, "build_and_prepare.ps1")

    add("branding.py exists", os.path.exists(branding_path), branding_path)
    add("JarvisAI.iss exists", os.path.exists(iss_path), iss_path)
    add("CHANGELOG.md exists", os.path.exists(changelog_path), changelog_path)
    add("README.md exists", os.path.exists(readme_path), readme_path)
    add("updates.json exists", os.path.exists(updates_path), updates_path)
    add("build_release.ps1 exists", os.path.exists(build_script), build_script)
    add("publish_tools/build_and_prepare.ps1 exists", os.path.exists(bundle_script), bundle_script)

    add("branding version synced", _file_contains(branding_path, f'APP_VERSION = "{version}"'), version)
    add("installer version synced", _file_contains(iss_path, f'#define MyAppVersion "{version}"'), version)
    add("changelog mentions version", _file_contains(changelog_path, f"## [{version}]"), version)
    add("readme mentions version", _file_contains(readme_path, f"`{version}`"), version)
    add("updates mentions version", _file_contains(updates_path, f'"version":  "{version}"') or _file_contains(updates_path, f'"version": "{version}"'), version)
    add("readme mentions executable", _file_contains(readme_path, exe_name), exe_name)
    add("readme mentions installer", _file_contains(readme_path, installer_name), installer_name)

    try:
        parsed = json.loads(_read_text(updates_path) or "{}")
        add("updates executable matches", str(parsed.get("executable_name", "") or "").strip() == exe_name, str(parsed.get("executable_name", "")))
        add("updates installer matches", str(parsed.get("installer_name", "") or "").strip() == installer_name, str(parsed.get("installer_name", "")))
    except Exception as exc:
        add("updates.json parse", False, str(exc))

    ok = all(bool(item.get("ok")) for item in checks)
    return {"ok": ok, "checks": checks, "version": version, "exe_name": exe_name, "installer_name": installer_name}


def format_release_lock_report(result: Dict[str, object]) -> str:
    lines = [
        "Проверка релиза",
        "============",
        f"Version: {result.get('version', '')}",
        f"Status: {'OK' if result.get('ok') else 'FAILED'}",
        "",
    ]
    for item in result.get("checks", []):
        prefix = "[OK]" if item.get("ok") else "[FAIL]"
        detail = str(item.get("detail", "") or "").strip()
        if detail:
            lines.append(f"{prefix} {item.get('label')} :: {detail}")
        else:
            lines.append(f"{prefix} {item.get('label')}")
    return "\n".join(lines).strip() + "\n"


__all__ = ["format_release_lock_report", "run_release_lock"]
