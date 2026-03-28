# Changelog

## [16.0.0] - 2026-03-28

- домашний экран полностью пересобран в chat-first shell: слева навигация и noob-помощник, в центре чат, справа голос и быстрые проверки
- удалены остатки старого стартового multi-mode поведения и лишние перегруженные блоки с домашнего экрана
- голосовой монитор теперь подбирает совместимую частоту устройства и больше не сыпет сырой `Invalid sample rate` на неподходящих микрофонах
- старт облегчен: фоновые noob-анимации запускаются мягче и позже, а shell быстрее приходит в рабочее состояние
- системный раздел собрал в одном месте readiness-check, проверку релиза, резервные копии, откат после обновления, диагностику ZIP и перенос пользовательских наборов
- улучшены подписи и объяснения в интерфейсе: меньше англо-русской мешанины, больше простых формулировок для обычного пользователя
- финальный цикл проверок расширен и подтвержден: `py_compile`, `unit_checks`, `crash_test`, `release_smoke_check` и полный `build_release`

## [15.5.0] - 2026-03-27

- turned `jarvisAI 2.0` into a standalone branch with its own release pipeline
- isolated config, database, logs, prompts, and update-state under `JarvisAI2`
- split branding, runtime, theme, storage, update helpers, scrolling, and clipboard logic into package modules
- split state, reminders, telegram bot, diagnostics, command parsing, setup wizard, and background effects into dedicated modules
- added local `build_release`, `publish_tools`, GitHub workflow, update manifest, and release notes flow
- cleaned the GitHub source bundle from `__pycache__`, bytecode, and temporary build directories
- changed the release build so final artifacts stay in `release/` and temporary build folders are removed after success
- prepared separate installer and executable names for side-by-side installation with the original app
