from pathlib import Path
import sys

_CURRENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CURRENT_DIR.parents[2]
_SHARED_SRC = _REPO_ROOT / "packages" / "shared"

if _SHARED_SRC.exists():
    shared_path = str(_SHARED_SRC)
    if shared_path not in sys.path:
        sys.path.insert(0, shared_path)
