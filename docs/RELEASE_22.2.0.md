# Release 22.2.0

## Main Changes

- Text chat now distinguishes ordinary conversation from local PC commands instead of defaulting to `Не понял`.
- Wake-word cleanup now strips common STT variants at the start of a phrase before routing.
- Telegram command handling follows the same command-vs-AI contract as the main chat.
- Post-wake command capture finishes faster after silence and keeps enough room for longer spoken commands.
- Voice and startup path got another optimization pass with lazy audio-device scanning and boot timing instrumentation.

## User-Facing Effects

- `привет`, `как дела`, `что умеешь` and similar text messages go to AI replies again.
- `Джарвис, как дела` can route to AI after wake instead of collapsing into `Не понял`.
- `гарви с ...`, `жарвис ...`, `джервис ...` and similar common prefix mistakes are cleaned when they appear at the start.
- Empty wake noise like just `джарвис` no longer turns into a Telegram AI reply.
- Multi-step spoken commands have a better chance of finishing before the capture window closes.

## Release Artifacts

- `JarvisAi_Unity_22.2.0_windows_installer.exe`
- `JarvisAi_Unity_22.2.0_windows_onefile.exe`
- `JarvisAi_Unity_22.2.0_windows_portable.zip`
