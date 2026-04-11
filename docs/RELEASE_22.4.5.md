# JARVIS Unity 22.4.5

22.4.5 is the final release for this cycle. The project version, release notes, and release hygiene checks are aligned again.

## What Changed

- Version source moved to `22.4.5`.
- Release metadata and README asset names were updated to the final build.
- The unfinished Local AI profile was removed from the user-facing settings flow.
- Source runs now reuse the checked build Vosk cache, so wake-word runtime matches the packaged build more closely.
- Release hygiene tests now validate committed build sources instead of the generated installer script.

## Verification

- `pytest -q`
- `ruff check app core tests tools ui`
- `python -m compileall app core ui tests`

## Status

Final version is out.
