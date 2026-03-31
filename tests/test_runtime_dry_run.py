import jarvis_ai.runtime_dry_run as dry_run


class _Cfg:
    def get_dangerous_action_modes(self):
        return {
            "power": "always",
            "input": "ask_once",
            "links": "ask_once",
            "launch": "ask_once",
            "scripts": "always",
        }


class _App:
    def _cfg(self):
        return _Cfg()


def test_shutdown_preview_mentions_windows_shutdown():
    preview = dry_run.build_action_dry_run_lines(
        _App(),
        action="shutdown",
        category="power",
        origin="unit-test",
    )
    joined = "\n".join(preview).lower()
    assert "предвар" in joined
    assert "windows" in joined
    assert "подтверждение" in joined


def test_dynamic_action_preview_renders_target(monkeypatch):
    monkeypatch.setattr(
        dry_run,
        "get_dynamic_entry_by_key",
        lambda key: {
            "name": "GitHub Jarvis",
            "launch": "https://github.com/theclepro1-hub/JarvisAI-2.0",
            "source": "manifest",
            "close_exes": [],
        },
    )
    monkeypatch.setattr(dry_run, "find_dynamic_entry", lambda query: None)
    preview = dry_run.build_action_dry_run_lines(
        _App(),
        action="open_dynamic_app",
        arg="jarvis_github",
        category="launch",
        origin="unit-test",
    )
    joined = "\n".join(preview).lower()
    assert "github jarvis" in joined
    assert "https://github.com/theclepro1-hub/jarvisai-2.0" in joined
    assert "сайт" in joined or "браузер" in joined
