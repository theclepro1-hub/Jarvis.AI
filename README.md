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
- local wake detection built on speech bursts + `faster-whisper`
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

- `JarvisAi_Unity_<version>_windows_installer.exe`
- `JarvisAi_Unity_<version>_windows_onefile.exe`
- `JarvisAi_Unity_<version>_windows_portable.zip`

## Release Notes

- [Release 20.5.5](docs/RELEASE_20.5.5.md)
- Legacy notes:
  - [Release 22.5.1](docs/RELEASE_22.5.1.md)
  - [Release 22.4.5](docs/RELEASE_22.4.5.md)
- [Release 22.2.0](docs/RELEASE_22.2.0.md)
- [Release 22.1.1](docs/RELEASE_22.1.1.md)
- [Release 22.1.0](docs/RELEASE_22.1.0.md)
- [Release 22.0.0](docs/RELEASE_22.0.0.md)
- [Release Readiness](docs/RELEASE_READINESS.md)
- [Security Notes](docs/SECURITY.md)

## Voice Runtime

- manual mic capture uses `sounddevice`
- local STT and wake recognition use `faster-whisper`
- cloud STT still uses Groq Whisper when policy routes there
- the release build first tries to preseed and bundle the local `faster-whisper` cache from explicit/local caches (`JARVIS_UNITY_FASTER_WHISPER_SEED_DIR`, `%LOCALAPPDATA%`, installed app assets) before it attempts a network download
- if no local snapshot is available, the frozen app falls back to `%LOCALAPPDATA%` for the first model download instead of writing into the bundled runtime
- registration secrets are protected with Windows DPAPI in the Windows build
