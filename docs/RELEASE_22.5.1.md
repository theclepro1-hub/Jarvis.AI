# JARVIS Unity 22.5.1

22.5.1 is a stabilization release for the current desktop build. It fixes noisy voice/chat routing, cleans the first-use UI copy, and reduces first-click lag without re-expanding the interface.

## What Changed

- Version source moved to `22.5.1` and README release link now points to `22.5.1`.
- Startup now uses staged asynchronous QML component preloading plus light bridge `prewarm()` hooks, so `Voice`, `Apps`, and `Settings` open faster on the first click without creating hidden duplicate screens.
- Voice routing now keeps short wake/noise garbage out of the AI lane and normalizes more broken STT fragments before command parsing.
- Short typed noise like `раз больше` now asks for clarification instead of producing an ugly local failure card.
- AI replies are sanitized before they hit chat: raw markdown tables, heavy formatting, and long walls are flattened into plain text.
- Single-step local actions no longer render as redundant execution cards with the same text repeated twice.
- User-facing fallback copy no longer exposes provider errors like `Groq: empty response`.
- Registration and settings copy no longer hard-code the old `Groq + Telegram` phrasing.

## Verification

- `python -m pytest -q` → `354 passed`
- `python -m pytest -q tests/unit/test_ai_service.py tests/unit/test_chat_bridge.py tests/unit/test_ai_prompt_contract.py tests/unit/test_command_router.py tests/unit/test_settings_bridge.py tests/unit/test_voice_bridge.py tests/unit/test_voice_postprocessor.py tests/unit/test_apps_bridge.py` → `113 passed`
- `python -m ruff check core/ai/ai_service.py core/routing/text_rules.py core/routing/command_router.py core/intent/voice_postprocessor.py core/voice/speech_capture_service.py ui/bridge/chat_bridge.py ui/bridge/apps_bridge.py ui/bridge/settings_bridge.py ui/bridge/voice_bridge.py tests/unit/test_ai_service.py tests/unit/test_chat_bridge.py tests/unit/test_ai_prompt_contract.py tests/unit/test_command_router.py tests/unit/test_settings_bridge.py tests/unit/test_voice_bridge.py tests/unit/test_voice_postprocessor.py tests/unit/test_apps_bridge.py` → `OK`

## Status

The source tree is aligned to `22.5.1` and ready for release build generation.
