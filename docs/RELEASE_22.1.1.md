# JarvisAi Unity 22.1.1

`22.1.1` is a small polish release for the Unity rebuild.

## What Changed Compared To 22.1.0

- Settings sections now start collapsed by default, so the Settings screen opens as a compact overview instead of several expanded panels.
- The default section state is handled in the shared `SettingsSection` component, while explicit Settings screen sections are also closed to keep first render consistent.

## Update Check

- This release is intended to verify the GitHub update checker path from `22.1.0` to `22.1.1`.
- Auto-update remains manual: JARVIS checks GitHub Releases, reports the newer version, and opens the release page on request.

## Quality Gates

- The version is bumped to `22.1.1` across packaging inputs.
- The change is intentionally narrow: no new runtime features, no new settings, and no silent installation behavior.
