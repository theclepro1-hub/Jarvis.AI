# JARVIS AI 2.0 Architecture

## Core layout

- `jarvis.py`: main application assembly and remaining `JarvisApp` orchestration.
- `jarvis_ai/branding.py`: product identity, version, filenames and window titles.
- `jarvis_ai/audio_devices.py`: microphone/output enumeration, cleanup, fallback discovery and auto-selection.
- `jarvis_ai/app_context.py`: explicit runtime context for config, prompts and database wiring.
- `jarvis_ai/state.py`: config/database/prompt state and config normalization.
- `jarvis_ai/commands.py`: wake-word logic, local command parsing and dynamic action lookup.
- `jarvis_ai/custom_actions.py`: optional manifest-based custom actions for repo-independent extensions.
- `jarvis_ai/service_hub.py`: centralized creation of Groq, reminders, Telegram and diagnostics services.
- `jarvis_ai/voice_profiles.py`: listening sensitivity profiles and device-aware tuning.
- `jarvis_ai/theme.py`, `jarvis_ai/ui_factory.py`: visual system primitives, action grids and wrap-aware UI builders.
- `jarvis_ai/settings_forms.py`: reusable settings form fields and hint rows shared by the polished settings UI.
- `jarvis_ai/app_mixins/chat_ui.py`: chat rendering, typing indicator, send/copy/history interactions.
- `jarvis_ai/app_mixins/diagnostics_tools.py`: diagnostics UI and internal/external runtime checks.
- `jarvis_ai/app_mixins/settings_ui.py`: settings center, quick settings and embedded settings surfaces.
- `jarvis_ai/app_mixins/update_flow.py`: update/download/install orchestration.
- `jarvis_ai/app_mixins/voice_pipeline.py`: mic button, passive listening, STT fallback and wake-word handling.
- `jarvis_ai/app_mixins/scrolling.py`, `clipboard.py`: shared UI infrastructure.

## Release layout

- `build_release.ps1`: local release build.
- `publish_tools/`: GitHub release helpers and clean source bundle generation.
- `release/`: final deliverables only.

## Validation layout

- `scripts/unit_checks.py`: module-level sanity checks for wake-word, profiles and custom actions.
- `scripts/crash_test.py`: broader app regression/crash coverage.
- `scripts/release_smoke_check.py`: validates release metadata, assets and hashes after build.

## Direction

- keep moving `JarvisApp` behavior into `app_mixins/`
- keep app/service wiring explicit through `app_context.py` and `service_hub.py`
- keep state/config migration logic in `state.py`
- keep extension points file-based so this folder can live as a standalone repo
