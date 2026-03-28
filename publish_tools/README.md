# Publish Tools 2.0

This folder contains the standalone release helpers for `JARVIS AI 2.0`.

## Files

- `..\\ONE_CLICK_PUBLISH.bat` - recommended root-level button for a full GitHub release
- `..\\build_release.bat` - recommended root-level button for local `.exe` and installer
- `Build-And-Prepare.bat` - build release and prepare the GitHub source bundle
- `Publish-One-Click.bat` - full one-click publish into GitHub
- `Commit-And-Push.bat` - commit and push source changes
- `Commit-And-Release.bat` - commit, push, create tag, and push tag
- `prepare_github_bundle.ps1` - generate a clean upload folder
- `commit_and_push.ps1` - reusable Git helper with isolated repo init and clearer git error output

## Output

Local build artifacts are generated here:

- `..\\release\\jarvis_ai_2.exe`
- `..\\release\\JarvisAI2_Setup.exe`

Prepared source bundle is generated here:

- `publish_tools\\github_bundle\\JARVIS_AI_2_v<version>`

One-click publish uses this clean bundle as git source, so it does not depend on the current dirty workspace state.
Legacy bundle folders are removed automatically before a new bundle is created.
