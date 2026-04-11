# JARVIS Unity 22.5.0

22.5.0 is the final assistant-mode release. It closes the remaining release blockers, switches GitHub distribution to installer-only, and keeps the product contract honest around local/cloud routing.

## What Changed

- Finalized the unified `assistant_mode` contract across registration, settings, voice routing, text AI, and STT.
- Fixed the last release-critical reliability and security issues around settings secrets, Telegram error handling, reminder recovery, chat history hydration, and service-container races.
- Added a real local LLM layer with `llama_cpp` and `Ollama` backends plus explicit readiness reporting.
- Hardened local LLM status so `Ollama` is reported as not ready when the daemon is up but the requested model is not installed.
- Moved the GitHub release flow to installer-only distribution.
- `build/build_release.ps1` now supports `-InstallerOnly` and publishes only the Windows installer plus checksum in that mode.

## Verification

- `C:\JarvisAi_Unity\.venv\Scripts\python.exe -m ruff check .`
- `C:\JarvisAi_Unity\.venv\Scripts\python.exe -m pytest -q`
- Installer-only release build completed successfully.
- Packaged offscreen smoke passed for the built `dist\JarvisAi_Unity\JarvisAi_Unity.exe`:
  app bootstrap completed, `App.qml` loaded, bridges initialized, and lazy services started.

## Runtime Notes

- `llama.cpp` requires both the `llama_cpp` Python package and a configured `.gguf` model path.
- `Ollama` requires a reachable daemon and an installed local model.
- On this machine, the daemon responds but no Ollama models are installed, so generation through the local backend is honestly reported as unavailable instead of silently pretending to be ready.

## Release Assets

- `JarvisAi_Unity_22.5.0_windows_installer.exe`
- `JarvisAi_Unity_22.5.0_windows_installer.exe.sha256.txt`
