from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def _bundle_roots():
    base = ROOT / "publish_tools" / "github_bundle"
    roots = []
    if base.exists():
        roots.extend(path for path in base.glob("JARVIS_AI_2_v*") if path.is_dir())
        roots.append(base)
    return roots


def _normalized(path_value: str) -> str:
    try:
        return str(Path(path_value).resolve())
    except Exception:
        return str(path_value)


root_text = _normalized(str(ROOT))
bundle_roots = {_normalized(str(path)) for path in _bundle_roots()}
sys.path[:] = [entry for entry in sys.path if _normalized(entry) not in bundle_roots]
if root_text in {_normalized(entry) for entry in sys.path}:
    sys.path[:] = [entry for entry in sys.path if _normalized(entry) != root_text]
sys.path.insert(0, str(ROOT))

wrong_pkg = sys.modules.get("jarvis_ai")
if wrong_pkg is not None and not _normalized(str(getattr(wrong_pkg, "__file__", ""))).startswith(root_text):
    for name in list(sys.modules):
        if name == "jarvis_ai" or name.startswith("jarvis_ai."):
            sys.modules.pop(name, None)
