import re
from typing import Iterable, Optional
from urllib.parse import urlparse


DEFAULT_RELEASE_NOTE = "Техническое обслуживание и улучшение стабильности."


def version_tuple(version: str):
    nums = []
    for part in re.findall(r"\d+", str(version or "")):
        try:
            nums.append(int(part))
        except Exception:
            nums.append(0)
    return tuple(nums) if nums else (0,)


def is_newer_version(current: str, latest: str) -> bool:
    return version_tuple(latest) > version_tuple(current)


def normalize_trusted_hosts(hosts: Optional[Iterable[str]]):
    result = []
    for host in hosts or []:
        normalized = str(host or "").strip().lower()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def is_trusted_update_url(url: str, trusted_hosts: Optional[Iterable[str]]) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host:
            return False
        for allowed in normalize_trusted_hosts(trusted_hosts):
            if host == allowed or host.endswith(f".{allowed}"):
                return True
        return False
    except Exception:
        return False


def extract_sha256(value: str):
    if not value:
        return ""
    match = re.search(r"(?i)(?:sha256[:=\s]+)?([a-f0-9]{64})", str(value))
    return match.group(1).lower() if match else ""


def is_installer_asset_name(name: str, installer_hints: Optional[Iterable[str]] = None) -> bool:
    low_name = str(name or "").strip().lower()
    if not low_name:
        return False
    if low_name.endswith(".msi"):
        return True
    if not low_name.endswith(".exe"):
        return False
    known_hints = [
        "setup",
        "installer",
        "jarvisai_setup",
        "jarvisai2_setup",
        "jarvis_ai_2_setup",
    ]
    for hint in installer_hints or []:
        normalized = str(hint or "").strip().lower()
        if normalized:
            known_hints.append(normalized)
    return (
        any(hint in low_name for hint in known_hints)
        or low_name.endswith("_setup.exe")
        or low_name.endswith("-setup.exe")
    )


def pick_release_asset(
    assets: list,
    *,
    is_frozen: bool = False,
    preferred_name: str = "",
    configured_asset_name: str = "",
    installer_hints: Optional[Iterable[str]] = None,
):
    if not isinstance(assets, list):
        return None
    preferred_exts = (".exe", ".msi") if is_frozen else (".zip", ".py", ".exe")
    chosen = None
    configured_asset_name = str(configured_asset_name or "").strip().lower()
    preferred_name_low = str(preferred_name or "").strip().lower()

    if preferred_name_low:
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name", "") or "").strip()
            if name.lower() == preferred_name_low:
                chosen = asset
                break

    if chosen is None and configured_asset_name:
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name", "") or "").strip()
            if configured_asset_name in name.lower():
                chosen = asset
                break

    if chosen is None and is_frozen:
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name", "") or "").strip()
            if is_installer_asset_name(name, installer_hints=installer_hints):
                chosen = asset
                break

    if chosen is None:
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name", "") or "").strip().lower()
            if any(name.endswith(ext) for ext in preferred_exts):
                chosen = asset
                break

    if chosen is None:
        for asset in assets:
            if isinstance(asset, dict):
                chosen = asset
                break

    if not isinstance(chosen, dict):
        return None

    name = str(chosen.get("name", "") or "")
    asset_kind = "installer" if is_installer_asset_name(name, installer_hints=installer_hints) else "portable"
    return {
        "name": name,
        "download_url": str(chosen.get("browser_download_url", "") or "").strip(),
        "sha256": extract_sha256(chosen.get("label", "")),
        "kind": asset_kind,
    }


def format_release_notes_for_chat(notes: str, max_items: int = 6) -> str:
    cleaned = []
    for raw in str(notes or "").splitlines():
        line = str(raw or "").strip()
        if not line:
            continue
        line = re.sub(r"^[#>\-\*\u2022\s]+", "", line).strip()
        if not line:
            continue
        if len(line) > 180:
            line = line[:177] + "..."
        cleaned.append(f"• {line}")
        if len(cleaned) >= max_items:
            break
    if not cleaned:
        return f"• {DEFAULT_RELEASE_NOTE}"
    return "\n".join(cleaned)
