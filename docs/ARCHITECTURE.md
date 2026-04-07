# Architecture

## App shell

- PySide6 application
- Qt Quick / QML UI
- Python bridges expose state and actions to QML

## Layers

### UI

- visual shell
- screens
- reusable components

### Bridge

- app bridge
- chat bridge
- voice bridge
- settings bridge
- registration bridge

### Core

- state
- services
- routing
- actions
- voice
- ai
- settings
- registration
- updates

## Runtime rules

- one source of truth for settings
- no import-time singleton magic
- no monkey-patch composition
- local command routing before AI calls
- background AI requests never block UI rendering
- AI routing is mode-based for users (`Авто`, `Быстро`, `Качество`, `Локально`) and provider-based inside the backend
- cloud AI network calls use the configured proxy mode and keep local endpoints out of proxy paths
