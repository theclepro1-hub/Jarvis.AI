#!/usr/bin/env python3
"""
Sync release notes from CHANGELOG.md into updates.json and release notes file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


DEFAULT_NOTE = "Техническое обслуживание и улучшение стабильности."


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def find_changelog_section(changelog: str, version: str) -> str:
    if not changelog.strip():
        return ""
    lines = changelog.splitlines()
    start = -1
    pattern = re.compile(
        rf"^\s*##\s*\[?v?{re.escape(version)}\]?(?:\s*-\s*.+)?\s*$",
        re.IGNORECASE,
    )
    for idx, line in enumerate(lines):
        if pattern.match(line.strip()):
            start = idx + 1
            break
    if start < 0:
        return ""

    end = len(lines)
    for idx in range(start, len(lines)):
        if re.match(r"^\s*##\s+", lines[idx]):
            end = idx
            break
    return "\n".join(lines[start:end]).strip()


def normalize_line(line: str) -> str:
    text = line.strip()
    text = re.sub(r"^[\-*\u2022]+\s*", "", text)
    text = re.sub(r"`+", "", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    return text.strip()


def build_notes_summary(section: str, limit: int = 4) -> str:
    if not section.strip():
        return DEFAULT_NOTE

    candidates: list[str] = []
    for raw in section.splitlines():
        line = raw.strip()
        if not line or line.startswith("###"):
            continue
        if re.match(r"^[\-*\u2022]\s+", line):
            text = normalize_line(line)
            if text:
                candidates.append(text)
        elif not candidates:
            text = normalize_line(line)
            if text:
                candidates.append(text)

    if not candidates:
        return DEFAULT_NOTE

    summary = "; ".join(candidates[:limit])
    if len(summary) > 420:
        summary = summary[:417].rstrip() + "..."
    return summary


def build_release_markdown(version: str, section: str) -> str:
    body = section.strip()
    if not body:
        body = f"- {DEFAULT_NOTE}"
    return f"## Что нового в v{version}\n\n{body}\n"


def sync_release_notes(
    version: str,
    changelog_path: Path,
    updates_json_path: Path,
    release_notes_path: Path,
) -> None:
    changelog = read_text(changelog_path)
    section = find_changelog_section(changelog, version)
    summary = build_notes_summary(section)
    release_md = build_release_markdown(version, section)

    updates = {}
    if updates_json_path.exists():
        try:
            updates = json.loads(updates_json_path.read_text(encoding="utf-8-sig"))
        except Exception:
            updates = {}
    updates["notes"] = summary
    updates_json_path.write_text(
        json.dumps(updates, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    release_notes_path.parent.mkdir(parents=True, exist_ok=True)
    release_notes_path.write_text(release_md, encoding="utf-8-sig")

    print(f"[notes] version={version}")
    print(f"[notes] summary={summary}")
    print(f"[notes] release_body={release_notes_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--changelog", required=True)
    parser.add_argument("--updates-json", required=True)
    parser.add_argument("--release-notes", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sync_release_notes(
        version=str(args.version).strip().lstrip("v"),
        changelog_path=Path(args.changelog),
        updates_json_path=Path(args.updates_json),
        release_notes_path=Path(args.release_notes),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
