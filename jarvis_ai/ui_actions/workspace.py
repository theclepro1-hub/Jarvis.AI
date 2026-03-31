from typing import List, Optional, Tuple


def _switch_to_chat(app) -> None:
    app.close_full_settings_view()
    app._set_workspace_section("chat")


def _open_section(app, section_key: str, settings_tab: str) -> None:
    app._set_workspace_section(section_key)
    app.open_full_settings_view(settings_tab)


def build_workspace_section_actions(app) -> List[dict]:
    return [
        {
            "key": "chat",
            "label": "Чат",
            "compact": "Чат",
            "command": lambda: _switch_to_chat(app),
        },
        {
            "key": "voice",
            "label": "Голос",
            "compact": "Голос",
            "command": lambda: _open_section(app, "voice", "voice"),
        },
        {
            "key": "main",
            "label": "Настройки",
            "compact": "Настр.",
            "command": lambda: _open_section(app, "main", "main"),
        },
        {
            "key": "diagnostics",
            "label": "Диагностика",
            "compact": "Диагн.",
            "command": lambda: _open_section(app, "diagnostics", "diagnostics"),
        },
        {
            "key": "system",
            "label": "Система",
            "compact": "Система",
            "command": lambda: _open_section(app, "system", "system"),
        },
    ]


def build_workspace_menu_actions(app) -> List[Optional[Tuple[str, object]]]:
    section_items = [(item["label"], item["command"]) for item in build_workspace_section_actions(app)]
    return section_items + [
        None,
        ("Журнал", app.show_history),
        ("Отменить", app.undo_last_action),
        ("Поиск команд", app.open_command_palette),
    ]
