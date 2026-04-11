# JARVIS Unity 22.5.5

22.5.5 is a small release-hygiene pass. It keeps the runtime contract unchanged while trimming a little work from cold start and keeping release metadata aligned.

## What Changed

- Deferred the application icon setup in `app/bootstrap.py` until after the single-instance check so second launches exit earlier without doing extra setup work.
- Made the assistant-mode policy module lazy-load `LocalLLMService` instead of importing it at module import time.
- Restored a clean release version bump to `22.5.5` and added a matching release note entry in `README.md`.

## Verification

- `.\.venv\Scripts\python.exe -m ruff check app/bootstrap.py core/services/service_container.py core/policy/assistant_mode.py`
- `.\.venv\Scripts\python.exe -m pytest tests/unit/test_service_container.py tests/integration/test_release_hygiene.py -q`

## Notes

- This release does not change the visible UI contract.
- The existing local LLM readiness rules remain honest: unavailable local runtimes stay reported as unavailable.
