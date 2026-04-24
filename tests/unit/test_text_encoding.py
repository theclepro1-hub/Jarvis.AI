from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TEXT_ROOTS = ("core", "ui", "app", "tests")
TEXT_SUFFIXES = {".py", ".qml", ".md", ".toml"}
SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", "build", "dist"}

MOJIBAKE_MARKERS = (
    "\u0420\u045f",
    "\u0420\u2018",
    "\u0420\u201c",
    "\u0420\u201d",
    "\u0420\u040b",
    "\u0420\u0408",
    "\u0420\u045c",
    "\u0420\u0455",
    "\u0420\u00b0",
    "\u0420\u00b5",
    "\u0420\u0451",
    "\u0420\u0454",
    "\u0420\u0458",
    "\u0420\u0457",
    "\u0420\u0491",
    "\u0420\u00bb",
    "\u0420\u0406",
    "\u0421\u201a",
    "\u0421\u0402",
    "\u0421\u0403",
    "\u0421\u040a",
    "\u0421\u2039",
    "\u0421\u040f",
    "\u0421\u040e",
    "\u0421\u2021",
    "\u0421\u02dc",
    "\u0421\u2030",
    "\u0421\u2020",
    "\u0421\u040c",
    "\u0432\u0402",
    "\u0412\u00ab",
    "\u0412\u00bb",
    "\u00c2",
    "\ufffd",
)


def _text_files() -> list[Path]:
    files: list[Path] = []
    for root_name in TEXT_ROOTS:
        root = REPO_ROOT / root_name
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            files.append(path)
    return files


def test_source_text_has_no_mojibake_markers() -> None:
    hits: list[str] = []
    for path in _text_files():
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(marker in line for marker in MOJIBAKE_MARKERS):
                relative_path = path.relative_to(REPO_ROOT)
                hits.append(f"{relative_path}:{line_number}: {line.strip()}")

    assert hits == []
