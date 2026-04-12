# JARVIS Unity 22.5.0

22.5.0 — это уже не промежуточная сборка с экспериментами в интерфейсе, а выровненный релиз под обычного пользователя: короче onboarding, чище настройки, честный private-режим и локальный runtime без giant installer.

## Что изменилось

- Упрощён первый запуск:
  - обязательные поля сведены к реальному минимуму;
  - выбор AI-режима остаётся в конце onboarding;
  - для `private` больше не требуется ключ Groq на завершение регистрации, достаточно Telegram bot token и Telegram ID.
- Private-режим стал реально подготавливаемым для обычного пользователя:
  - приложение сначала пытается поднять portable Ollama через официальный Windows zip;
  - runtime и модели складываются в `%LOCALAPPDATA%\JarvisAi_Unity\runtime`;
  - если portable-путь не поднялся, открывается официальный `OllamaSetup.exe` как fallback;
  - в обычном UX это сведено к одной кнопке `Подготовить локальный режим`.
- Локальная диагностика больше не тормозит экран настроек:
  - passive probe локальной модели больше не стартует сам по себе на каждый рендер;
  - диагностика запускается только по явному действию пользователя;
  - это убирает лишние лаги и закрывает lifecycle-crash полного `pytest` на Windows.
- Settings снова выровнены под обычного пользователя:
  - секции по умолчанию свёрнуты;
  - `Для опытных` оставляет только дополнительные облачные ключи;
  - ручной `llama.cpp/.gguf` путь больше не торчит как обязательная часть пользовательского сценария.
- Nubik снова ведёт себя как навигатор, а не как шум:
  - подсказки остаются короткими;
  - help подхватывается не только по hover, но и по клику на секции и настройки.

## Что осталось внутри, но не навязывается пользователю

- Поддержка `llama.cpp` и ручной локальной модели остаётся в коде как advanced/fallback слой.
- Managed local runtime идёт через Ollama как основной пользовательский путь.
- Старый compatibility-слой настроек пока не вырезан полностью, чтобы не ломать апдейт существующим пользователям.

## Проверка

- `ruff check .`
- `python -m compileall -q app core tests tools`
- `pytest -q` → `318 passed`
- `powershell -ExecutionPolicy Bypass -File .\build\build_release.ps1` → OK
- packaged portable smoke:
  - `QT_QPA_PLATFORM=offscreen`
  - `JARVIS_UNITY_DISABLE_STARTUP_REGISTRY=1`
  - `JARVIS_UNITY_DISABLE_WAKE=1`
  - приложение успешно стартовало из `dist\JarvisAi_Unity\JarvisAi_Unity.exe` и прожило smoke-окно без падения (`SMOKE_OK`)

## Артефакты Windows

- `JarvisAi_Unity_22.5.0_windows_installer.exe`
- `JarvisAi_Unity_22.5.0_windows_portable.zip`
- `JarvisAi_Unity_22.5.0_windows_onefile.exe`
