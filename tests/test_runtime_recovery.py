from jarvis_ai.branding import APP_VERSION
from jarvis_ai.runtime_recovery import (
    clear_recovery_session_state,
    load_recovery_session_state,
    session_recovery_path,
    write_recovery_session_state,
)


def test_recovery_state_roundtrip(tmp_path):
    target = session_recovery_path(str(tmp_path))
    payload = {
        "status": "running",
        "version": APP_VERSION,
        "started_at": "2026-03-29 10:00:00",
        "last_query": "открой стим",
        "last_error": "resize loop",
    }
    write_recovery_session_state(payload, target)
    loaded = load_recovery_session_state(target)
    assert loaded == payload


def test_recovery_state_clear(tmp_path):
    target = session_recovery_path(str(tmp_path))
    write_recovery_session_state({"status": "running"}, target)
    clear_recovery_session_state(target)
    assert load_recovery_session_state(target) is None
