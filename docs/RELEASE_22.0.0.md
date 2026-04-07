# JarvisAi Unity 22.0.0

`22.0.0` is a new JARVIS generation built from scratch in `C:\JarvisAi_Unity`.
The old `C:\jarvisAI` project was used only as a behavior reference, not as a codebase to copy.

## What Changed Compared To The Original JARVIS

- New PySide6 + Qt Quick/QML desktop shell instead of the old UI stack.
- Offline-first command routing: local PC commands do not depend on AI or the internet.
- Unified execution cards for multi-step commands instead of scattered chat bubbles.
- New Apps resolver with categories, default music app behavior, and safer launcher discovery.
- New voice settings screen with microphone/output selection, wake status, manual mic, and JARVIS voice controls.
- New Settings flow: Groq and Telegram keys are editable after first run in `Settings -> Connections`.
- New first-run registration order: Groq key, Telegram bot token, Telegram ID.
- New tray/single-instance behavior: repeated launches should focus the existing JARVIS instead of spawning unlimited windows.
- Bundled Vosk wake model and `Golos Text` font for stable local wake/runtime and Cyrillic UI rendering.
- Packaged Windows outputs: installer, portable zip, and onefile exe.

## Latest Fixes In This Release

- Added `Connections` to Settings for Groq key, Telegram bot token, and Telegram ID.
- Telegram bot polling is faster and can refresh bot token/user ID without restarting the app.
- Telegram reminders now keep the source chat and send the due reminder back to Telegram.
- Volume up/down commands now target `+10` / `-10` volume changes instead of tiny system steps.
- Natural game/music aliases were expanded: `кс`, `кска`, `делочек`, `фортик`, `дбдшка`, `музычку`, and related forms.
- Registration links now match their fields: Groq keys, BotFather, and userinfobot.
- AI selection is exposed as one profile selector instead of separate confusing controls.
- Runtime data now lives under `%LOCALAPPDATA%\JarvisAi_Unity`, not in the project folder.
- Secrets are stored under the current Windows user profile and protected with Windows DPAPI.

## Data Storage

- Installed app: `C:\Program Files\JARVIS Unity` by default when using the installer.
- User data: `%LOCALAPPDATA%\JarvisAi_Unity`.
- Main settings: `%LOCALAPPDATA%\JarvisAi_Unity\settings.json`.
- Chat history: `%LOCALAPPDATA%\JarvisAi_Unity\chat_history.json`.
- Telegram polling state: `%LOCALAPPDATA%\JarvisAi_Unity\telegram_state.json`.

Deleting the app does not delete user settings. Deleting `%LOCALAPPDATA%\JarvisAi_Unity` resets first-run registration.

## Quality Gates

- UI clicks, scroll interactions, registration, settings connections, and command entry are covered by Qt UI tests.
- Offline command routing, Telegram routing, settings storage, launcher discovery, and voice contracts are covered by unit tests.
- `pytest`, `ruff`, and `compileall` passed before packaging.
- Portable, onefile, and installer assets are produced by the release script.
