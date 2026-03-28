#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_ai import runtime as runtime_mod
from jarvis_ai.brain_router import route_query
from jarvis_ai.commands import detect_wake_word, normalize_text
from jarvis_ai.custom_actions import load_custom_action_entries
from jarvis_ai.profile_tools import create_update_snapshot, list_update_snapshots
from jarvis_ai.runtime import _looks_like_runtime_root, runtime_root_path
from jarvis_ai.state import CONFIG_MGR, DEFAULT_CHAT_MODEL, DEFAULT_SYSTEM_PROMPT, _prompt_needs_repair
from jarvis_ai.storage import custom_actions_path
from jarvis_ai.voice_profiles import apply_device_listening_tuning, device_adaptation_tags, get_capture_timing, profile_values


def main() -> int:
    checks = []

    wake_detected, _ = detect_wake_word(normalize_text("джарвис открой стим"))
    checks.append(("wake word direct", wake_detected))

    typo_detected, _ = detect_wake_word(normalize_text("жарвис открой стим"))
    checks.append(("wake word typo", typo_detected))

    split_detected, _ = detect_wake_word(normalize_text("джа вис открой стим"))
    checks.append(("wake word split token", split_detected))

    tuned = apply_device_listening_tuning(profile_values("normal"), "Logitech PRO X Gaming Headset", passive_mode=True)
    checks.append(("passive tuning lowers threshold", int(tuned["energy_threshold"]) < int(profile_values("normal")["energy_threshold"])))
    checks.append(("passive tuning shortens phrase threshold", float(tuned["phrase_threshold"]) < float(profile_values("normal")["phrase_threshold"])))
    checks.append(("device adaptation tags", "гарнитура" in device_adaptation_tags("Logitech PRO X Gaming Headset", passive_mode=True, wake_word_boost=True)))

    timeout, phrase_limit = get_capture_timing("boost", manual_mode=True)
    checks.append(("manual timing available", timeout > 0 and phrase_limit > 0))
    checks.append(("router prefers memory over local", route_query("запомни что любимая платформа стим", CONFIG_MGR).get("route") == "memory"))
    CONFIG_MGR.set_scenarios(
        [
            {
                "name": "Ночной режим",
                "summary": "Тестовый сценарий",
                "trigger_phrases": ["ночной режим"],
                "enabled": True,
                "changes": {"focus_mode_enabled": True},
            }
        ]
    )
    checks.append(("router matches scenario", route_query("включи ночной режим", CONFIG_MGR).get("route") == "scenario"))
    CONFIG_MGR.set_scenarios([])
    checks.append(("default chat model", DEFAULT_CHAT_MODEL == "groq/compound-mini"))
    checks.append(("prompt repair flags mojibake", _prompt_needs_repair("РўС‹ РјРѕР·Рі РїРѕРјРѕС‰РЅРёРєР°")))
    checks.append(("prompt default is healthy", not _prompt_needs_repair(DEFAULT_SYSTEM_PROMPT)))

    snapshot_path = Path(create_update_snapshot("unit-test"))
    try:
        with zipfile.ZipFile(snapshot_path, "r") as archive:
            checks.append(("update snapshot includes metadata", "snapshot_meta.json" in archive.namelist()))
        checks.append(("update snapshot listed", str(snapshot_path) in list_update_snapshots(limit=5)))
    finally:
        snapshot_path.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        (root / "jarvis_ai").mkdir()
        (root / "jarvis_ai" / "branding.py").write_text("# marker\n", encoding="utf-8")
        (root / "publish_tools").mkdir()
        (root / "scripts").mkdir()
        (root / "updates.json").write_text("{}", encoding="utf-8")
        checks.append(("runtime root sentinel", _looks_like_runtime_root(str(root))))
        release_dir = root / "release"
        release_dir.mkdir()
        original_executable = runtime_mod.sys.executable
        original_frozen = getattr(runtime_mod.sys, "frozen", None)
        had_frozen = hasattr(runtime_mod.sys, "frozen")
        had_meipass = hasattr(runtime_mod.sys, "_MEIPASS")
        original_meipass = getattr(runtime_mod.sys, "_MEIPASS", None)
        try:
            runtime_mod.sys.executable = str(release_dir / "jarvis_ai_2.exe")
            runtime_mod.sys.frozen = True
            if had_meipass:
                delattr(runtime_mod.sys, "_MEIPASS")
            checks.append(("runtime root from release exe", runtime_root_path() == str(root)))
            checks.append(("runtime publish tools from release exe", runtime_root_path("publish_tools") == str(root / "publish_tools")))
        finally:
            runtime_mod.sys.executable = original_executable
            if had_frozen:
                runtime_mod.sys.frozen = original_frozen
            elif hasattr(runtime_mod.sys, "frozen"):
                delattr(runtime_mod.sys, "frozen")
            if had_meipass:
                runtime_mod.sys._MEIPASS = original_meipass

    manifest_path = Path(custom_actions_path())
    original = None
    if manifest_path.exists():
        original = manifest_path.read_text(encoding="utf-8")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"actions": [{"name": "Docs", "launch": "https://example.com", "aliases": ["доки"]}]}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        entries = load_custom_action_entries()
        checks.append(("custom action manifest load", bool(entries) and entries[0]["launch"].startswith("https://")))
    finally:
        if original is None:
            manifest_path.unlink(missing_ok=True)
        else:
            manifest_path.write_text(original, encoding="utf-8")

    failed = [name for name, ok in checks if not ok]
    print("JARVIS AI unit checks")
    print("=====================")
    for name, ok in checks:
        print(f"[{'OK' if ok else 'FAIL'}] {name}")
    if failed:
        print("")
        print("Failed checks:")
        for name in failed:
            print(f"- {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
