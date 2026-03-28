from typing import Optional

import tkinter as tk
from tkinter import messagebox, ttk

from .audio_devices import _expand_audio_device_name, _get_audio_device_entry
from .branding import app_brand_name, app_version_badge
from .settings_forms import field_dropdown, field_entry, field_slider, flag_row
from .state import CONFIG_MGR, DEFAULT_CHAT_MODEL
from .theme import Theme
from .ui_factory import bind_dynamic_wrap, create_action_button, create_note_box, create_section_card


def apply_settings_ui_polish(SettingsUiMixin):
    if getattr(SettingsUiMixin, "_polish_20260328_applied", False):
        return

    def _create_scrollable_settings_host(self, parent, inner_bg: Optional[str] = None):
        for child in parent.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

        host = tk.Frame(parent, bg=Theme.BG_LIGHT)
        host.pack(fill="both", expand=True)
        canvas = tk.Canvas(host, bg=Theme.BG_LIGHT, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(host, orient="vertical", command=canvas.yview, style="Jarvis.Vertical.TScrollbar")
        inner = tk.Frame(canvas, bg=inner_bg or Theme.BG_LIGHT)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def _sync_scroll(_event=None):
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas.itemconfigure(inner_id, width=max(1, canvas.winfo_width()))
            except Exception:
                pass

        inner.bind("<Configure>", _sync_scroll, add="+")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(inner_id, width=max(1, int(getattr(e, "width", 0) or canvas.winfo_width()))), add="+")
        self._register_scroll_target(canvas)
        try:
            parent._jarvis_scroll_canvas = canvas
        except Exception:
            pass
        return host, canvas, inner

    def _schedule_settings_visual_refresh(self):
        after_id = getattr(self, "_settings_visual_after_id", None)
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass

        def _refresh():
            self._settings_visual_after_id = None
            try:
                self.root.update_idletasks()
            except Exception:
                pass
            try:
                current_tab = self.embedded_settings_notebook.nametowidget(self.embedded_settings_notebook.select())
            except Exception:
                current_tab = None
            if current_tab is not None:
                try:
                    canvas = getattr(current_tab, "_jarvis_scroll_canvas", None)
                    if canvas is not None:
                        canvas.configure(scrollregion=canvas.bbox("all"))
                except Exception:
                    pass
            self._restyle_settings_window()

        self._settings_visual_after_id = self.root.after(36, _refresh)

    def _build_embedded_settings_page(self):
        page = getattr(self, "embedded_settings_page", None)
        if page is None or not page.winfo_exists():
            page = tk.Frame(self.content_stage, bg=Theme.BG_LIGHT)
            self.embedded_settings_page = page
        for child in list(page.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass

        self._settings_tab1_save_callback = None
        self._configure_ttk_styles()
        try:
            style = ttk.Style()
            style.configure("Jarvis.Wide.TNotebook", background=Theme.BG_LIGHT, borderwidth=0)
            style.configure(
                "Jarvis.Wide.TNotebook.Tab",
                background=Theme.BUTTON_BG,
                foreground=Theme.FG,
                padding=(16, 9),
                borderwidth=0,
                font=("Segoe UI Semibold", 10),
            )
            style.map(
                "Jarvis.Wide.TNotebook.Tab",
                background=[("selected", Theme.ACCENT), ("active", Theme.CARD_BG)],
                foreground=[("selected", Theme.FG), ("active", Theme.FG)],
            )
        except Exception:
            pass

        head = tk.Frame(page, bg=Theme.CARD_BG, highlightbackground=Theme.BORDER, highlightthickness=1)
        head.pack(fill="x", padx=6, pady=(0, 10))
        top_row = tk.Frame(head, bg=Theme.CARD_BG)
        top_row.pack(fill="x", padx=18, pady=(16, 6))
        title_group = tk.Frame(top_row, bg=Theme.CARD_BG)
        title_group.pack(side="left", fill="x", expand=True)
        tk.Label(title_group, text="Настройки JARVIS 2.0", bg=Theme.CARD_BG, fg=Theme.FG, font=("Segoe UI Semibold", 16)).pack(side="left")
        tk.Label(title_group, text=app_version_badge(), bg=Theme.ACCENT, fg=Theme.FG, font=("Segoe UI", 8, "bold"), padx=8, pady=3).pack(side="left", padx=(10, 0))
        tk.Button(top_row, text="Назад к чату", command=self.close_full_settings_view, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=14, pady=9).pack(side="right")
        head_desc = tk.Label(
            head,
            text="Разделы стали короче и понятнее: ИИ и профиль отдельно, аудио отдельно, релиз и сервисные функции отдельно. Это уменьшает визуальную кашу и лучше работает даже на небольшом окне.",
            bg=Theme.CARD_BG,
            fg=Theme.FG_SECONDARY,
            font=("Segoe UI", 9),
            justify="left",
        )
        head_desc.pack(fill="x", padx=18, pady=(0, 14))
        bind_dynamic_wrap(head_desc, head, padding=36, minimum=260)

        notebook = ttk.Notebook(page, style="Jarvis.Wide.TNotebook")
        self.embedded_settings_notebook = notebook
        notebook.pack(fill="both", expand=True, padx=6, pady=(0, 10))
        tab1 = tk.Frame(notebook, bg=Theme.BG_LIGHT)
        tab_audio = tk.Frame(notebook, bg=Theme.BG_LIGHT)
        tab2 = tk.Frame(notebook, bg=Theme.BG_LIGHT)
        tab3 = tk.Frame(notebook, bg=Theme.BG_LIGHT)
        tab4 = tk.Frame(notebook, bg=Theme.BG_LIGHT)
        tab5 = tk.Frame(notebook, bg=Theme.BG_LIGHT)
        self.embedded_settings_tabs = {
            "main": tab1,
            "audio": tab_audio,
            "apps": tab2,
            "diagnostics": tab3,
            "updates": tab4,
            "technical": tab5,
        }
        notebook.add(tab1, text="ИИ и профиль")
        notebook.add(tab_audio, text="Аудио")
        notebook.add(tab2, text="Приложения")
        notebook.add(tab3, text="Диагностика")
        notebook.add(tab4, text="Релиз")
        notebook.add(tab5, text="Система")

        self._create_settings_tab1(tab1)
        self._create_settings_tab_audio(tab_audio)
        self._create_settings_tab2(tab2)
        self._create_settings_tab4(tab4)
        self._create_diagnostic_tab(tab3)
        self._create_settings_tab5(tab5)
        try:
            notebook.bind(
                "<<NotebookTabChanged>>",
                lambda _e: (self._schedule_settings_visual_refresh(), self._sync_embedded_settings_workspace_section()),
                add="+",
            )
        except Exception:
            pass

        footer = tk.Frame(page, bg=Theme.BG_LIGHT)
        footer.pack(fill="x", padx=8, pady=(0, 6))
        tk.Button(footer, text="Сохранить основные", command=self._save_settings_tab1_from_footer, bg=Theme.ACCENT, fg=Theme.FG, relief="flat", padx=16, pady=9).pack(side="right", padx=(0, 8))
        tk.Button(footer, text="Назад", command=self.close_full_settings_view, bg=Theme.BUTTON_BG, fg=Theme.FG, relief="flat", padx=16, pady=9).pack(side="right")
        self._sync_embedded_settings_workspace_section()
        self._schedule_settings_visual_refresh()
        return page

    def _create_settings_tab1(self, parent):
        _, _, inner = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)

        _, access_body = create_section_card(inner, "Доступ и профиль", "Groq нужен для ИИ-команд и чата. Telegram нужен только для удаленного управления.")
        groq_var, _ = field_entry(self, access_body, "Groq API ключ", CONFIG_MGR.get_api_key(), show="*", hint="Без ключа ИИ останется в локальном/offline-режиме и не сможет нормально понимать сложные команды.")
        user_name_var, _ = field_entry(self, access_body, "Имя профиля", CONFIG_MGR.get_user_name(), hint="Показывается в интерфейсе и делает ответы персональнее.")
        login_var, _ = field_entry(self, access_body, "Логин пользователя", CONFIG_MGR.get_user_login(), hint="Технический идентификатор профиля.")
        tg_token_var, _ = field_entry(self, access_body, "Telegram bot token", CONFIG_MGR.get_telegram_token(), show="*", hint="Нужен только для Telegram-бота.")
        tg_id_var, _ = field_entry(self, access_body, "Telegram user ID", str(CONFIG_MGR.get_telegram_user_id() or ""), hint="ID пользователя, которому разрешено управлять JARVIS через Telegram.")
        create_note_box(access_body, "Если Telegram не нужен, token и user ID можно оставить пустыми.", tone="soft")

        _, brain_body = create_section_card(inner, "Мозг JARVIS", "Эти настройки влияют на стиль мышления ИИ и на то, насколько стабильно он отдает команды в нужном формате.")
        model_items = [
            ("Groq Compound Mini — лучший баланс для JARVIS", "groq/compound-mini"),
            ("Llama 3.3 70B — тяжелее, но сильнее", "llama-3.3-70b-versatile"),
            ("Llama 3.1 8B — быстрый fallback", "llama-3.1-8b-instant"),
            ("Qwen3 32B — альтернативный стиль", "qwen/qwen3-32b"),
        ]
        current_model = str(CONFIG_MGR.get_model() or DEFAULT_CHAT_MODEL).strip()
        current_model_label = next((label for label, key in model_items if key == current_model), model_items[0][0])
        model_var, _ = field_dropdown(self, brain_body, "Модель ИИ", [label for label, _key in model_items], current_model_label, hint="Compound Mini обычно лучше всего подходит именно для голосовых команд и короткого чата.")
        temperature_var, _, _ = field_slider(self, brain_body, "Температура ИИ", 0.0, 0.6, float(CONFIG_MGR.get_temperature()), 0.01, "", hint="Ниже — стабильнее и строже. Выше — креативнее, но больше шанс кривого JSON. Для команд держите ближе к нулю.")
        max_tokens_var, _, _ = field_slider(self, brain_body, "Лимит ответа ИИ", 120, 600, float(CONFIG_MGR.get_max_tokens()), 1, " tok", hint="Ограничивает максимальную длину ответа. Небольшой лимит делает ответы быстрее и чище.")
        create_note_box(brain_body, "Рекомендуемый профиль для релиза: Compound Mini + температура 0.00 + лимит 240–320 tok.", tone="accent")

        _, behavior_body = create_section_card(inner, "Поведение и режим", "Флаги ниже управляют запуском, стилем ответов, wake-word и фоновой активностью приложения.")
        theme_items = [("Тёмная", "dark"), ("Светлая", "light")]
        current_theme = str(CONFIG_MGR.get_theme_mode() or "dark").strip().lower()
        if current_theme not in {"dark", "light"}:
            current_theme = "dark"
        current_theme_label = next((label for label, key in theme_items if key == current_theme), theme_items[0][0])
        theme_var, _ = field_dropdown(self, behavior_body, "Тема интерфейса", [label for label, _key in theme_items], current_theme_label)

        auto_update_var = tk.BooleanVar(value=CONFIG_MGR.get_auto_update())
        single_user_var = tk.BooleanVar(value=CONFIG_MGR.get_single_user_mode())
        free_chat_mode_var = tk.BooleanVar(value=CONFIG_MGR.get_free_chat_mode())
        safe_mode_var = tk.BooleanVar(value=CONFIG_MGR.get_safe_mode_enabled())
        autostart_var = tk.BooleanVar(value=CONFIG_MGR.get_autostart())
        active_listening_var = tk.BooleanVar(value=CONFIG_MGR.get_active_listening_enabled())
        wake_word_boost_var = tk.BooleanVar(value=CONFIG_MGR.get_wake_word_boost_enabled())
        bg_self_check_var = tk.BooleanVar(value=CONFIG_MGR.get_background_self_check())
        self_learning_var = tk.BooleanVar(value=CONFIG_MGR.get_self_learning_enabled())
        initial_active_listening = [bool(CONFIG_MGR.get_active_listening_enabled())]

        flag_row(behavior_body, "Автообновление", auto_update_var, "JARVIS сам проверяет новые версии и уведомляет, когда релиз готов.")
        flag_row(behavior_body, "Режим одного пользователя", single_user_var, "Упрощает логику доступа и подходит для персонального ПК.")
        flag_row(behavior_body, "Свободный стиль ответов", free_chat_mode_var, "Делает чат живее, но для строгих команд лучше держать выключенным.")
        flag_row(behavior_body, "Безопасный режим при старте", safe_mode_var, "Снижает фоновую активность и полезен для диагностики лагов.")
        flag_row(behavior_body, "Автозапуск Windows", autostart_var, "Запускает JARVIS вместе с системой.")
        flag_row(behavior_body, "Активное прослушивание слова «Джарвис»", active_listening_var, "Включает ожидание wake-word без нажатия на кнопку микрофона.")
        flag_row(behavior_body, "Усилить чувствительность wake-word", wake_word_boost_var, "Полезно, если JARVIS слышит слово только вплотную к микрофону.")
        flag_row(behavior_body, "Фоновая самодиагностика", bg_self_check_var, "Периодически проверяет журнал и состояние системы.")
        flag_row(behavior_body, "Самообучение на командах", self_learning_var, "Помогает JARVIS лучше запоминать удачные команды.")
        self_check_interval_var, _ = field_entry(self, behavior_body, "Интервал фоновой диагностики (мин)", str(CONFIG_MGR.get_self_check_interval_min()), hint="Обычно хватает 10–15 минут.")

        def save_tab1():
            try:
                try:
                    tg_id = int(str(tg_id_var.get() or "").strip()) if str(tg_id_var.get() or "").strip() else 0
                except Exception:
                    tg_id = 0
                try:
                    interval_min = int(str(self_check_interval_var.get() or "").strip() or "10")
                except Exception:
                    interval_min = 10
                selected_theme_key = next((key for label, key in theme_items if label == str(theme_var.get() or "").strip()), current_theme)
                selected_model_key = next((key for label, key in model_items if label == str(model_var.get() or "").strip()), DEFAULT_CHAT_MODEL)
                prev_theme_mode = str(CONFIG_MGR.get_theme_mode() or "dark").strip().lower()
                if prev_theme_mode not in {"dark", "light"}:
                    prev_theme_mode = "dark"
                previous_safe_mode = bool(getattr(self, "safe_mode", False))
                next_safe_mode = bool(safe_mode_var.get())

                CONFIG_MGR.set_many({
                    "api_key": str(groq_var.get() or "").strip(),
                    "model": selected_model_key,
                    "temperature": float(temperature_var.get()),
                    "max_tokens": int(max_tokens_var.get()),
                    "user_name": str(user_name_var.get() or "").strip(),
                    "user_login": str(login_var.get() or "").strip(),
                    "telegram_token": str(tg_token_var.get() or "").strip(),
                    "telegram_user_id": tg_id,
                    "allowed_user_ids": [tg_id] if tg_id else [],
                    "auto_update": bool(auto_update_var.get()),
                    "update_check_on_start": True,
                    "single_user_mode": bool(single_user_var.get()),
                    "free_chat_mode": bool(free_chat_mode_var.get()),
                    "safe_mode_enabled": next_safe_mode,
                    "autostart": bool(autostart_var.get()),
                    "active_listening_enabled": bool(active_listening_var.get()),
                    "wake_word_boost": bool(wake_word_boost_var.get()),
                    "background_self_check": bool(bg_self_check_var.get()),
                    "self_learning_enabled": bool(self_learning_var.get()),
                    "self_check_interval_min": interval_min,
                    "theme_mode": selected_theme_key,
                })

                if initial_active_listening[0] and not bool(active_listening_var.get()):
                    messagebox.showinfo(app_brand_name(), "Активное прослушивание выключено.\nТеперь JARVIS не будет ждать слово «Джарвис» в фоне.")
                initial_active_listening[0] = bool(active_listening_var.get())
                self.safe_mode = next_safe_mode
                self._set_bg_animation_paused(next_safe_mode, reason="safe_mode")
                if not next_safe_mode and not getattr(self, "_bg_anim_started", False):
                    self.start_bg_anim()
                if previous_safe_mode != next_safe_mode:
                    messagebox.showinfo(app_brand_name(), "Режим запуска обновлен.\nДля честной проверки защищенного режима лучше один раз перезапустить приложение.")

                self.reload_services()
                if selected_theme_key != prev_theme_mode:
                    self.apply_theme_runtime()
                else:
                    self._restyle_settings_window()
                self.apply_autostart()
                self.refresh_mic_status_label()
                self.refresh_output_status_label()
                self.refresh_tts_status_label()
                self.set_status("Основные настройки сохранены", "ok")
                self._schedule_settings_visual_refresh()
                messagebox.showinfo(app_brand_name(), "Основные настройки сохранены.")
            except Exception as e:
                self.report_error("Ошибка сохранения основных настроек", e, speak=False)
                messagebox.showerror(app_brand_name(), str(e))

        self._settings_tab1_save_callback = save_tab1

    def _create_settings_tab_audio(self, parent):
        _, _, inner = self._create_scrollable_settings_host(parent, inner_bg=Theme.BG_LIGHT)

        _, devices_body = create_section_card(inner, "Маршрутизация звука", "Здесь выбирается, откуда JARVIS слушает и куда говорит.")
        mic_index_map = {}
        mic_pairs = self._microphone_names_for_settings(self._get_microphone_devices(refresh=True))
        mic_values = []
        for idx, name in mic_pairs:
            label = name
            if label in mic_index_map and idx is not None:
                label = f"{name} [#{idx}]"
            mic_values.append(label)
            mic_index_map[label] = idx
        if not mic_values:
            mic_values = ["(микрофон не найден)"]
        mic_index = CONFIG_MGR.get_mic_device_index()
        mic_value = next((label for label, idx in mic_index_map.items() if idx == mic_index), mic_values[0])
        mic_var, _ = field_dropdown(self, devices_body, "Микрофон", mic_values, mic_value, hint="Если wake-word слышно плохо, сначала убедитесь, что выбран правильный микрофон.")

        output_option_map = {}
        output_values = []
        for idx, label in self._output_options_for_settings():
            output_values.append(label)
            output_option_map[label] = idx
        if not output_values:
            output_values = ["(вывод звука не найден)"]
        output_selected_idx = CONFIG_MGR.get_output_device_index()
        output_value = next((label for label, idx in output_option_map.items() if idx == output_selected_idx), output_values[0])
        output_var, _ = field_dropdown(self, devices_body, "Вывод звука", output_values, output_value)
        mic_status_var = tk.StringVar(value="Готов к проверке")
        action_row = tk.Frame(devices_body, bg=Theme.CARD_BG)
        action_row.pack(fill="x", pady=(2, 0))
        create_action_button(action_row, "Проверить микрофон", lambda: self.test_microphone_device(callback=lambda ok, msg: mic_status_var.set(msg)), side="left")
        tk.Label(action_row, textvariable=mic_status_var, bg=Theme.CARD_BG, fg=Theme.FG_SECONDARY, font=("Segoe UI", 9)).pack(side="left", padx=(10, 0))

        _, voice_body = create_section_card(inner, "Голос и TTS", "Голосовые движки отделены от ИИ, чтобы было проще искать проблему и настраивать качество.")
        voice_values = self._voice_names()
        voice_value = self._selected_voice_label()
        voice_var, _ = field_dropdown(self, voice_body, "Голос Windows TTS", voice_values or ["(голоса не найдены)"], voice_value or (voice_values[0] if voice_values else ""), hint="Работает offline через pyttsx3 и остается самым надежным fallback-вариантом.")
        rate_var, _, _ = field_slider(self, voice_body, "Скорость голоса", 150, 350, float(CONFIG_MGR.get_voice_rate()), 1, " сим/мин")
        volume_var, _, _ = field_slider(self, voice_body, "Громкость", 0.2, 1.0, float(CONFIG_MGR.get_voice_volume()), 0.01)

        tts_provider_items = [
            ("pyttsx3 — offline / стабильно", "pyttsx3"),
            ("Edge-TTS — online / быстро", "edge-tts"),
            ("ElevenLabs — online / красиво", "elevenlabs"),
        ]
        current_tts_provider = CONFIG_MGR.get_tts_provider()
        current_tts_provider_label = next((label for label, key in tts_provider_items if key == current_tts_provider), tts_provider_items[0][0])
        tts_provider_var, _ = field_dropdown(self, voice_body, "Источник TTS", [label for label, _key in tts_provider_items], current_tts_provider_label, hint="pyttsx3 и Edge-TTS подходят почти всем. ElevenLabs нужен только если реально важна красота голоса.")
        provider_fields = tk.Frame(voice_body, bg=Theme.CARD_BG)
        provider_fields.pack(fill="x", pady=(2, 0))
        edge_voice_var, edge_voice_entry = field_entry(self, provider_fields, "Edge-TTS voice", CONFIG_MGR.get_edge_tts_voice())
        eleven_key_var, eleven_key_entry = field_entry(self, provider_fields, "ElevenLabs API key", CONFIG_MGR.get_elevenlabs_api_key(), show="*")
        eleven_voice_var, eleven_voice_entry = field_entry(self, provider_fields, "ElevenLabs voice_id", CONFIG_MGR.get_elevenlabs_voice_id())
        eleven_model_var, eleven_model_entry = field_entry(self, provider_fields, "ElevenLabs model_id", CONFIG_MGR.get_elevenlabs_model_id(), hint="Например: eleven_flash_v2_5 для минимальной задержки.")

        def _toggle_provider_fields(*_args):
            provider_key = next((key for label, key in tts_provider_items if label == str(tts_provider_var.get() or "").strip()), "pyttsx3")
            for widget in (edge_voice_entry.master, eleven_key_entry.master, eleven_voice_entry.master, eleven_model_entry.master):
                try:
                    widget.pack_forget()
                except Exception:
                    pass
            if provider_key == "edge-tts":
                edge_voice_entry.master.pack(fill="x", pady=(0, 10))
            elif provider_key == "elevenlabs":
                eleven_key_entry.master.pack(fill="x", pady=(0, 10))
                eleven_voice_entry.master.pack(fill="x", pady=(0, 10))
                eleven_model_entry.master.pack(fill="x", pady=(0, 10))

        try:
            tts_provider_var.trace_add("write", _toggle_provider_fields)
        except Exception:
            pass
        _toggle_provider_fields()

        _, listening_body = create_section_card(inner, "Слышимость и wake-word", "Эти параметры отвечают за чувствительность к вашему голосу и реакцию на слово «Джарвис».")
        listening_items = [("1 — базовый", "normal"), ("2 — усиленный", "boost"), ("3 — максимальный", "aggressive")]
        current_listening = CONFIG_MGR.get_listening_profile()
        current_listening_label = next((label for label, key in listening_items if key == current_listening), listening_items[0][0])
        listening_var, _ = field_dropdown(self, listening_body, "Профиль слышимости", [label for label, _key in listening_items], current_listening_label, hint="Базовый профиль чище и безопаснее. Усиленные профили лучше слышат, но чаще цепляют фон.")
        create_note_box(listening_body, "Если JARVIS плохо слышит wake-word, попробуйте сначала правильный микрофон, потом wake-word boost, и только после этого усиленный профиль слышимости.", tone="soft")

        def save_audio():
            try:
                selected_mic = str(mic_var.get() or "").strip()
                mic_idx = mic_index_map.get(selected_mic)
                mic_name = ""
                if mic_idx is not None:
                    selected_mic_item = _get_audio_device_entry(mic_idx, refresh=False)
                    if selected_mic_item is not None:
                        mic_name = _expand_audio_device_name(selected_mic_item.get("name"), "input")
                selected_output = str(output_var.get() or "").strip()
                output_idx = output_option_map.get(selected_output)
                output_name = ""
                if output_idx is not None:
                    selected_output_item = _get_audio_device_entry(output_idx, refresh=False)
                    if selected_output_item is not None:
                        output_name = _expand_audio_device_name(selected_output_item.get("name"), "output")

                voice_index = CONFIG_MGR.get_voice_index()
                selected_voice = str(voice_var.get() or "").strip()
                if selected_voice and voice_values and selected_voice in voice_values:
                    voice_index = voice_values.index(selected_voice)

                selected_provider = next((key for label, key in tts_provider_items if label == str(tts_provider_var.get() or "").strip()), "pyttsx3")
                eleven_key = str(eleven_key_var.get() or "").strip()
                eleven_voice = str(eleven_voice_var.get() or "").strip()
                if selected_provider == "elevenlabs" and (not eleven_key or not eleven_voice):
                    messagebox.showwarning(app_brand_name(), "Для ElevenLabs нужны API key и voice_id.\nПока переключаю голос на безопасный offline-режим pyttsx3.")
                    selected_provider = "pyttsx3"

                selected_listening = next((key for label, key in listening_items if label == str(listening_var.get() or "").strip()), "normal")
                CONFIG_MGR.set_many({
                    "mic_device_index": mic_idx,
                    "mic_device_name": mic_name,
                    "output_device_index": output_idx,
                    "output_device_name": output_name,
                    "voice_index": int(voice_index),
                    "voice_rate": int(rate_var.get()),
                    "voice_volume": float(volume_var.get()),
                    "tts_provider": selected_provider,
                    "edge_tts_voice": str(edge_voice_var.get() or "").strip(),
                    "elevenlabs_api_key": eleven_key,
                    "elevenlabs_voice_id": eleven_voice,
                    "elevenlabs_model_id": str(eleven_model_var.get() or "").strip(),
                    "listening_profile": selected_listening,
                })

                self.reload_services()
                self.refresh_mic_status_label()
                self.refresh_output_status_label()
                self.refresh_tts_status_label()
                self.set_status("Аудио-настройки сохранены", "ok")
                self._schedule_settings_visual_refresh()
                messagebox.showinfo(app_brand_name(), "Аудио-настройки сохранены.")
            except Exception as e:
                self.report_error("Ошибка сохранения аудио-настроек", e, speak=False)
                messagebox.showerror(app_brand_name(), str(e))

        action_row = tk.Frame(inner, bg=Theme.BG_LIGHT)
        action_row.pack(fill="x", padx=18, pady=(0, 14))
        create_action_button(action_row, "Сохранить аудио", save_audio, bg=Theme.ACCENT, side="left")

    SettingsUiMixin._create_scrollable_settings_host = _create_scrollable_settings_host
    SettingsUiMixin._schedule_settings_visual_refresh = _schedule_settings_visual_refresh
    SettingsUiMixin._build_embedded_settings_page = _build_embedded_settings_page
    SettingsUiMixin._create_settings_tab1 = _create_settings_tab1
    SettingsUiMixin._create_settings_tab_audio = _create_settings_tab_audio

    SettingsUiMixin._polish_20260328_applied = True
