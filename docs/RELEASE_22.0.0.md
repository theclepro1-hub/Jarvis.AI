# JarvisAi Unity 22.0.0

`22.0.0` is the first full `JarvisAi Unity` release built from scratch in `C:\JarvisAi_Unity`.

## Highlights

- brand-new PySide6 + Qt Quick/QML desktop shell
- clean registration screen with Groq / Telegram helper links
- chat-first interface with quick actions and command palette
- compact settings with `Нубик` preserved only as a settings navigator
- rewritten local command router and batch command flow
- always-on local wake word runtime using `vosk`
- manual microphone capture with Groq Whisper STT after capture
- bundled `Golos Text` font for stable Cyrillic rendering
- rebuilt Windows icon and packaged portable + onefile executables

## Quality Gates

- UI clicks and scroll interactions verified through Qt UI tests
- `Ctrl+V` paste path verified in the composer
- Cyrillic text rendering rechecked through offscreen screenshots
- `pytest`, `ruff`, and `compileall` passed
- both portable and onefile EXE passed startup smoke runs
