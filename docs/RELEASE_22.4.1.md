# JARVIS Unity 22.4.1

22.4.1 закрывает стартовые тормоза, убирает лишние подтверждения для системных power-команд и вычищает несколько реальных UX-залипаний без ломки рабочего Vosk/wake-контура.

## Что вошло

- Ускорен старт приложения:
  - версия вынесена в лёгкий модуль `core.version`;
  - `bootstrap` и `app` больше не тянут updater и тяжёлые сервисы раньше времени;
  - `ServiceContainer` теперь лениво импортирует AI, voice, updater, Telegram и роутеры.
- Снижен ранний UI-лаг:
  - initial chat hydration сдвинута после first paint;
  - initial catalog hydration вынесена из раннего GUI-path;
  - Apps scan/import переведён в фоновый поток и больше не должен стопорить экран «Приложения».
- Смягчён runtime-шум на старте:
  - Telegram и update path будятся позже;
  - их первое создание больше не должно происходить на самом раннем GUI-клике;
  - wake стартует позже и меньше мешает первому отклику UI.
- Исправлен lifecycle окна:
  - приложение больше не должно оставаться живым без окна при выключенном tray-режиме;
  - tray activation стал менее агрессивным;
  - скрытие в tray больше не показывает лишний balloon.
- Убрано голосовое подтверждение для системных power-команд:
  - `выключи компьютер`, `перезагрузи`, `сон`, `гибернация`, `выйди из системы` исполняются сразу, без фразы `подтверждаю`.
- Voice/Vosk path не сломан ради оптимизаций:
  - Vosk runtime сохранён;
  - тяжёлые Vosk/OpenAI импорты отложены до фактического использования;
  - fallback-контур сохранён.

## Что проверено

- `pytest -q`
- `ruff check app core tests tools ui`
- `python -m compileall app core ui tests`
- portable smoke
- onefile smoke
- installer launch smoke

## Замер старта

- portable: `bootstrap:after-runtime-start` около `0.33 c`
- onefile: `bootstrap:after-runtime-start` около `1.99 c`
- installed app: `bootstrap:after-runtime-start` около `1.31 c`

## Примечание

`onefile` на Windows всё ещё остаётся самым тяжёлым вариантом запуска из-за самораспаковки и внешнего сканирования системы. Для самого быстрого и предсказуемого старта лучше использовать installer или portable.

## Итог

22.4.1 — это финальный релиз на ускорение старта, снижение липких кликов, выправление window/tray lifecycle и стабилизацию desktop-контура без отката voice/system/update функциональности.
