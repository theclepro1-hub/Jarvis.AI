# JARVIS Unity Local QA Gate

This gate is local-only. Do not push to GitHub or publish a release until these checks pass and the user confirms the app manually.

## Commands

Run from `C:\JarvisAi_Unity`:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check app core tests tools ui
.venv\Scripts\python.exe -m compileall -q app core tests tools
powershell -ExecutionPolicy Bypass -File .\build\build_release.ps1
```

## Smoke

Portable smoke:

```powershell
$env:JARVIS_UNITY_DISABLE_STARTUP_REGISTRY='1'
$env:JARVIS_UNITY_DISABLE_WAKE='1'
.\dist\JarvisAi_Unity\JarvisAi_Unity.exe
```

If `dist` is locked by a running app, the release script may build into `dist_fresh_*`; smoke the fresh path reported by `BUILD_OK`.

## Manual Scenarios

1. Settings -> theme -> chat -> messages.
Fail if chat bubbles move outside the visible window, horizontal scrolling appears, messages stop auto-scrolling down, or navigation resets.

2. Voice -> microphone/output/TTS.
Fail if microphone list contains Stereo Mix, Line In, SPDIF, HDMI/NVIDIA output devices, driver endpoints, or duplicates. Fail if output list contains microphones. Fail if `Проверить голос` pretends to work when no actual TTS route exists.

3. Voice wake status.
Fail if wake shows a ready/active state before the model/stream/callback are ready. Fail if wake notes appear as normal chat bubbles.

4. Apps auto-import.
Fail if the UI shows a wall of duplicate candidates, `Steamworks Common Redistributables`, uninstall targets, or every Steam shortcut. Safe unique apps may be added quietly; conflicts must be summarized separately.

5. Music default resolver.
Fail if `открой музыку` opens Windows Music when Yandex Music or Spotify was selected as the default. Fail if `открой яндекс музыку` resolves to generic Windows Music.

6. Quick actions.
Fail if quick actions contain more than 7 visible actions or long imported junk names. Quick actions are curated, not a dump of all discovered apps.

7. Minimized/tray mode.
Fail if close-to-tray loses the app, autostart ignores minimized mode, or a second visible window opens on startup.

8. AI routing.
Fail if local commands call the LLM. Fail if a concrete AI profile silently falls back to `Auto` without telling the user. Fail if mocked 429/timeout does not fall back in `Auto`. If API keys are unavailable in the environment, mark live AI as not tested instead of faking it.

9. Microphone hardware smoke.
If safe, enumerate devices and open the selected/system microphone for one short read without saving audio. Fail if opening a valid selected/system microphone crashes the app path. If hardware access is unavailable, mark hardware as not tested and keep mocked classifier tests as the gate.
