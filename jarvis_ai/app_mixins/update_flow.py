import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from tkinter import messagebox
from urllib.parse import urlparse

from ..branding import APP_DIR_NAME, APP_INSTALLER_NAME, APP_LOGGER_NAME, APP_USER_AGENT, APP_VERSION
from ..profile_tools import create_update_snapshot, restore_latest_update_snapshot, restore_profile_backup
from ..release_meta import DEFAULT_GITHUB_REPO, DEFAULT_RELEASES_URL, DEFAULT_RELEASE_API_URL
from ..storage import update_status_path
from ..update_helpers import (
    extract_sha256,
    format_release_notes_for_chat,
    is_installer_asset_name,
    is_newer_version,
    is_trusted_update_url,
    normalize_trusted_hosts,
    pick_release_asset,
    version_tuple,
)
from ..utils import short_exc

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
logger = logging.getLogger(APP_LOGGER_NAME)


class UpdateFlowMixin:
    def _version_tuple(self, version: str):
        return version_tuple(version)

    def _is_newer_version(self, current: str, latest: str) -> bool:
        return is_newer_version(current, latest)

    def _trusted_update_hosts(self):
        return normalize_trusted_hosts(self.config_mgr.get_update_trusted_hosts() or [])

    def _is_trusted_update_url(self, url: str) -> bool:
        return is_trusted_update_url(url, self._trusted_update_hosts())

    def _rollback_state_path(self) -> str:
        return os.path.join(os.path.dirname(update_status_path()), "update_rollback.json")

    def _save_rollback_state(self, payload: dict):
        if not isinstance(payload, dict):
            return
        path = self._rollback_state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def rollback_last_update_action(self):
        rollback_path = self._rollback_state_path()
        snapshot_path = ""
        from_version = ""
        to_version = ""
        binary_backup = ""
        target_path = ""

        if os.path.exists(rollback_path):
            try:
                with open(rollback_path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                snapshot_path = str(payload.get("snapshot") or "").strip()
                from_version = str(payload.get("from_version") or "").strip()
                to_version = str(payload.get("to_version") or "").strip()
                binary_backup = str(payload.get("binary_backup") or "").strip()
                target_path = str(payload.get("target_path") or "").strip()
            except Exception as exc:
                logger.warning(f"Could not read rollback state: {exc}")

        profile_restored = False
        binary_restored = False
        messages = []

        if snapshot_path and os.path.exists(snapshot_path):
            ok, message = restore_profile_backup(snapshot_path)
            if ok:
                profile_restored = True
                messages.append("Профиль и пользовательские данные восстановлены из снимка перед обновлением.")
            else:
                messages.append(str(message))
        else:
            ok, latest_snapshot, message = restore_latest_update_snapshot()
            if ok:
                profile_restored = True
                snapshot_path = latest_snapshot
                messages.append("Профиль и пользовательские данные восстановлены из последнего снимка перед обновлением.")
            else:
                messages.append(str(message))

        if binary_backup and target_path and os.path.exists(binary_backup) and not getattr(sys, "frozen", False):
            try:
                os.replace(binary_backup, target_path)
                binary_restored = True
                messages.append("Файл приложения тоже откатан на предыдущую копию.")
            except Exception as exc:
                messages.append(f"Файл приложения не удалось откатить автоматически: {short_exc(exc)}")
        elif from_version or to_version:
            messages.append(
                f"Версия до обновления: {from_version or 'неизвестно'}, обновлялось до: {to_version or 'неизвестно'}."
            )
            if not binary_backup:
                messages.append("Если нужен откат самого билда, переустановите предыдущий релиз вручную.")

        if profile_restored:
            try:
                self.reload_services()
            except Exception:
                pass
            self.set_status("Откат последнего обновления выполнен", "ok")
            self.add_msg("\n".join(messages), "bot")
            messagebox.showinfo("Откат обновления", "\n".join(messages), parent=self.root)
            if binary_restored:
                try:
                    os.remove(rollback_path)
                except Exception:
                    pass
        else:
            self.set_status("Откат обновления не выполнен", "warn")
            messagebox.showwarning("Откат обновления", "\n".join(messages), parent=self.root)

    def _fetch_json_from_url(self, url: str, timeout: float = 8.0):
        if not url:
            return None
        if not self._is_trusted_update_url(url):
            raise ValueError("Небезопасный источник обновления. Разрешены только доверенные HTTPS-хосты.")
        from urllib.request import Request, urlopen

        req = Request(
            url,
            headers={
                "User-Agent": APP_USER_AGENT,
                "Accept": "application/json, text/plain, */*",
            },
        )
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8-sig", errors="replace"))

    def _extract_sha256(self, value: str):
        return extract_sha256(value)

    def _is_installer_asset_name(self, name: str) -> bool:
        return is_installer_asset_name(name, installer_hints=[APP_INSTALLER_NAME])

    def _pick_release_asset(self, assets: list, preferred_name: str = ""):
        return pick_release_asset(
            assets,
            is_frozen=bool(getattr(sys, "frozen", False)),
            preferred_name=preferred_name,
            configured_asset_name=(self.config_mgr.get("update_asset_name", "") or "").strip().lower(),
            installer_hints=[APP_INSTALLER_NAME],
        )

    def _fetch_update_info(self):
        manifest_url = (self.config_mgr.get_update_manifest_url() or DEFAULT_RELEASE_API_URL or "").strip()
        repo = (self.config_mgr.get_github_repo() or DEFAULT_GITHUB_REPO or "").strip()
        is_frozen = bool(getattr(sys, "frozen", False))

        data = None
        source = ""
        if manifest_url:
            data = self._fetch_json_from_url(manifest_url)
            source = manifest_url
        elif repo:
            api_url = f"https://api.github.com/repos/{repo}/releases/latest"
            data = self._fetch_json_from_url(api_url)
            source = api_url

        if not isinstance(data, dict):
            return None

        version = (data.get("version") or data.get("tag_name") or data.get("name") or "").strip()
        notes = (data.get("notes") or data.get("body") or "").strip()

        configured_download_url = (self.config_mgr.get_update_download_url() or "").strip()
        download_url = configured_download_url
        sha256 = self._extract_sha256(data.get("sha256") or data.get("checksum") or "")
        asset_label = ""
        asset_kind = "portable"
        preferred_installer_name = str(data.get("installer_name", "") or "").strip()

        picked_from_files = None
        files = data.get("files")
        if isinstance(files, list):
            if is_frozen:
                if preferred_installer_name:
                    for item in files:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("name") or item.get("path") or "").strip()
                        if name.lower() == preferred_installer_name.lower():
                            picked_from_files = item
                            break
                if picked_from_files is None:
                    for item in files:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("name") or item.get("path") or "").strip()
                        if self._is_installer_asset_name(name):
                            picked_from_files = item
                            break
            else:
                for item in files:
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("name") or item.get("path") or "").strip().lower().endswith(".zip"):
                        picked_from_files = item
                        break
                if picked_from_files is None and files:
                    picked_from_files = files[0] if isinstance(files[0], dict) else None

        if picked_from_files:
            download_url = str(
                picked_from_files.get("url")
                or picked_from_files.get("download_url")
                or ""
            ).strip()
            asset_label = str(
                picked_from_files.get("name")
                or picked_from_files.get("path")
                or ""
            ).strip()
            asset_kind = "installer" if self._is_installer_asset_name(asset_label) else "portable"
            if not sha256:
                sha256 = self._extract_sha256(
                    picked_from_files.get("sha256")
                    or picked_from_files.get("checksum")
                    or ""
                )

        if not download_url:
            download_url = (data.get("download_url") or data.get("browser_download_url") or "").strip()

        if isinstance(data.get("assets"), list):
            picked = self._pick_release_asset(data["assets"], preferred_name=preferred_installer_name)
            if picked:
                picked_url = picked.get("download_url", "").strip()
                picked_name = picked.get("name", "")
                picked_kind = picked.get("kind", "portable")
                should_override = (
                    not download_url
                    or (is_frozen and picked_kind == "installer")
                )
                if should_override and picked_url:
                    download_url = picked_url
                    asset_label = picked_name
                    asset_kind = picked_kind
                if not sha256:
                    sha256 = picked.get("sha256", "")

        if is_frozen and download_url:
            path_low = (urlparse(download_url).path or "").lower()
            if not self._is_installer_asset_name(os.path.basename(path_low)):
                if isinstance(data.get("assets"), list):
                    picked_installer = self._pick_release_asset(data["assets"], preferred_name=preferred_installer_name)
                    if picked_installer and picked_installer.get("kind") == "installer" and picked_installer.get("download_url"):
                        download_url = picked_installer.get("download_url").strip()
                        asset_label = picked_installer.get("name", "")
                        asset_kind = "installer"
                        if not sha256:
                            sha256 = picked_installer.get("sha256", "")

        if download_url and not self._is_trusted_update_url(download_url):
            logger.warning(f"Blocked update from untrusted host: {download_url}")
            return None

        return {
            "version": version,
            "download_url": download_url,
            "notes": notes,
            "source": source,
            "sha256": sha256,
            "asset_name": asset_label,
            "asset_kind": asset_kind,
        }

    def _download_binary(self, url: str, timeout: float = 20.0, expected_sha256: str = "") -> bytes:
        if not self._is_trusted_update_url(url):
            raise ValueError("Источник обновления не прошел проверку безопасности.")
        from urllib.request import Request, urlopen

        req = Request(url, headers={"User-Agent": APP_USER_AGENT})
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if not data:
            raise ValueError("Загружен пустой файл обновления.")
        if expected_sha256:
            digest = hashlib.sha256(data).hexdigest().lower()
            if digest != expected_sha256.lower():
                raise ValueError("Контрольная сумма обновления не совпадает.")
        return data

    def _installer_silent_candidates(self, download_url: str, tmp_path: str):
        lower_url = (download_url or "").lower()
        parsed_path = (urlparse(download_url).path or "").lower()
        file_ext = ".msi" if parsed_path.endswith(".msi") else ".exe"
        if file_ext == ".msi":
            return [f'msiexec /i "{tmp_path}" /qn /norestart'], file_ext

        name = os.path.basename(parsed_path)
        candidates = []
        if "nsis" in lower_url or "nsis" in name:
            candidates.append(f'"{tmp_path}" /S')
        if "inno" in lower_url or "setup" in lower_url or "installer" in lower_url or name.endswith(".exe"):
            candidates.append(f'"{tmp_path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-')
        candidates.append(f'"{tmp_path}" /S')
        candidates.append(f'"{tmp_path}" /silent')

        unique = []
        for candidate in candidates:
            if candidate not in unique:
                unique.append(candidate)
        return unique, file_ext

    def _install_update_file(self, download_url: str, latest_version: str, expected_sha256: str = "", release_notes: str = ""):
        import shutil
        import tempfile

        if not download_url:
            return False, "Нет ссылки для обновления."

        is_frozen = bool(getattr(sys, "frozen", False))
        lower_url = download_url.lower()
        if is_frozen and not (lower_url.endswith(".exe") or lower_url.endswith(".msi")):
            return False, "Для установленной версии разрешены только .exe/.msi обновления."

        safe_ver = re.sub(r"[^0-9a-zA-Z._-]+", "_", str(latest_version or "new"))
        parsed_path = (urlparse(download_url).path or "").lower()
        file_ext = ".msi" if parsed_path.endswith(".msi") else ".exe"
        is_installer_package = self._is_installer_asset_name(os.path.basename(parsed_path)) or file_ext == ".msi"
        if is_frozen:
            target_path = os.path.abspath(sys.executable)
            tmp_path = os.path.join(tempfile.gettempdir(), f"{APP_DIR_NAME}_update_{safe_ver}{file_ext}")
        else:
            target_path = os.path.abspath(sys.argv[0])
            tmp_path = target_path + ".download"

        rollback_state = {
            "from_version": APP_VERSION,
            "to_version": str(latest_version or ""),
            "snapshot": "",
            "target_path": target_path,
            "binary_backup": "",
            "created_at": time.time(),
        }

        data = self._download_binary(download_url, timeout=30.0, expected_sha256=expected_sha256)
        if is_frozen and not data.startswith(b"MZ"):
            return False, "Файл обновления не похож на исполняемый файл Windows."

        snapshot_path = ""
        try:
            snapshot_path = create_update_snapshot(latest_version)
            logger.info(f"Created pre-update snapshot: {snapshot_path}")
            rollback_state["snapshot"] = snapshot_path
        except Exception as exc:
            logger.warning(f"Could not create pre-update snapshot: {exc}")

        with open(tmp_path, "wb") as handle:
            handle.write(data)

        update_flag_file = update_status_path()
        try:
            with open(update_flag_file, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "version": latest_version,
                        "timestamp": time.time(),
                        "notes": str(release_notes or ""),
                        "snapshot": snapshot_path,
                    },
                    handle,
                    ensure_ascii=False,
                )
        except Exception as exc:
            logger.warning(f"Could not save update flag: {exc}")

        if is_frozen:
            exe_name = os.path.basename(target_path)
            bat_path = os.path.join(tempfile.gettempdir(), f"{APP_DIR_NAME}_update_{safe_ver}.bat")
            if is_installer_package:
                install_candidates, _ = self._installer_silent_candidates(download_url, tmp_path)
            else:
                install_candidates = [f'copy /y "{tmp_path}" "{target_path}" >nul']

            bat_lines = [
                "@echo off",
                "setlocal enableextensions",
                f'set "SRC={tmp_path}"',
                f'set "DST={target_path}"',
                f'set "EXE={exe_name}"',
                ":waitloop",
                "timeout /t 1 /nobreak >nul",
                'tasklist /fi "imagename eq %EXE%" | find /i "%EXE%" >nul',
                "if not errorlevel 1 goto waitloop",
            ]
            if is_installer_package:
                bat_lines.append('set "UPDATED=0"')
                for command in install_candidates:
                    bat_lines.append('if "%UPDATED%"=="1" goto launch')
                    bat_lines.append(command)
                    bat_lines.append('if not errorlevel 1 set "UPDATED=1"')
                bat_lines.append('if "%UPDATED%"=="0" goto fail')
                bat_lines.append(":launch")
                bat_lines.append('if exist "%DST%" start "" "%DST%"')
                bat_lines.append('del "%SRC%" 2>nul')
                bat_lines.append('del "%~f0" 2>nul')
                bat_lines.append("exit /b 0")
                bat_lines.append(":fail")
                bat_lines.append("echo Update failed.")
                bat_lines.append('del "%SRC%" 2>nul')
                bat_lines.append('del "%~f0" 2>nul')
            else:
                bat_lines.extend([
                    'copy /y "%SRC%" "%DST%" >nul',
                    'if exist "%DST%" start "" "%DST%"',
                    'del "%~f0" 2>nul',
                ])

            with open(bat_path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(bat_lines) + "\n")
            try:
                self._save_rollback_state(rollback_state)
            except Exception as exc:
                logger.warning(f"Could not save rollback state: {exc}")
            subprocess.Popen(["cmd", "/c", bat_path], creationflags=CREATE_NO_WINDOW)
            return True, tmp_path

        backup_path = target_path + ".bak"
        try:
            if os.path.exists(target_path):
                shutil.copy2(target_path, backup_path)
                rollback_state["binary_backup"] = backup_path
        except Exception:
            pass
        try:
            self._save_rollback_state(rollback_state)
        except Exception as exc:
            logger.warning(f"Could not save rollback state: {exc}")
        os.replace(tmp_path, target_path)
        return True, target_path

    def _check_for_updates_worker(self):
        try:
            info = self._fetch_update_info()
            if not info:
                return

            latest = (info.get("version") or "").strip()
            if not latest:
                return

            if self._is_newer_version(APP_VERSION, latest):
                self.root.after(0, lambda: self.set_status_temp(f"Доступна версия {latest}", "warn"))
                self.config_mgr.set_available_version(latest)
                notice = f"📦 Доступно обновление {latest}.\nСкачать: {DEFAULT_RELEASES_URL}"
                self.root.after(0, lambda message=notice: self.add_msg(message, "bot"))
                if self.telegram_bot and self.config_mgr.get_telegram_user_id():
                    try:
                        self.telegram_bot.send_message(self.config_mgr.get_telegram_user_id(), notice)
                    except Exception:
                        pass

                if self.config_mgr.get_auto_update() and info.get("download_url"):
                    self.root.after(0, lambda: self.set_status(f"Обновляю до {latest}...", "busy"))
                    ok, result = self._install_update_file(
                        info["download_url"],
                        latest,
                        expected_sha256=(info.get("sha256") or ""),
                        release_notes=(info.get("notes") or ""),
                    )
                    if ok:
                        self.root.after(0, lambda: self.add_msg(f"✅ Обновление {latest} скачано.", "bot"))
                        self.root.after(0, lambda: self.set_status("Обновление загружено", "ok"))
                        if getattr(sys, "frozen", False):
                            self.root.after(2500, lambda: self.set_status("Перезапуск для обновления...", "busy"))
                            self.root.after(3200, self.quit_app)
                    else:
                        self.root.after(0, lambda: self.add_msg(f"⚠️ Не удалось обновить: {result}", "bot"))
                elif info.get("download_url"):
                    self.root.after(0, lambda: self.add_msg(f"📦 Доступна новая версия {latest}.\nСсылка обновления готова.", "bot"))
        except Exception as exc:
            if self._is_transient_network_error(exc):
                logger.warning(f"Update check transient issue: {exc}")
            else:
                logger.error(f"Update check error: {exc}")

    def check_for_updates(self):
        if getattr(self, "_update_check_started", False):
            return
        self._update_check_started = True
        threading.Thread(target=self._check_for_updates_worker, daemon=True, name="UpdateCheckThread").start()

    def check_for_updates_now(self):
        self.set_status("Поиск обновлений...", "busy")
        threading.Thread(target=self._check_for_updates_worker_with_status, daemon=True, name="ManualUpdateCheck").start()

    def _ask_yes_no_sync(self, title: str, text: str) -> bool:
        if threading.current_thread() is threading.main_thread():
            return bool(messagebox.askyesno(title, text))
        result = {"value": False}
        done = threading.Event()

        def _ask():
            try:
                result["value"] = bool(messagebox.askyesno(title, text))
            finally:
                done.set()

        self.root.after(0, _ask)
        done.wait(timeout=180.0)
        return bool(result["value"])

    def _check_for_updates_worker_with_status(self):
        try:
            info = self._fetch_update_info()
            if not info:
                self.root.after(0, lambda: self.set_status("Не найдено: обновления недоступны", "warn"))
                self.root.after(2000, lambda: self.set_status("Готов", "ok"))
                return

            latest = (info.get("version") or "").strip()
            if not latest:
                self.root.after(0, lambda: self.set_status("Не найдено: версия не определена", "warn"))
                self.root.after(2000, lambda: self.set_status("Готов", "ok"))
                return

            if self._is_newer_version(APP_VERSION, latest):
                self.root.after(0, lambda: self.set_status(f"Найдено: версия {latest}", "warn"))
                if self._ask_yes_no_sync("Обновление", f"Доступна новая версия {latest}. Установить сейчас?"):
                    self.set_status("Обновление...", "busy")
                    if info.get("download_url"):
                        ok, result = self._install_update_file(
                            info["download_url"],
                            latest,
                            expected_sha256=(info.get("sha256") or ""),
                            release_notes=(info.get("notes") or ""),
                        )
                        if ok:
                            self.root.after(0, lambda: self.add_msg(f"✅ Обновление {latest} скачано.", "bot"))
                            self.root.after(0, lambda: self.set_status("Обновление загружено", "ok"))
                            if getattr(sys, "frozen", False):
                                self.root.after(2500, lambda: self.set_status("Перезапуск для обновления...", "busy"))
                                self.root.after(3200, self.quit_app)
                        else:
                            self.root.after(0, lambda: self.set_status("Ошибка обновления", "error"))
                    else:
                        self.root.after(0, lambda: self.set_status("Нет ссылки для скачивания", "error"))
                else:
                    self.root.after(0, lambda: self.set_status("Готов", "ok"))
            else:
                self.root.after(0, lambda: self.set_status("Не найдено: у вас последняя версия", "ok"))
                self.root.after(2000, lambda: self.set_status("Готов", "ok"))
        except Exception as exc:
            if self._is_transient_network_error(exc):
                logger.warning(f"Manual update check transient issue: {exc}")
                self.root.after(0, lambda: self.set_status("Сервер обновлений временно недоступен", "warn"))
                self.root.after(2000, lambda: self.set_status("Готов", "ok"))
            else:
                logger.error(f"Update check error: {exc}")
                self.root.after(0, lambda: self.set_status("Ошибка проверки обновлений", "error"))
                self.root.after(2000, lambda: self.set_status("Готов", "ok"))

    def check_update_notification(self):
        update_flag_file = update_status_path()
        if not os.path.exists(update_flag_file):
            return

        try:
            with open(update_flag_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            new_version = str(data.get("version", "") or "").strip()
            notes = str(data.get("notes", "") or "").strip()
            snapshot_path = str(data.get("snapshot", "") or "").strip()
            if new_version and self.config_mgr.get_last_update_notice_version() != new_version:
                if notes:
                    notes_text = self._format_release_notes_for_chat(notes)
                    summary = f"✅ Обновление до {new_version} завершено.\nЧто изменилось:\n{notes_text}"
                    speech_text = f"Обновление до версии {new_version} установлено. Что нового: {notes_text.replace('•', '').replace(chr(10), '. ')}"
                else:
                    summary = f"✅ Обновление до {new_version} завершено."
                    speech_text = f"Обновление до версии {new_version} установлено."
                if snapshot_path:
                    summary = summary + "\nСнимок профиля перед обновлением сохранен. Откат доступен из раздела 'Система'."
                self.add_msg(summary, "bot")
                self.say(speech_text)
                self.set_status(f"Обновлено до {new_version}", "ok")
                self.root.after(2000, lambda: self.set_status("Готов", "ok"))
                self.config_mgr.set_last_update_notice_version(new_version)
        except Exception as exc:
            logger.error(f"Error processing update notification: {exc}")
        finally:
            try:
                if os.path.exists(update_flag_file):
                    os.remove(update_flag_file)
            except Exception:
                pass

    def _format_release_notes_for_chat(self, notes: str, max_items: int = 6) -> str:
        return format_release_notes_for_chat(notes, max_items=max_items)


def _patched_fetch_json_from_url(self, url: str, timeout: float = 8.0):
    try:
        return UpdateFlowMixin._base_fetch_json_from_url(self, url, timeout=timeout)
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code == 404 and "releases/latest" in str(url or ""):
            logger.info(f"No published GitHub release yet for update channel: {url}")
            return {"_not_published": True, "source": url}
        raise


def _patched_fetch_update_info(self):
    info = UpdateFlowMixin._base_fetch_update_info(self)
    if isinstance(info, dict) and not info.get("version") and not info.get("download_url"):
        source = str(info.get("source") or "")
        if info.get("_not_published") or "releases/latest" in source:
            info["not_published"] = True
    return info


def _patched_check_for_updates_worker(self):
    try:
        info = self._fetch_update_info()
        if isinstance(info, dict) and info.get("not_published"):
            logger.info("Skipping update notice: GitHub release is not published yet.")
            return
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            logger.info("Skipping update check error because release is not published yet.")
            return
        raise
    return UpdateFlowMixin._base_check_for_updates_worker(self)


def _patched_check_for_updates_worker_with_status(self):
    try:
        info = self._fetch_update_info()
        if isinstance(info, dict) and info.get("not_published"):
            self.root.after(0, lambda: self.set_status("GitHub-релиз еще не опубликован", "warn"))
            self.root.after(2200, lambda: self.set_status("Готов", "ok"))
            return
    except Exception as exc:
        if getattr(exc, "code", None) == 404:
            self.root.after(0, lambda: self.set_status("GitHub-релиз еще не опубликован", "warn"))
            self.root.after(2200, lambda: self.set_status("Готов", "ok"))
            return
        raise
    return UpdateFlowMixin._base_check_for_updates_worker_with_status(self)


UpdateFlowMixin._base_fetch_json_from_url = UpdateFlowMixin._fetch_json_from_url
UpdateFlowMixin._base_fetch_update_info = UpdateFlowMixin._fetch_update_info
UpdateFlowMixin._base_check_for_updates_worker = UpdateFlowMixin._check_for_updates_worker
UpdateFlowMixin._base_check_for_updates_worker_with_status = UpdateFlowMixin._check_for_updates_worker_with_status
UpdateFlowMixin._fetch_json_from_url = _patched_fetch_json_from_url
UpdateFlowMixin._fetch_update_info = _patched_fetch_update_info
UpdateFlowMixin._check_for_updates_worker = _patched_check_for_updates_worker
UpdateFlowMixin._check_for_updates_worker_with_status = _patched_check_for_updates_worker_with_status
