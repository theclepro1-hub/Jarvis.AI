# Security Notes

## Current Risks

- Registration secrets are stored through Windows DPAPI and are not written to `settings.json` as plaintext on Windows.
- The local wake model is bundled into release artifacts; the app must not claim wake readiness before the model and stream are ready.
- Groq API requests are sent only after the user has filled registration data or explicitly uses AI/voice capture.
- Windows startup is controlled through the current user `Run` registry key.

## What is acceptable for `22.0.0`

- Secrets are not committed to git.
- Registration secrets are protected at rest with Windows DPAPI in the Windows build.
- Wake word detection stays local.
- Manual mic capture is explicit and user-initiated.
- Startup can be disabled from the UI and through the `JARVIS_UNITY_DISABLE_STARTUP_REGISTRY` env flag for tests.

## What should be revisited later

- Adding a guided local model repair step if the bundled model is missing or corrupted.
- Moving to a more explicit privacy status model for wake vs. STT vs. AI routing.
