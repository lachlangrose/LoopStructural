from __future__ import annotations

import sys
from pathlib import Path


def _append_src(path: Path) -> None:
    src = path / "src"
    src_str = str(src)
    if src.exists() and src_str not in sys.path:
        sys.path.insert(0, src_str)


ROOT = Path(__file__).resolve().parents[3]
PACKAGES = ROOT / "packages"

_append_src(PACKAGES / "loop_common")
_append_src(PACKAGES / "loop_model")
_append_src(PACKAGES / "loop_engine")
