from .runtime_activity import register_activity_runtime
from .runtime_activity_filters import apply_activity_history_filters
from .runtime_brain import register_brain_runtime
from .runtime_dry_run import apply_dry_run_runtime
from .runtime_inline_status import apply_inline_status_runtime
from .runtime_recovery import apply_recovery_runtime
from .runtime_shell import register_shell_runtime
from .runtime_system_ui import register_system_ui
from .runtime_voice import register_voice_runtime


def compose_jarvis_app(*, settings_mixin_cls, emoji_detector=None):
    def _decorate(app_cls):
        register_voice_runtime(app_cls)
        register_brain_runtime(app_cls, emoji_detector=emoji_detector)
        register_activity_runtime(app_cls)
        apply_activity_history_filters(app_cls)
        apply_inline_status_runtime(app_cls)
        apply_dry_run_runtime(app_cls)
        register_shell_runtime(app_cls)
        register_system_ui(app_cls, settings_mixin_cls)
        apply_recovery_runtime(app_cls)
        return app_cls

    return _decorate


__all__ = ["compose_jarvis_app"]
