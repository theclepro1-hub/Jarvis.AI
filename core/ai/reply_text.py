from __future__ import annotations

import re


SUPPORTED_AI_MODES = ("auto", "fast", "quality")

_MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MARKDOWN_FENCE_PATTERN = re.compile(r"```(?:[\w+-]+\n)?|```")
_MARKDOWN_MARKERS_PATTERN = re.compile(r"(\*\*|__|~~|`)")
_LIST_PREFIX_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
_TABLE_SEPARATOR_PATTERN = re.compile(r"^[\s|:\-]+$")


def sanitize_ai_reply_text(text: str, *, max_lines: int = 5, max_chars: int = 800) -> str:
    clean = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not clean:
        return ""

    clean = _MARKDOWN_LINK_PATTERN.sub(r"\1", clean)
    clean = _MARKDOWN_FENCE_PATTERN.sub("", clean)
    clean = _MARKDOWN_MARKERS_PATTERN.sub("", clean)

    lines: list[str] = []
    for raw_line in clean.split("\n"):
        line = raw_line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if line.count("|") >= 2:
            if _TABLE_SEPARATOR_PATTERN.fullmatch(line):
                continue
            cells = [_MARKDOWN_MARKERS_PATTERN.sub("", cell).strip() for cell in line.strip("|").split("|")]
            cells = [cell for cell in cells if cell]
            if not cells:
                continue
            line = " — ".join(cells)
        line = _LIST_PREFIX_PATTERN.sub("", line)
        line = re.sub(r"\s{2,}", " ", line)
        if line:
            lines.append(line)

    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()

    compact: list[str] = []
    for line in lines:
        if line == "" and (not compact or compact[-1] == ""):
            continue
        compact.append(line)

    if not compact:
        return ""
    if len(compact) > max_lines:
        compact = compact[:max_lines]
        compact[-1] = compact[-1].rstrip(" .") + "…"

    reply = "\n".join(compact).strip()
    if len(reply) > max_chars:
        reply = reply[:max_chars].rstrip(" ,;:-") + "…"
    return reply
