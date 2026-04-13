# JARVIS Unity 20.5.5

20.5.5 is a cleanup release that keeps the update flow intact while removing version-specific identity leftovers.

## What Changed

- Product version was moved to `20.5.5`.
- Internal updater version stays monotonic at `22.5.5`, so existing `22.5.1` installs can still see this release as newer.
- Installer and single-instance identity now use versionless names, so new builds do not carry stale `22.x` mutex/server identifiers.
- Update UX remains compatible: the updater still uses the same current-version source and release metadata flow.
- Version handling now has a real `display_version` / `update_version` bridge in code.

## Verification

- `python -m pytest -q tests/integration/test_release_hygiene.py tests/unit/test_update_service.py tests/unit/test_app_bridge.py` → expected release/version/identity coverage
