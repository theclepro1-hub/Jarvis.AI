Apps/Command Resolver pass

Scope:
- app discovery cleanup
- default music resolver
- curated quick actions
- structured local action summary

Implemented:
- Discovery now filters Steamworks redistributables, uninstall targets, redistributables, runtime/driver junk.
- Discovery deduplicates shortcut/direct candidates and prefers launcher manifests or direct app paths over Start Menu shortcuts.
- `открой музыку` resolves through `default_music_app` or the single custom music app when unambiguous.
- `открой яндекс музыку` resolves to Yandex Music instead of Windows Music.
- Quick actions are capped and curated; imported apps no longer flood the chat strip by default.
- Apps bridge uses scan/import summary instead of exposing a raw wall of candidates as the primary feedback.
- Local multi-command open chains collapse into one action summary when they are all simple launches.

Verification:
- `.venv\Scripts\python.exe -m pytest -q` -> `64 passed`
- `.venv\Scripts\python.exe -m ruff check core\actions core\routing ui\bridge tests\unit` -> clean
- `.venv\Scripts\python.exe -m compileall -q core\actions core\routing ui\bridge\apps_bridge.py ui\bridge\chat_bridge.py tests\unit\test_launcher_discovery.py tests\unit\test_action_registry.py tests\unit\test_command_router.py tests\unit\test_batch_router.py` -> clean

Still needs UI/design integration:
- Apps import screen should present the bridge summary compactly.
- Music conflicts need a small UI selector to call the default-music setter.
- Chat screen needs the design pass for ListView/max-width/autoscroll.
