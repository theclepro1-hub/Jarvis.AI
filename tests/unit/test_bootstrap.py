from __future__ import annotations

import app.bootstrap as bootstrap_module


class _FakeQApplication:
    def __init__(self, argv) -> None:  # noqa: ANN001
        self.argv = list(argv)
        self.quit_on_last_window_closed = None
        self.exec_calls = 0
        self.window_icons: list[object] = []

    def setQuitOnLastWindowClosed(self, value: bool) -> None:
        self.quit_on_last_window_closed = value

    def setWindowIcon(self, icon) -> None:  # noqa: ANN001
        self.window_icons.append(icon)

    def exec(self) -> int:
        self.exec_calls += 1
        return 137


class _FakeSingleInstance:
    def __init__(self, ensure_primary: bool) -> None:
        self.ensure_primary = ensure_primary
        self.ensure_calls = 0
        self.show_handlers: list[object] = []
        self.stop_calls = 0

    def ensure_primary_instance(self) -> bool:
        self.ensure_calls += 1
        return self.ensure_primary

    def attach_show_handler(self, handler) -> None:  # noqa: ANN001
        self.show_handlers.append(handler)

    def stop(self) -> None:
        self.stop_calls += 1


class _FakeRuntime:
    def __init__(self, qapp, *, start_minimized: bool = False, single_instance=None) -> None:
        self.qapp = qapp
        self.start_minimized = start_minimized
        self.single_instance = single_instance
        self.start_calls = 0

    def start(self) -> None:
        self.start_calls += 1


def _install_bootstrap_fakes(monkeypatch, *, ensure_primary: bool):
    captured_qapp = {"app": None}
    single_instance = _FakeSingleInstance(ensure_primary=ensure_primary)

    def fake_qapplication(argv):
        captured_qapp["app"] = _FakeQApplication(argv)
        return captured_qapp["app"]

    monkeypatch.setattr(bootstrap_module, "QApplication", fake_qapplication)
    # Avoid constructing a real Qt icon in tests; this can crash in headless CI.
    monkeypatch.setattr(bootstrap_module, "QIcon", lambda path: path)
    monkeypatch.setattr(
        "core.services.single_instance.SingleInstanceService",
        lambda *args, **kwargs: single_instance,
    )
    monkeypatch.setattr("app.app.JarvisUnityApplication", _FakeRuntime)
    monkeypatch.setattr(bootstrap_module.sys, "argv", ["jarvis.exe", "--tray"])

    settings_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        bootstrap_module.QGuiApplication,
        "setOrganizationName",
        lambda value: settings_calls.append(("organization", value)),
    )
    monkeypatch.setattr(
        bootstrap_module.QGuiApplication,
        "setOrganizationDomain",
        lambda value: settings_calls.append(("domain", value)),
    )
    monkeypatch.setattr(
        bootstrap_module.QGuiApplication,
        "setApplicationName",
        lambda value: settings_calls.append(("name", value)),
    )
    monkeypatch.setattr(
        bootstrap_module.QGuiApplication,
        "setApplicationDisplayName",
        lambda value: settings_calls.append(("display_name", value)),
    )
    monkeypatch.setattr(
        bootstrap_module.QGuiApplication,
        "setApplicationVersion",
        lambda value: settings_calls.append(("version", value)),
    )
    monkeypatch.setattr(bootstrap_module.QQuickStyle, "setStyle", lambda _value: None)
    return captured_qapp, single_instance, settings_calls


def test_bootstrap_runs_primary_instance_path(monkeypatch) -> None:
    captured_qapp, single_instance, settings_calls = _install_bootstrap_fakes(monkeypatch, ensure_primary=True)

    result = bootstrap_module.bootstrap()
    qapp = captured_qapp["app"]

    assert result == 137
    assert qapp is not None
    assert qapp.exec_calls == 1
    assert qapp.quit_on_last_window_closed is True
    assert single_instance.ensure_calls == 1
    assert single_instance.stop_calls == 0
    assert settings_calls == [
        ("organization", "theclepro1"),
        ("domain", "jarvisai.unity"),
        ("name", "JARVIS Unity"),
        ("display_name", "JARVIS Unity"),
        ("version", bootstrap_module.WINDOWS_APP_VERSION),
    ]


def test_bootstrap_returns_zero_for_secondary_instance(monkeypatch) -> None:
    captured_qapp, single_instance, settings_calls = _install_bootstrap_fakes(monkeypatch, ensure_primary=False)

    result = bootstrap_module.bootstrap()
    qapp = captured_qapp["app"]

    assert result == 0
    assert qapp is not None
    assert qapp.exec_calls == 0
    assert qapp.quit_on_last_window_closed is True
    assert single_instance.ensure_calls == 1
    assert single_instance.stop_calls == 0
    assert settings_calls == [
        ("organization", "theclepro1"),
        ("domain", "jarvisai.unity"),
        ("name", "JARVIS Unity"),
        ("display_name", "JARVIS Unity"),
        ("version", bootstrap_module.WINDOWS_APP_VERSION),
    ]
