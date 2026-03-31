from concurrent.futures import TimeoutError as FutureTimeoutError
from tkinter import messagebox

from .brain_router import build_action_explanation, route_query
from .commands import SIMPLE_BATCH_ACTIONS, SPLIT_PATTERN, normalize_text
from .scenario_engine import apply_scenario_changes, find_auto_scenarios, normalize_scenarios, scenario_digest
from .smart_memory import (
    find_memory_items,
    format_memory_summary,
    memory_digest,
    normalize_memory_items,
    remove_memory_item,
    touch_memory_item,
    upsert_memory_item,
)
from .state import CONFIG_MGR, db


def _announce_route_explanation(self, route, reply_callback=None):
    if not self._cfg().get_explain_actions_enabled():
        return
    text = str(build_action_explanation(route) or "").strip()
    if not text:
        return
    var = getattr(self, "action_explainer_var", None)
    if var is not None:
        try:
            var.set(text)
        except Exception:
            pass
    try:
        self.root.after(0, self._apply_voice_insight_widgets)
    except Exception:
        pass
    try:
        self.set_status_temp(text, "ok", duration_ms=2800)
    except Exception:
        pass
    if getattr(self, "_route_explainer_after_id", None) is not None:
        try:
            self.root.after_cancel(self._route_explainer_after_id)
        except Exception:
            pass
        self._route_explainer_after_id = None

    def _clear():
        self._route_explainer_after_id = None
        current = getattr(self, "action_explainer_var", None)
        if current is not None:
            try:
                if str(current.get() or "").strip() == text:
                    current.set("JARVIS коротко покажет, что понял, перед сложным действием.")
            except Exception:
                pass

    try:
        self._route_explainer_after_id = self.root.after(6200, _clear)
    except Exception:
        pass


def _get_memory_items(self):
    raw_items = list(self._cfg().get_user_memory_items() or [])
    normalized = normalize_memory_items(raw_items)
    if normalized != raw_items:
        self._cfg().set_user_memory_items(normalized)
    return normalized


def _set_memory_items(self, items):
    normalized = normalize_memory_items(items or [])
    self._cfg().set_user_memory_items(normalized)
    if hasattr(self, "_refresh_memory_widgets"):
        try:
            self._refresh_memory_widgets()
        except Exception:
            pass
    return normalized


def _get_scenario_items(self):
    raw_items = list(self._cfg().get_scenarios() or [])
    normalized = normalize_scenarios(raw_items)
    if normalized != raw_items:
        self._cfg().set_scenarios(normalized)
    return normalized


def _set_scenario_items(self, items):
    normalized = normalize_scenarios(items or [])
    self._cfg().set_scenarios(normalized)
    if hasattr(self, "_refresh_scenario_widgets"):
        try:
            self._refresh_scenario_widgets()
        except Exception:
            pass
    return normalized


