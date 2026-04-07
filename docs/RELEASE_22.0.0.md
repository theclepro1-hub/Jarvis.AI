# JarvisAi Unity 22.0.0

`22.0.0` is the first full `JarvisAi Unity` release built from scratch in `C:\JarvisAi_Unity`.

## Highlights

- brand-new PySide6 + Qt Quick/QML desktop shell
- clean registration screen with Groq / Telegram helper links
- chat-first interface with quick actions and command palette
- compact settings with `Нубик` preserved only as a contextual guide
- rewritten offline-first command router and batch command flow
- explicit AI profiles: Auto, fast Groq, quality Gemini, fast Cerebras, OpenRouter reserve, local
- always-on local wake word runtime using `vosk`
- manual microphone capture with STT routing by voice mode
- bundled `Golos Text` font for stable Cyrillic rendering
- rebuilt Windows icon and packaged installer, portable, and onefile executables

## Quality Gates

- UI clicks and scroll interactions verified through Qt UI tests
- `Ctrl+V` paste path verified in the composer
- Cyrillic text rendering rechecked through offscreen screenshots
- `pytest`, `ruff`, and `compileall` passed
- portable, onefile, and installer assets are produced by the release script
