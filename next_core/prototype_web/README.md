# JARVIS NEXT Prototype

Это исполняемый пролог и первый рабочий shell для `next_core`.

## Запуск

```powershell
python scripts/run_next_core_prototype.py
```

По умолчанию поднимется локальный сервер и откроется:

`http://127.0.0.1:8765/next_core/prototype_web/index.html`

## Полезные режимы

- `?state=hub` — сразу открыть хаб, минуя катсцену.
- `?scene=identity` — открыть конкретную сцену пролога.
- `?scene=modes` — быстро проверить режимы и композицию.

## Что уже есть

- катсцена из `next_core/prologue_scene.json`
- стиль из `next_core/design_tokens.json`
- переход в хаб без боковой визуальной свалки
- wide/compact shell
- `Меню` только в compact-режиме
- composer и базовый живой диалог после входа

## Что это не делает

Это не legacy `jarvis.py` и не старый Tk-UI. Это новая основа под `JARVIS NEXT`.