def _handle_memory_route(self, route, raw_text: str = "") -> str:
    items = self._get_memory_items()
    intent = str(route.get("intent", "") or "").strip().lower()
    if intent == "remember":
        write_mode = str(self._cfg().get_memory_write_mode() or "always").strip().lower()
        scope = str(route.get("scope") or "").strip().lower()
        combined_text = normalize_text(" ".join([str(route.get("title") or ""), str(route.get("value") or raw_text)]))
        memory_avoid_patterns = [normalize_text(item) for item in (self._cfg().get_memory_avoid_patterns() or []) if str(item or "").strip()]
        if combined_text and any(pattern and pattern in combined_text for pattern in memory_avoid_patterns):
            return "Пропустил запись: пользователь запретил запоминать такие формулировки."
        payload = {
            "title": route.get("title") or raw_text[:80],
            "value": route.get("value") or raw_text,
            "scope": scope or ("temporary" if write_mode == "temporary_first" else "personal"),
            "kind": route.get("kind") or "fact",
            "tags": route.get("tags") or [],
            "pinned": scope == "pinned",
            "why": route.get("why") or "Пользователь явно попросил сохранить это в память.",
            "source": route.get("source") or "chat",
        }
        if write_mode == "ask":
            title = str(payload.get("title") or "new item").strip()
            detail = str(payload.get("value") or "").strip()
            preview = detail[:180] + ("..." if len(detail) > 180 else "")
            allowed = messagebox.askyesno(
                "Память JARVIS",
                f"Сохранить в память: {title}?\n\n{preview}",
                parent=getattr(self, "root", None),
            )
            if not allowed:
                return "Сохранение памяти отменено."
        updated = upsert_memory_item(items, payload)
        self._set_memory_items(updated)
        if payload.get("scope") == "temporary":
            return "Сохранил во временную память."
        return "Сохранил в память."
    if intent == "forget":
        query = str(route.get("query", "") or "").strip()
        matches = find_memory_items(items, query)
        if not matches:
            return "Подходящая запись памяти не найдена."
        updated = items
        for item in matches[:1]:
            updated = remove_memory_item(updated, item.get("id"))
        self._set_memory_items(updated)
        return f"Удалил из памяти: {matches[0].get('title') or query}."
    query = str(route.get("query", "") or "").strip()
    matches = find_memory_items(items, query) if query else items
    refreshed = list(items)
    for item in matches[:4]:
        refreshed = upsert_memory_item(refreshed, touch_memory_item(item))
    self._set_memory_items(refreshed)
    return format_memory_summary(matches if query else refreshed, query="")


def _handle_scenario_route(self, route) -> str:
    scenario = route.get("scenario") or {}
    if not scenario:
        return "Сценарий не найден."
    message = apply_scenario_changes(self, scenario)
    try:
        self.refresh_workspace_layout_mode()
    except Exception:
        pass
    try:
        self._update_guide_context("release")
    except Exception:
        pass
    return message


def _auto_apply_matching_scenarios(self):
    items = self._get_scenario_items()
    matches = find_auto_scenarios(self, items)
    if not matches:
        self._last_auto_scenario_id = ""
        return
    target = matches[0]
    target_id = str(target.get("id", "") or "").strip()
    current_name = str(self._cfg().get_current_scenario() or "").strip()
    if target_id and getattr(self, "_last_auto_scenario_id", "") == target_id and current_name == str(target.get("name", "") or "").strip():
        return
    result = self._handle_scenario_route({"scenario": target})
    self._last_auto_scenario_id = target_id
    try:
        self.set_status_temp(f"Авто-сценарий: {target.get('name')}", "ok", duration_ms=2400)
    except Exception:
        pass
    try:
        self.add_msg(result, "bot")
    except Exception:
        pass


def _compose_ai_query(self, cmd: str) -> str:
    chunks = []
    memory_text = memory_digest(self._get_memory_items(), limit=6)
    if memory_text:
        chunks.append("Память пользователя:\n" + memory_text)
    active_scenario = str(self._cfg().get_current_scenario() or "").strip()
    if active_scenario:
        chunks.append(f"Активный сценарий: {active_scenario}")
    scenario_text = scenario_digest(self._get_scenario_items(), limit=4)
    if scenario_text:
        chunks.append("Сценарии:\n" + scenario_text)
    chunks.append(
        "Правило маршрутизации: если запрос можно понять как локальную команду Windows, ответи JSON-командой. "
        "Если это обычный разговор или нужна логика/объяснение, ответи JSON-чатом."
    )
    chunks.append("Запрос пользователя:\n" + str(cmd or "").strip())
    return "\n\n".join(chunk for chunk in chunks if str(chunk or "").strip())


