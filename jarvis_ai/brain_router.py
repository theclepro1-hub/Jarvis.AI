from typing import Any, Dict

from .commands import CommandParser, normalize_text
from .scenario_engine import find_matching_scenario
from .smart_memory import parse_memory_command


def build_action_explanation(route: Dict[str, Any]) -> str:
    route_type = str(route.get("route", "") or "").strip().lower()
    if route_type == "local":
        action = str(route.get("action", "") or "").strip()
        arg = route.get("arg")
        pretty = {
            "youtube": "открыть YouTube",
            "steam": "открыть Steam",
            "discord": "открыть Discord",
            "browser": "открыть браузер",
            "settings": "открыть настройки",
            "search": f"найти: {arg}",
            "time": "показать время",
            "date": "показать дату",
            "weather": "открыть погоду",
            "close_app": f"закрыть приложение: {arg}",
            "open_dynamic_app": f"открыть приложение: {arg}",
        }.get(action, action or "выполнить локальную команду")
        return f"Я понял: {pretty}."
    if route_type == "memory":
        intent = str(route.get("intent", "") or "").strip().lower()
        if intent == "remember":
            return "Я понял: сохранить это в памяти."
        if intent == "forget":
            return "Я понял: удалить это из памяти."
        return "Я понял: показать, что JARVIS помнит."
    if route_type == "scenario":
        scenario = route.get("scenario") or {}
        return f"Я понял: включить сценарий «{scenario.get('name', 'без названия')}»."
    if route_type == "ai":
        return "Я понял: нужен смысловой разбор через ИИ."
    return ""


def route_query(text: str, config_mgr) -> Dict[str, Any]:
    norm = normalize_text(text)
    if not norm:
        return {"route": "empty"}

    memory_route = parse_memory_command(norm)
    if memory_route:
        memory_route["route"] = "memory"
        memory_route["reason"] = "memory_command"
        return memory_route

    scenario = find_matching_scenario(getattr(config_mgr, "get_scenarios", lambda: [])(), norm)
    if scenario:
        return {
            "route": "scenario",
            "scenario": scenario,
            "reason": "scenario_match",
        }

    if getattr(config_mgr, "get_hybrid_brain_enabled", lambda: True)():
        action, arg = CommandParser.classify_local(norm)
        if action:
            return {
                "route": "local",
                "action": action,
                "arg": arg,
                "reason": "local_command",
            }

    return {
        "route": "ai",
        "reason": "ai_fallback",
    }


__all__ = ["build_action_explanation", "route_query"]
