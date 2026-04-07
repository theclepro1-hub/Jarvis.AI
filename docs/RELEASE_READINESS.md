# Release Readiness Checklist

## Must pass

- `pytest -q`
- `ruff check app core tests tools`
- `python -m compileall app core tests tools`
- portable EXE smoke starts and stays alive
- onefile EXE smoke starts and stays alive
- UI screenshots reviewed for:
  - registration
  - chat
  - voice
  - apps
  - settings

## Must not regress

- no white/native default control states
- no overlapped layout blocks
- no broken `Ctrl+V`
- no broken `Enter` send path
- no duplicate startup registration
- no temp data left tracked in git
- no raw driver dump in microphone picker

## Known risks accepted for `22.0.0`

- wake model is bundled at build time; if the download fails, build must fail before release
- PySide6 packaging is large because the UI runtime is bundled conservatively

## Release blockers

- wake status lying about readiness
- plaintext API keys or Telegram tokens in `settings.json` on Windows
- registration save not advancing to chat
- chat composer not sending on `Enter`
- obvious clipped or overlapping UI
- missing release artifacts or broken smoke startup
