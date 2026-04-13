# JARVIS Unity 20.5.0

20.5.0 is the recovery release for the desktop build. It rolls back the worst product regressions from the 22.5.x line without throwing away the useful infrastructure work.

## What Changed

- Telegram transport keeps the pooled `httpx` client and parallel dispatch, but the dialog path is less over-shaped and no longer wraps every normal message in a special Telegram-only AI prompt.
- Update UX is restored: Settings now exposes both `Установить обновление` and `Скачать обновление`, instead of hiding the actual update action behind a release link only.
- Voice routing is less aggressive after wake-word detection: distorted wake forms like `жаравис`, `дарвис`, and `рыж` now fall back into conversation more reliably instead of being treated as useless noise.
- Chat autoscroll is simplified back to one follow-bottom contract instead of the fragile pending/retry state machine that caused lag and lost tracking on new messages.
- AI/chat output is less over-sanitized. The app keeps execution cards for local actions and no longer flattens every reply into an artificially dry plain-text block.
- First-run and registration copy is cleaned up around cloud AI / Telegram wording instead of exposing the old Groq-specific phrasing in the visible UI.
- Runtime version is now `20.5.0`, while release publishing can still use a bridge GitHub tag for legacy updater compatibility from already installed `22.5.1` clients.

## Verification

- `python -m pytest -q` -> green in the release workspace before publish
- `python -m pytest -q tests/integration/test_release_hygiene.py tests/unit/test_release_acceptance_contract.py tests/unit/test_update_service.py tests/unit/test_ai_service.py tests/unit/test_chat_bridge.py tests/unit/test_command_router.py tests/unit/test_service_container.py` -> green in the release workspace before publish
- `python -m ruff check core/ai/ai_service.py core/routing/command_router.py core/routing/text_rules.py core/services/service_container.py core/telegram/telegram_service.py core/updates/update_service.py core/voice/speech_capture_service.py ui/bridge/chat_bridge.py ui/bridge/registration_bridge.py tests/unit/test_ai_service.py tests/unit/test_chat_bridge.py tests/unit/test_command_router.py tests/unit/test_release_acceptance_contract.py tests/unit/test_service_container.py tests/unit/test_update_service.py` -> green in the release workspace before publish

## Status

The source tree is aligned to `20.5.0` and intended for a release publish only after installer smoke, Telegram smoke, voice/wake smoke, and update-screen smoke are complete.
