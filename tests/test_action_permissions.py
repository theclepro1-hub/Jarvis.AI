import jarvis_ai.action_permissions as perms


class DummyConfig:
    def __init__(self, modes=None):
        self._modes = modes or {}

    def get_dangerous_action_modes(self):
        return self._modes


class DummyApp:
    def __init__(self, modes=None):
        self._cfg_obj = DummyConfig(modes)
        self.root = object()
        self.log_calls = []

    def _cfg(self):
        return self._cfg_obj

    def _record_human_log(self, *args, **kwargs):
        self.log_calls.append((args, kwargs))


def test_normalize_permission_modes_fills_defaults():
    normalized = perms.normalize_permission_modes({"power": "trust", "scripts": "invalid"})

    assert normalized["power"] == "trust"
    assert normalized["scripts"] == perms.DEFAULT_PERMISSION_MODES["scripts"]
    assert normalized["links"] == perms.DEFAULT_PERMISSION_MODES["links"]


def test_permission_category_for_action_covers_known_groups():
    assert perms.permission_category_for_action("shutdown") == "power"
    assert perms.permission_category_for_action("browser") == "links"
    assert perms.permission_category_for_action("steam") == "launch"
    assert perms.permission_category_for_action("unknown_action") is None


def test_permission_mode_for_action_uses_configured_modes():
    app = DummyApp({"links": "ask_once"})

    assert perms.permission_mode_for_action(app._cfg(), "browser") == "ask_once"
    assert perms.permission_mode_for_action(app._cfg(), "unknown_action") == "trust"


def test_ask_permission_reuses_ask_once_allowance(monkeypatch):
    calls = []
    app = DummyApp({"links": "ask_once"})

    def fake_askyesno(*_args, **_kwargs):
        calls.append(True)
        return True

    monkeypatch.setattr(perms.messagebox, "askyesno", fake_askyesno)

    assert perms.ask_permission(app, "browser", origin="command") is True
    assert perms.ask_permission(app, "browser", origin="command") is True
    assert len(calls) == 1


def test_ask_permission_logs_denial(monkeypatch):
    app = DummyApp({"power": "always"})
    monkeypatch.setattr(perms.messagebox, "askyesno", lambda *_args, **_kwargs: False)

    assert perms.ask_permission(app, "shutdown", origin="command") is False
    assert len(app.log_calls) == 1
