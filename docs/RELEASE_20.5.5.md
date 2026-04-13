# JARVIS Unity 20.5.5

20.5.5 is the final recovery-and-polish release for the 20.x line. It keeps updater compatibility for existing 22.5.1 installs, but the product surface, runtime identity, chat behavior, voice path, and release UX are now aligned around `20.5.5`.

## What Changed

- Telegram was split into a real fast lane for local commands and an AI lane for normal replies, with shared HTTP client reuse and per-chat short memory.
- Fast local Telegram actions no longer need to wait behind normal chat traffic, and Telegram replies are compacted for chat readability.
- Assistant modes were separated more honestly: `fast`, `standard`, `smart`, and `private` no longer pretend to be different only by label.
- AI prompt building now pushes Russian prompts to stay Russian, answer broad questions directly, and avoid useless clarification-first replies.
- `fast` mode keeps a provider/model fallback path, but now has a safer latency/token budget so it degrades less often into empty or cut-off replies.
- Wake and noisy STT handling were softened again for real speech: aliases like `жаравис`, `дарвис`, and `рыж` are treated as live wake-like input instead of dead noise.
- Voice/chat routing no longer over-eagerly throws conversational wake phrases into `Не расслышал команду`.
- Update UX was restored: the Settings screen keeps both `Установить обновление` and `Скачать обновление`, with a stable GitHub release fallback for manual download.
- Chat autoscroll was simplified. The old retry-heavy bottom-follow machine was removed in favor of a smaller contract that follows new messages when the user is already at the bottom and stops pulling when the user scrolls away.
- Startup was optimized with lighter imports and QML prewarm, reducing first-open stall without changing the visible app contract.
- Runtime/release identity was cleaned up: product display version is `20.5.5`, updater version is `22.5.5`, and stale version-specific single-instance/setup tails were removed.
- First-run onboarding is now consistent again: non-private mode is honestly Groq-first, while private mode only requires Telegram on first start.

## Versioning

- Product display version: `20.5.5`
- Internal updater version: `22.5.5`
- Why this split exists: existing `22.5.1` installs must still see this release as newer through the updater, so the GitHub release tag stays monotonic in the 22.x stream.

## Verification

- `python -m pytest -q` -> `394 passed`
- `python -m ruff check .` -> clean
- `powershell -ExecutionPolicy Bypass -File C:\JarvisAi_Unity\build\build_release.ps1` -> green
- Smoke launch of `C:\JarvisAi_Unity\dist\JarvisAi_Unity\JarvisAi_Unity.exe` -> process and window `JARVIS Unity v20.5.5` came up successfully

## Release Assets

- `JarvisAi_Unity_20.5.5_windows_installer.exe`
- `JarvisAi_Unity_20.5.5_windows_portable.zip`
- `JarvisAi_Unity_20.5.5_windows_onefile.exe`
- matching `.sha256.txt` checksum files
