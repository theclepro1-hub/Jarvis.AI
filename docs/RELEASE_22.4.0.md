# JARVIS Unity 22.4.0

22.4.0 — финальный стабилизационный билд. Этот релиз добивает публичный desktop-контур: голос, системные действия, updater/install, чат/статусы и release hygiene.

## Что вошло

- Новый локальный voice/STT путь:
  - добавлен `faster-whisper`;
  - `auto` и `balance` теперь могут идти по локальной цепочке `faster-whisper -> Vosk`;
  - сохранён fallback на старые пути.
- Wake/voice контур:
  - уменьшен handoff penalty после слова активации;
  - усилен local STT warm-up;
  - нижний статус больше не должен терять wake-смысл из-за AI latency.
- Planner и системные действия:
  - улучшена нормализация шумных голосовых фраз;
  - лучше проходят `параметры`, `проводник`, `панель управления`, `погромче`, bare system targets;
  - multi-action стал строже к ambiguous tail и меньше делает ложный partial success.
- Chat/UI:
  - автоскролл новых сообщений стал жёстче и больше не должен зависеть только от ответа ассистента;
  - очищены реальные UI-крокозябры и техмусор;
  - destructive reset вынесен в отдельный confirm-dialog;
  - `Обновления` стоят последними;
  - экран приложений не раскрывает ручную форму по умолчанию.
- Updater/install/runtime:
  - updater лучше переживает грязную сеть, retry и битый кеш installer;
  - apply flow остался installer-based, но стал честнее и устойчивее;
  - installer metadata/taskbar identity/startup контур выровнен под 22.4.0;
  - uninstall cleanup подтверждён: каталог установки удаляется.

## Проверка релиза

- `pytest -q` -> `270 passed`
- `ruff check app core tests tools ui` -> clean
- `python -m compileall app core ui tests` -> OK
- portable smoke -> OK
- onefile smoke -> OK
- installer silent install/uninstall smoke -> OK
- release build -> OK

## Остаточный риск

- Главный оставшийся стратегический риск — сам voice backend на чужом железе. Если после живого использования голос всё ещё будет вести себя игрушечно, следующий шаг уже не polish, а полная замена voice/wake основы.
