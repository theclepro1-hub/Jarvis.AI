# JARVIS AI 2.0

Standalone branch of the assistant, isolated from the original app.

## Current release

- Product: `JARVIS AI 2.0`
- Version: `16.0.0`
- Default GitHub repo slug: `theclepro1-hub/Jarvis.AI`
- User data namespace: `JarvisAI2`

## What is already split

- `jarvis_ai/branding.py` - product name, version, release filenames, app ids
- `jarvis_ai/theme.py` - palette management and theme color remapping
- `jarvis_ai/app_context.py` - explicit runtime context for config, prompts and database wiring
- `jarvis_ai/runtime.py` - resource paths, runtime root, geometry parsing, Windows app id
- `jarvis_ai/audio_devices.py` - isolated audio device discovery, cleanup, scoring and auto-pick logic
- `jarvis_ai/release_meta.py` - default GitHub release endpoints
- `jarvis_ai/storage.py` - isolated config, db, prompts, logs, update-state paths
- `jarvis_ai/commands.py` - wake-word logic, command parsing, dynamic app aliases, text normalization
- `jarvis_ai/custom_actions.py` - manifest-based custom actions for repo-independent extensions
- `jarvis_ai/service_hub.py` - explicit service wiring for Groq, reminders, Telegram and diagnostics
- `jarvis_ai/settings_forms.py` - reusable settings fields, sliders and toggle rows for the polished settings UI
- `jarvis_ai/voice_profiles.py` - hearing profiles and wake-word device tuning
- `jarvis_ai/update_helpers.py` - version comparison, release asset picking, trusted URL helpers, release note formatting
- `jarvis_ai/setup_wizard.py` - first-run and activation wizard UI
- `jarvis_ai/effects.py` - animated noob/DVD background effect
- `jarvis_ai/app_mixins/scrolling.py` - shared mousewheel routing, nested scroll fallback, combobox wheel guard
- `jarvis_ai/app_mixins/clipboard.py` - clipboard paste helpers, entry/text bindings, context menu handling
- `jarvis_ai/app_mixins/settings_ui.py` - full settings center, quick settings and embedded settings page
- `jarvis_ai/app_mixins/chat_ui.py` - chat/history/rendering flow
- `jarvis_ai/app_mixins/diagnostics_tools.py` - diagnostics tab and runtime checks
- `jarvis_ai/app_mixins/voice_pipeline.py` - manual mic, passive listening and STT flow
- `jarvis_ai/app_mixins/update_flow.py` - app-level update download/install/check flow, isolated from the main UI file
- `jarvis_ai/state.py`, `jarvis_ai/telegram_bot.py`, `jarvis_ai/reminders.py`, `jarvis_ai/diagnostics.py` - extracted services and state layer

## Standalone workspace rules

- everything needed for source, build, GitHub publish and release notes is inside this folder
- final artifacts live in `release/`
- temporary build folders are cleaned automatically after a successful release build
- progress tracker for this branch lives in `TASKS.md`
- project map and module responsibilities live in `ARCHITECTURE.md`
- `TASKS.md` tracks the current release readiness and last full verification pass

## Release workflow

- Local build: `build_release.bat`
- Full GitHub publish: `ONE_CLICK_PUBLISH.bat`
- Release helpers: `publish_tools/`
- Release build runs `py_compile`, `scripts/unit_checks.py`, `scripts/crash_test.py` and `scripts/release_smoke_check.py`

Artifacts are produced in:

- `release/jarvis_ai_2.exe`
- `release/JarvisAI2_Setup.exe`

## Runtime extras

- Safe mode: `python jarvis.py --safe-mode`
- Custom action manifest: open it from `Настройки -> Приложения -> Открыть custom_actions.json`
- Wake-word sensitivity can be boosted from `Настройки -> Основные`
- Default home screen now opens as a cleaner desktop-like shell with sidebar navigation, central workspace, helper noob rail and command palette
- Settings, diagnostics and publish panels now use wrap-aware cards and action grids so narrow windows stay readable
- Readiness master, release lock, backup/restore and diagnostics export are available directly from the main workspace

## Independence from the original app

- Separate app name, version, installer, and executable
- Separate Windows AppUserModelID
- Separate user config/data/log directories via `JarvisAI2`
- Separate release scripts, changelog, updates manifest, workflow, and publish helpers
- Can be kept as the only remaining project folder without depending on files outside `jarvisAI 2.0`
