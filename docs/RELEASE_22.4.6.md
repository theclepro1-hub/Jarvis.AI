# JARVIS Unity 22.4.6

22.4.6 is a release-hardening build based on 22.4.5.

## What Changed

- Stabilized manual speech recognition with worker shutdown, timeout handling, and safer cancellation paths.
- Reduced noisy voice routing by keeping non-command speech out of local app actions and cloud fallback unless it is clearly dialogue.
- Improved chat scroll behavior so manual scroll position survives tab changes and auto-scroll only follows when the user is already near the bottom.
- Cleaned the Voice screen by removing the verbose technical status card while keeping backend diagnostics available for tests and future debug mode.
- Removed obsolete QML components that were no longer imported by the interface.
- Localized the user-facing Local assistant profile text.
- Hardened bootstrap, release hygiene, text encoding, voice bridge lifecycle, and runtime tests.

## Verification

- `ruff check .`
- `pytest -q -k "not e2e"`
- PyInstaller release build through `build/build_release.ps1`
- Clean-start smoke checks with isolated `JARVIS_UNITY_DATA_DIR`

## Known Notes

- Wake recognition still needs a separate product pass and real microphone tuning. This release does not claim final wake quality.
