# JarvisAi Unity

`JarvisAi Unity` is a full rebuild of JARVIS as a modern desktop assistant.

## Principles

- New codebase in `C:\JarvisAi_Unity`
- No direct UI migration from `C:\jarvisAI`
- Chat-first layout
- Fast local command routing
- Clean registration flow with editable connections in Settings
- Compact settings with an optional `Нубик` guide

## Stack

- Python 3.11.9 for the current build environment, project requirement `>=3.11`
- PySide6 6.11
- Qt Quick / QML
- OpenAI-compatible Groq client via `openai`
- `sounddevice` + `numpy` for manual mic capture
- `vosk` for always-on local wake word
- bundled `Golos Text` font for stable Cyrillic rendering in QML
- generated Windows icon in `assets/icons/jarvis_unity.ico`

## User Data

- Installed app: `C:\Program Files\JARVIS Unity` by default when using the installer
- User settings and protected secrets: `%LOCALAPPDATA%\JarvisAi_Unity\settings.json`
- Chat history: `%LOCALAPPDATA%\JarvisAi_Unity\chat_history.json`
- Telegram polling state: `%LOCALAPPDATA%\JarvisAi_Unity\telegram_state.json`

Deleting `%LOCALAPPDATA%\JarvisAi_Unity` resets first-run registration.

## Run

```powershell
C:\JarvisAi_Unity\.venv\Scripts\python.exe -m app.main
```

## Dev Checks

```powershell
C:\JarvisAi_Unity\.venv\Scripts\ruff.exe check C:\JarvisAi_Unity
C:\JarvisAi_Unity\.venv\Scripts\pytest.exe -q
```

## Build

```powershell
powershell -ExecutionPolicy Bypass -File C:\JarvisAi_Unity\build\build_release.ps1
```

## Release Assets

The release build produces:

- `JarvisAi_Unity_22.1.0_windows_installer.exe`
- `JarvisAi_Unity_22.1.0_windows_onefile.exe`
- `JarvisAi_Unity_22.1.0_windows_portable.zip`

## Release Notes

- [Release 22.1.0](docs/RELEASE_22.1.0.md)
- [Release 22.0.0](docs/RELEASE_22.0.0.md)
- [Release Readiness](docs/RELEASE_READINESS.md)
- [Security Notes](docs/SECURITY.md)

## Voice Runtime

- manual mic capture uses `sounddevice`
- transcription uses Groq Whisper STT after capture
- always-on local wake word uses a bundled Vosk Russian model and reports readiness only after the local model and microphone stream are actually available
- registration secrets are protected with Windows DPAPI in the Windows build
