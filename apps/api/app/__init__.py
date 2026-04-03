from pathlib import Path
import sys


def _find_shared_src(current_dir: Path) -> Path | None:
    for base_dir in (current_dir, *current_dir.parents):
        candidate = base_dir / "packages" / "shared"
        if candidate.exists():
            return candidate
    return None


_CURRENT_DIR = Path(__file__).resolve().parent
_SHARED_SRC = _find_shared_src(_CURRENT_DIR)

if _SHARED_SRC is not None:
    shared_path = str(_SHARED_SRC)
    if shared_path not in sys.path:
        sys.path.insert(0, shared_path)
