from __future__ import annotations

from core.settings.startup_manager import StartupManager


def test_startup_command_includes_minimized_flag_by_default() -> None:
    command = StartupManager()._command()

    assert "--minimized" in command


def test_startup_command_can_skip_minimized_flag() -> None:
    command = StartupManager()._command(minimized=False)

    assert "--minimized" not in command
