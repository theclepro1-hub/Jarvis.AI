# JARVIS AI 2.0

Отдельная ветка настольного ассистента со своим runtime, релизным контуром и пространством пользовательских данных.

## Текущий релиз

- Продукт: `JARVIS AI 2.0`
- Версия: `20.0.0`
- GitHub-репозиторий по умолчанию: `theclepro1-hub/Jarvis.AI`
- Пространство пользовательских данных: `JarvisAI2`

## На чём сфокусирован 20.0.0

- Полный отказ от `ui_rewrite` как активного runtime и возврат на стабильный shell/control-center фундамент
- Возврат красивого chat-first экрана с левой панелью, реальными asset-кнопками `send` и `mic` и кликабельным Нубиком
- Возврат полноэкранного центра настроек с `noob2` и общей стабильной навигацией без самостоятельной геометрии каждой вкладки
- Возврат встроенной активации: до регистрации чат блокируется, после активации открывается тот же рабочий экран
- Фиксация важных кликов: микрофон, ввод, отправка, навигация центра настроек и gate-submit
- Стабилизация smoke/crash-проверок под новый UI-фундамент

## Важные модули

- `jarvis_ai/branding.py` — имя продукта, версия, имена релизных файлов
- `jarvis_ai/runtime.py` — runtime path helpers и разбор геометрии окна
- `jarvis_ai/audio_devices.py` — поиск аудиоустройств и автоподбор микрофона
- `jarvis_ai/commands.py` — команды, wake-word и динамические действия
- `jarvis_ai/custom_actions_store.py` — хранение визуальных пользовательских действий
- `jarvis_ai/action_permissions.py` — режимы доверия и подтверждения опасных действий
- `jarvis_ai/environment_doctor.py` — проверки окружения и отчёты Doctor
- `jarvis_ai/runtime_shell.py` — chat-first shell и live-context
- `jarvis_ai/runtime_system_ui.py` — память, сценарии, журнал, Doctor, системные операции
- `jarvis_ai/app_mixins/settings_ui.py` — центр настроек
- `jarvis_ai/app_mixins/chat_ui.py` — чат, история и отправка сообщений
- `jarvis_ai/app_mixins/voice_pipeline.py` — голосовой ввод, ручное прослушивание и STT

## Что заметит пользователь

- Главный экран теперь держит в центре только разговор
- Техничка вынесена в `Система` и `Диагностика`
- `Что услышал JARVIS` и `Что делает JARVIS` живут в верхнем статусе, а не в отдельной колонке
- Микрофон можно удерживать для быстрой команды
- Настройки и активация занимают весь экран приложения, а не часть контента
- Интерфейс стал крупнее и лучше переносит сужение окна

## Релизный контур

- Локальная сборка: `build_release.bat`
- Полная публикация: `ONE_CLICK_PUBLISH.bat`
- Вспомогательные инструменты: `publish_tools/`

Сборка и проверка используют:

- `python -m compileall jarvis.py jarvis_ai scripts tests`
- `pytest`
- `python scripts/unit_checks.py`
- `python scripts/crash_test.py`
- `python scripts/release_smoke_check.py`

Артефакты появляются в:

- `release/jarvis_ai_2.exe`
- `release/JarvisAI2_Setup.exe`

## Дополнительно

- Безопасный запуск: `python jarvis.py --safe-mode`
- Текущий список задач: `TASKS.md`
- Карта проекта: `ARCHITECTURE.md`
- История изменений: `CHANGELOG.md`
