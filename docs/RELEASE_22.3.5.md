# JARVIS Unity 22.3.5

22.3.5 is a cleanup and release-quality pass on top of 22.3.0/22.3.0-era fixes.

## What changed

- Installer uninstall now removes the application directory so a reinstall does not stop on an "existing folder" prompt.
- Release gate keeps the updater contract honest and continues to require the installer asset for apply flow.
- Runtime identity stays aligned across bootstrap, installer metadata, and Windows taskbar/AppUserModelID setup.
- Release checks cover the release document, build script, installer metadata, and update service contract.

## Notes

- This release does not add new user-facing features.
- The focus is installation hygiene, update flow correctness, and release metadata consistency.
