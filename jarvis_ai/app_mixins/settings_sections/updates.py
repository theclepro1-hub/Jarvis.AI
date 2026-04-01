import os
import tkinter as tk
from tkinter import messagebox

from ...branding import app_brand_name, app_version_badge
from ...release_meta import DEFAULT_GITHUB_REPO, DEFAULT_RELEASE_API_URL, DEFAULT_RELEASES_URL
from ...runtime import runtime_root_path
from ...state import CONFIG_MGR
from ...theme import Theme


def build_updates_settings_section(self, parent):
    _, _, body = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)
    frame = tk.Frame(body, bg=Theme.CARD_BG)
    frame.pack(fill="x", padx=18, pady=12)

    github_var = tk.StringVar(value=DEFAULT_GITHUB_REPO)
    manifest_var = tk.StringVar(value=DEFAULT_RELEASE_API_URL)
    download_var = tk.StringVar(value=str(CONFIG_MGR.get_update_download_url() or "").strip())
    trusted_hosts_var = tk.StringVar(value=", ".join(CONFIG_MGR.get_update_trusted_hosts()))

    tk.Label(
        frame,
        text=f"Официальный канал обновлений: {DEFAULT_RELEASES_URL}\nПроверка выполняется автоматически на каждом запуске.",
        bg=Theme.CARD_BG,
        fg=Theme.FG_SECONDARY,
        justify="left",
        wraplength=760,
    ).pack(anchor="w", pady=(0, 10))

    tk.Label(frame, text="GitHub репозиторий (owner/repo)", bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(0, 3))
    github_entry = tk.Entry(frame, textvariable=github_var, bg=Theme.INPUT_BG, fg=Theme.FG, state="readonly", readonlybackground=Theme.INPUT_BG)
    github_entry.pack(fill="x", pady=(0, 10))
    self._setup_entry_bindings(github_entry)

    tk.Label(frame, text="URL манифеста обновлений (JSON)", bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(0, 3))
    manifest_entry = tk.Entry(frame, textvariable=manifest_var, bg=Theme.INPUT_BG, fg=Theme.FG, state="readonly", readonlybackground=Theme.INPUT_BG)
    manifest_entry.pack(fill="x", pady=(0, 10))
    self._setup_entry_bindings(manifest_entry)

    tk.Label(frame, text="Прямая ссылка на скачивание (опционально)", bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(0, 3))
    download_entry = tk.Entry(frame, textvariable=download_var, bg=Theme.INPUT_BG, fg=Theme.FG)
    download_entry.pack(fill="x", pady=(0, 15))
    self._setup_entry_bindings(download_entry)

    tk.Label(frame, text="Доверенные хосты обновлений (через запятую)", bg=Theme.CARD_BG, fg=Theme.FG).pack(anchor="w", pady=(0, 3))
    trusted_entry = tk.Entry(frame, textvariable=trusted_hosts_var, bg=Theme.INPUT_BG, fg=Theme.FG)
    trusted_entry.pack(fill="x", pady=(0, 15))
    self._setup_entry_bindings(trusted_entry)

    def save_updates():
        hosts = [h.strip().lower() for h in trusted_hosts_var.get().split(",") if h.strip()]
        default_hosts = list(dict.fromkeys((hosts or []) + list(CONFIG_MGR.default_config.get("update_trusted_hosts", []))))
        CONFIG_MGR.set_many(
            {
                "github_repo": DEFAULT_GITHUB_REPO,
                "update_manifest_url": DEFAULT_RELEASE_API_URL,
                "update_download_url": download_var.get().strip(),
                "update_trusted_hosts": default_hosts,
                "update_check_on_start": True,
            }
        )
        self._settings_toast("Настройки обновлений сохранены", "ok")

    tk.Button(frame, text="Сохранить настройки обновлений", command=save_updates, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8, cursor="hand2").pack(pady=(0, 10))
    tk.Button(frame, text="Проверить обновления сейчас", command=self.check_for_updates_now, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=14, pady=8, cursor="hand2").pack(pady=5)

    publish_card = tk.Frame(frame, bg=Theme.BUTTON_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
    publish_card.pack(fill="x", pady=(16, 0))
    publish_head = tk.Frame(publish_card, bg=Theme.BUTTON_BG)
    publish_head.pack(fill="x", padx=12, pady=(10, 4))
    tk.Label(publish_head, text="Публикация в 1 клик", bg=Theme.BUTTON_BG, fg=Theme.FG, font=("Segoe UI", 11, "bold")).pack(side="left")
    tk.Label(publish_head, text=app_version_badge(), bg=Theme.ACCENT, fg=Theme.FG, font=("Segoe UI", 8, "bold"), padx=8, pady=3).pack(side="right")
    tk.Label(
        publish_card,
        text=f"Сборка, подготовка GitHub bundle, commit, push и tag {app_version_badge()} одной кнопкой. Используется репозиторий {DEFAULT_GITHUB_REPO}.",
        bg=Theme.BUTTON_BG,
        fg=Theme.FG_SECONDARY,
        justify="left",
        wraplength=760,
    ).pack(anchor="w", padx=12, pady=(0, 8))

    def open_publish_tools_folder():
        tools_dir = runtime_root_path("publish_tools")
        if not os.path.isdir(tools_dir):
            messagebox.showerror(app_brand_name(), f"Папка publish_tools не найдена:\n{tools_dir}")
            return
        try:
            os.startfile(tools_dir)
        except Exception as exc:
            self.report_error("Ошибка открытия publish_tools", exc, speak=False)

    def run_publish_one_click():
        script_path = runtime_root_path("publish_tools", "Publish-One-Click.bat")
        if not os.path.exists(script_path):
            messagebox.showerror(app_brand_name(), f"Скрипт публикации в 1 клик не найден:\n{script_path}")
            return
        if not messagebox.askyesno(
            app_brand_name(),
            "Запустить публикацию в 1 клик?\n\nЭто соберёт релиз, подготовит GitHub bundle, сделает commit, push и отправит tag в GitHub.",
        ):
            return
        try:
            os.startfile(script_path)
            self.set_status_temp("Открыл публикацию в 1 клик", "ok")
        except Exception as exc:
            self.report_error("Ошибка запуска публикации в 1 клик", exc, speak=False)

    publish_actions = tk.Frame(publish_card, bg=Theme.BUTTON_BG)
    publish_actions.pack(fill="x", padx=12, pady=(0, 12))
    tk.Button(
        publish_actions,
        text="Опубликовать одним кликом",
        command=run_publish_one_click,
        bg=Theme.ACCENT,
        fg=Theme.FG,
        relief="flat",
        padx=14,
        pady=9,
        cursor="hand2",
    ).pack(side="left")
    tk.Button(
        publish_actions,
        text="Открыть publish_tools",
        command=open_publish_tools_folder,
        bg=Theme.CARD_BG,
        fg=Theme.FG,
        relief="flat",
        padx=14,
        pady=9,
        cursor="hand2",
    ).pack(side="left", padx=(8, 0))
