import json
import os
import shutil
import zipfile
from datetime import datetime
from typing import Dict, List, Tuple

from .storage import app_backup_dir, app_export_dir, config_path, custom_actions_path, db_path, fix_history_path, plugin_packs_dir


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _profile_sources():
    return [config_path(), db_path(), custom_actions_path(), fix_history_path()]


def _write_sources_to_archive(archive: zipfile.ZipFile, sources):
    for source in sources:
        if not os.path.exists(source):
            continue
        archive.write(source, arcname=os.path.basename(source))


def create_profile_backup() -> str:
    backup_root = app_backup_dir()
    backup_path = os.path.join(backup_root, f"jarvis_profile_backup_{_timestamp()}.zip")
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _write_sources_to_archive(archive, _profile_sources())
    return backup_path


def restore_profile_backup(backup_zip: str) -> Tuple[bool, str]:
    if not backup_zip or not os.path.exists(backup_zip):
        return False, "Файл backup не найден."
    try:
        with zipfile.ZipFile(backup_zip, "r") as archive:
            for name, target in {
                "config.json": config_path(),
                "jarvis_history.db": db_path(),
                "custom_actions.json": custom_actions_path(),
                "fix_history.json": fix_history_path(),
            }.items():
                if name in archive.namelist():
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with archive.open(name, "r") as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        return True, "Профиль восстановлен."
    except Exception as exc:
        return False, f"Ошибка восстановления: {exc}"


def create_update_snapshot(version_hint: str = "") -> str:
    backup_root = app_backup_dir()
    safe_hint = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(version_hint or "").strip()).strip("._")
    suffix = f"_{safe_hint}" if safe_hint else ""
    snapshot_path = os.path.join(backup_root, f"jarvis_update_snapshot{suffix}_{_timestamp()}.zip")
    with zipfile.ZipFile(snapshot_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _write_sources_to_archive(archive, _profile_sources())
        archive.writestr(
            "snapshot_meta.json",
            json.dumps(
                {
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "version_hint": str(version_hint or ""),
                    "kind": "pre_update_snapshot",
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    return snapshot_path


def list_update_snapshots(limit: int = 20) -> List[str]:
    backup_root = app_backup_dir()
    items = []
    for name in os.listdir(backup_root):
        if not name.startswith("jarvis_update_snapshot") or not name.endswith(".zip"):
            continue
        items.append(os.path.join(backup_root, name))
    items.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    return items[: max(1, int(limit or 1))]


def restore_latest_update_snapshot() -> Tuple[bool, str, str]:
    snapshots = list_update_snapshots(limit=1)
    if not snapshots:
        return False, "", "Снимок перед обновлением не найден."
    snapshot_path = snapshots[0]
    ok, message = restore_profile_backup(snapshot_path)
    return ok, snapshot_path, message


def export_diagnostics_bundle(extra_files: List[str] | None = None) -> str:
    export_root = app_export_dir()
    bundle_path = os.path.join(export_root, f"jarvis_diagnostics_{_timestamp()}.zip")
    candidates = [config_path(), db_path(), custom_actions_path(), fix_history_path()]
    if extra_files:
        candidates.extend([x for x in extra_files if x])
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in candidates:
            if path and os.path.exists(path):
                archive.write(path, arcname=os.path.basename(path))
    return bundle_path


def export_plugin_pack(payload: Dict[str, object], name_hint: str = "plugin_pack") -> str:
    pack_root = plugin_packs_dir()
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(name_hint or "plugin_pack")).strip("._") or "plugin_pack"
    pack_path = os.path.join(pack_root, f"{safe_name}_{_timestamp()}.json")
    with open(pack_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return pack_path


def import_plugin_pack(pack_path: str) -> Tuple[bool, Dict[str, object] | str]:
    if not pack_path or not os.path.exists(pack_path):
        return False, "Файл набора не найден."
    try:
        with open(pack_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return False, "Набор должен быть JSON-объектом."
        normalized = {
            "custom_apps": data.get("custom_apps", []) if isinstance(data.get("custom_apps", []), list) else [],
            "launcher_games": data.get("launcher_games", []) if isinstance(data.get("launcher_games", []), list) else [],
            "learned_commands": data.get("learned_commands", []) if isinstance(data.get("learned_commands", []), list) else [],
            "scenarios": data.get("scenarios", []) if isinstance(data.get("scenarios", []), list) else [],
            "memory": data.get("memory", []) if isinstance(data.get("memory", []), list) else [],
        }
        return True, normalized
    except Exception as exc:
        return False, f"Ошибка чтения набора: {exc}"


__all__ = [
    "create_profile_backup",
    "create_update_snapshot",
    "export_diagnostics_bundle",
    "export_plugin_pack",
    "import_plugin_pack",
    "list_update_snapshots",
    "restore_profile_backup",
    "restore_latest_update_snapshot",
]
