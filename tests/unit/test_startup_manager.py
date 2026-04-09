from __future__ import annotations

from core.settings.startup_manager import StartupManager


def test_startup_command_is_visible_by_default() -> None:
    command = StartupManager()._command()

    assert "--minimized" not in command


def test_startup_command_can_skip_minimized_flag() -> None:
    command = StartupManager()._command(minimized=False)

    assert "--minimized" not in command
