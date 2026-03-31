#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_ai.release_checks import assert_version_consistency


def main() -> int:
    expected, versions = assert_version_consistency(ROOT)
    print(f"[version] OK: {expected}")
    for path, version in versions.items():
        print(f"[version] {path} -> {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
