from jarvis_ai.controllers import ActionExecutor


class DummyApp:
    root = object()


def test_action_executor_dispatch_runs_handler_when_allowed(monkeypatch):
    executor = ActionExecutor(DummyApp())
    calls = []

    monkeypatch.setattr("jarvis_ai.controllers.ask_permission", lambda *_args, **_kwargs: True)

    result = executor.dispatch(
        "browser",
        "openai.com",
        origin="command",
        handler=lambda action, arg: calls.append((action, arg)) or "ok",
    )

    assert result == "ok"
    assert calls == [("browser", "openai.com")]


def test_action_executor_dispatch_stops_on_permission_denial(monkeypatch):
    executor = ActionExecutor(DummyApp())
    calls = []

    monkeypatch.setattr("jarvis_ai.controllers.ask_permission", lambda *_args, **_kwargs: False)

    result = executor.dispatch(
        "shutdown",
        None,
        origin="command",
        handler=lambda action, arg: calls.append((action, arg)) or "should-not-run",
    )

    assert result is None
    assert calls == []
