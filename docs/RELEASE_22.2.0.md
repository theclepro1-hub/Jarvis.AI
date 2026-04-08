# Release 22.2.0

## Main Changes

- Wake/STT path got another pass: common wake-word mistakes are cleaned before routing, post-wake capture starts with pre-roll audio, and command capture closes faster after silence.
- Text chat, voice chat, and Telegram now follow the same contract: local commands stay local, ordinary conversation goes to AI, and broken command fragments prefer clarification over `Не понял`.
- Batch command parsing is stronger for chained бытовые commands, especially when one open verb should apply to multiple targets.
- Telegram transport is more robust under a message burst: polling and dispatch are separated so one slow reply does not block the whole channel as easily.
- Settings-side heavy actions moved behind single-flight guards: Telegram test and update checks no longer should stack on repeated clicks.
- Update flow is no longer only a checker in the backend: the app can download the preferred installer asset and launch it from the settings path.
- Windows integration was tightened: explicit AppUserModelID is set at startup, installer metadata is richer, and installer build keeps uninstall metadata and restart flags.
- Runtime fallback for generic `музыка` no longer silently jumps into Windows Media Player when the user did not choose that path.
- Settings persistence is more resilient on Windows when `settings.json` is contended by another live process.
- Startup path got extra instrumentation so boot-time regressions can be measured instead of guessed.

## User-Facing Effects

- `привет`, `как дела`, `что умеешь` and similar messages should go to AI again instead of collapsing into local `Не понял`.
- `Джарвис, открой ютуб` and similar voice commands have a better chance of keeping the start of the phrase after wake.
- Prefix garbage like `гарви с`, `жарвис`, `джервис` at the beginning of a phrase is stripped before command routing.
- Telegram should feel less like a one-message-at-a-time queue and more like the same assistant logic as the main chat.
- Repeated presses on `Проверить обновления` or Telegram test should not pile up parallel blocking operations in the UI.
- Generic `включи музыку` now prefers the chosen/default music app instead of silently falling back to system music.

## Release Artifacts

- `JarvisAi_Unity_22.2.0_windows_installer.exe`
- `JarvisAi_Unity_22.2.0_windows_onefile.exe`
- `JarvisAi_Unity_22.2.0_windows_portable.zip`
