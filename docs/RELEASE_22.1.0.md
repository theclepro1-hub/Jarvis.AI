# JarvisAi Unity 22.1.0

`22.1.0` is a backend hardening release for the Unity rebuild of JARVIS.
It keeps the Qt shell and focuses on honest Telegram, reminders, update status, local data control,
and clearer user-facing diagnostics.

## What Changed Compared To 22.0.0

- Telegram now exposes a real runtime status model: configured, connected, last command, last reply, last error, and last poll time.
- Telegram can send a test message to the configured Telegram ID without relying on the chat flow.
- Reminder delivery is kept honest: due reminders are sent to the UI and Telegram, not only confirmed in chat.
- Update checks now compare GitHub latest release metadata against the current version without auto-installing anything.
- The update checker keeps last version, release URL, assets, and last error available for UI bindings.
- Chat history can be cleared and history persistence can be turned off from settings.
- Local runtime data can be wiped from `%LOCALAPPDATA%\JarvisAi_Unity` with a two-step confirmation.
- Apps can be rescanned with a quiet added/already/skipped/conflict summary.
- Quick commands can be pinned from the apps catalog and appear first in chat.
- Voice diagnostics now has one practical check: JARVIS shows what it heard, what it cleaned, and what it would do.
- Settings are reordered so connections and Telegram status come before theme and cosmetic controls.
- Background polling and update checks stay off the UI thread.

## Backend Notes

- User data stays under `%LOCALAPPDATA%\JarvisAi_Unity`.
- Telegram and reminder state are stored in the runtime data directory.
- Auto-update remains manual download plus install; JARVIS only checks and reports, then opens the GitHub release on request.

## Quality Gates

- Telegram polling errors are reported honestly.
- Update checks fail honestly on network or GitHub errors.
- Reminder delivery is covered by unit tests for UI and Telegram fan-out.
- The version is bumped to `22.1.0` across packaging inputs.
