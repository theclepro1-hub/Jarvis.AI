# JARVIS Unity 22.5.0

22.5.0 — это финальная замена релиза с выровненным интерфейсом, локальным private/runtime-контуром и добитым Telegram-path без лишней технической свалки для пользователя.

## Что вошло в релиз

- Первый запуск и настройки остались короткими и пользовательскими.
- Private/local runtime больше не выглядит фейковым режимом: локальная модель и runtime проверяются честно.
- Wake и voice-контур уже выровнены под обычный сценарий без лишнего UI-мусора.
- Дополнительные провайдерные и runtime-настройки остаются глубже и не лезут в основной UX.

## Что исправлено в Telegram

- Telegram теперь разделяет быстрые локальные команды и AI-ответы:
  - команды вроде `открой ютуб`, `следующее`, `пауза`, `напомни` больше не должны ждать обычную болтовню;
  - AI-диалог идёт отдельной полосой обработки.
- Transport переведён на один долгоживущий `httpx.Client`:
  - меньше лишних переподключений;
  - reuse соединения для `getUpdates`, `sendMessage` и `sendChatAction`;
  - предсказуемее работает timeout и proxy.
- Telegram получил короткую память по `chat_id`:
  - короткий контекст последних сообщений учитывается только внутри конкретного Telegram-чата;
  - память не смешивается с desktop chat.
- Для AI-ответов добавлен компактный Telegram-стиль:
  - ответ короче и суше;
  - меньше лишней “ассистентской воды”.
- Для длинного AI-пути включён промежуточный `typing`-сигнал через `sendChatAction`.
- `proxy_mode`, `proxy_url` и `timeout_seconds` теперь реально участвуют в пересоздании Telegram transport без необходимости менять токен или перезапускать приложение.
- Reset-path стал безопаснее:
  - при `Удалить все данные` Telegram transport закрывается;
  - offset/state не должны дописываться поверх сброса из завершившихся фоновых dispatch-задач.

## Внутренние изменения

- `core/services/service_container.py`
  - command-first обработка Telegram вынесена в явный fast/ai split;
  - добавлена короткая in-memory history по `telegram_chat_id`;
  - Telegram transport теперь получает network proxy settings полностью.
- `core/telegram/telegram_service.py`
  - persistent `httpx.Client`;
  - fast/ai dispatch pools;
  - `sendChatAction` throttle;
  - refresh transport при изменении network settings;
  - reset-guard для transport и offset persistence.

## Проверка

- `python -m pytest -q tests/unit tests/integration` → `328 passed`
- `python -m pytest -q tests/ui/test_shell_ui.py` → `12 passed`
- `python -m pytest -q tests/unit/test_telegram_service.py tests/unit/test_service_container.py tests/unit/test_release_acceptance_contract.py tests/unit/test_app_background_services.py` → `49 passed`
- `python -m ruff check .` → `All checks passed`
- `python -m compileall -q app core tests tools` → OK
- `powershell -ExecutionPolicy Bypass -File .\build\build_release.ps1` → OK

## Примечание по полному pytest

- Агрегированный `pytest -q` в этом окружении остаётся нестабильным из-за нативного Qt/PySide access violation в общем прогоне.
- Сам проблемный UI-набор `tests/ui/test_shell_ui.py` отдельно проходит полностью.
- Для этого релизного прохода ориентир — зелёные unit/integration и отдельный зелёный UI-shell прогон.

## Артефакты Windows

- Основной GitHub-артефакт для пользователя: `JarvisAi_Unity_22.5.0_windows_installer.exe`
- `portable` и `onefile` остаются внутренними release-артефактами для диагностики и smoke-проверок.
