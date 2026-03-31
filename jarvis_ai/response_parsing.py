from __future__ import annotations

import ast
import json
import re
from typing import Any


def balanced_json_segments(text: str):
    src = str(text or "")
    if not src:
        return []
    candidates = []
    for start in (match.start() for match in re.finditer(r"[\{\[]", src)):
        stack = []
        in_string = False
        escaped = False
        for idx in range(start, len(src)):
            ch = src[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch in "{[":
                stack.append(ch)
                continue
            if ch in "}]":
                if not stack:
                    break
                opening = stack.pop()
                if (opening == "{" and ch != "}") or (opening == "[" and ch != "]"):
                    break
                if not stack:
                    segment = src[start : idx + 1].strip()
                    if segment:
                        candidates.append(segment)
                    break
    unique = []
    seen = set()
    for segment in candidates:
        if segment in seen:
            continue
        seen.add(segment)
        unique.append(segment)
    return unique


def try_parse_json_candidate(candidate: str) -> Any:
    raw = str(candidate or "").strip()
    if not raw:
        return None
    for variant in (
        raw,
        raw.replace("“", '"').replace("”", '"').replace("’", "'"),
    ):
        try:
            return json.loads(variant)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    try:
        parsed = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def extract_json_block(text: str):
    src = str(text or "").strip()
    if not src:
        return None

    fenced_match = re.search(r"```(?:json)?\s*(.*?)\s*```", src, flags=re.IGNORECASE | re.DOTALL)
    if fenced_match:
        src = fenced_match.group(1).strip()

    direct = try_parse_json_candidate(src)
    if isinstance(direct, (dict, list)):
        return direct

    for candidate in balanced_json_segments(src):
        parsed = try_parse_json_candidate(candidate)
        if isinstance(parsed, (dict, list)):
            return parsed

    reply_match = re.search(r'"reply"\s*:\s*"((?:[^"\\]|\\.)+)"', src)
    if reply_match:
        try:
            reply = bytes(reply_match.group(1), "utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
            reply = reply_match.group(1)
        return {"reply": reply}
    return None


__all__ = ["balanced_json_segments", "extract_json_block", "try_parse_json_candidate"]