def make_process_query(emoji_detector):
    def _patched_process_query(self, query: str, reply_callback=None) -> None:
        raw_query = str(query or "").strip()
        if self._startup_gate_setup and not bool(str(CONFIG_MGR.get_api_key() or "").strip()):
            msg = "Сначала завершите активацию в разделе «Основное»."
            if reply_callback:
                reply_callback(msg)
            else:
                self.root.after(0, lambda: self.add_msg(msg, "bot"))
                self.root.after(0, lambda: self.open_full_settings_view("main"))
            return

        if emoji_detector and emoji_detector(raw_query):
            if reply_callback:
                reply_callback(raw_query)
            else:
                self.root.after(0, lambda t=raw_query: self.add_msg(t, "bot"))
            self.set_status("Готов", "ok")
            return

        text = normalize_text(raw_query)
        if not text:
            return

        with self._process_state_lock:
            if self.processing_command:
                busy_msg = "Уже обрабатываю предыдущую команду. Повторите через секунду."
                if reply_callback:
                    reply_callback(busy_msg)
                else:
                    self.root.after(0, lambda: self.add_msg(busy_msg, "bot"))
                return
            self.processing_command = True

        self.set_status("Обрабатываю...", "busy")
        try:
            parts = [p.strip() for p in SPLIT_PATTERN.split(text) if p.strip()] or [text]
            routed = [(cmd, route_query(cmd, CONFIG_MGR)) for cmd in parts]

            if len(parts) > 3 and all(route.get("route") == "local" and route.get("action") in SIMPLE_BATCH_ACTIONS for _, route in routed):
                futures = [
                    self.executor.submit(self.execute_action, route.get("action"), route.get("arg"), cmd, False, None)
                    for cmd, route in routed
                ]
                results = []
                for fut in futures:
                    try:
                        res = fut.result(timeout=7)
                        if res:
                            results.append(res)
                            self.last_ai_reply = res
                    except FutureTimeoutError:
                        pass
                    except Exception as exc:
                        self.report_error("Ошибка пакетной команды", exc, speak=True)
                msg = self._summarize_multi_action_reply(results)
                if reply_callback:
                    reply_callback(msg)
                else:
                    self.speak_msg(msg)
                self.set_status("Готов", "ok")
                return

            local_only_multi = len(routed) > 1 and all(str(route.get("route", "") or "").strip().lower() == "local" for _, route in routed)
            local_only_results = []
            for cmd, route in routed:
                route_name = str(route.get("route", "") or "").strip().lower()
                if not local_only_multi:
                    self._announce_route_explanation(route, reply_callback=reply_callback)
                if route_name == "local":
                    res = self.execute_action(
                        route.get("action"),
                        route.get("arg"),
                        cmd,
                        speak=not local_only_multi,
                        reply_callback=None if local_only_multi else reply_callback,
                    )
                    if res:
                        local_only_results.append(res)
                        self.last_ai_reply = res
                        db.save_command(cmd, res)
                    continue

                if route_name == "memory":
                    res = self._handle_memory_route(route, raw_text=cmd)
                    self.last_ai_reply = res
                    db.save_command(cmd, res)
                    if reply_callback:
                        reply_callback(res)
                    else:
                        self.speak_msg(res)
                    continue

                if route_name == "scenario":
                    res = self._handle_scenario_route(route)
                    self.last_ai_reply = res
                    db.save_command(cmd, res)
                    if reply_callback:
                        reply_callback(res)
                    else:
                        self.speak_msg(res)
                    continue

                self.ai_handler(self._compose_ai_query(cmd), reply_callback=reply_callback)

            if local_only_multi:
                msg = self._summarize_multi_action_reply(local_only_results)
                if reply_callback:
                    reply_callback(msg)
                else:
                    self.speak_msg(msg)
            self.set_status("Готов", "ok")
        finally:
            with self._process_state_lock:
                self.processing_command = False

    return _patched_process_query


def register_brain_runtime(app_cls, emoji_detector=None):
    app_cls._announce_route_explanation = _announce_route_explanation
    app_cls._get_memory_items = _get_memory_items
    app_cls._set_memory_items = _set_memory_items
    app_cls._get_scenario_items = _get_scenario_items
    app_cls._set_scenario_items = _set_scenario_items
    app_cls._handle_memory_route = _handle_memory_route
    app_cls._handle_scenario_route = _handle_scenario_route
    app_cls._auto_apply_matching_scenarios = _auto_apply_matching_scenarios
    app_cls._compose_ai_query = _compose_ai_query
    app_cls.process_query = make_process_query(emoji_detector)


__all__ = ["register_brain_runtime"]
