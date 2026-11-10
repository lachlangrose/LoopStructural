"""Guard tests: the core package does not depend on the skills package.

Spec 007-loop-skills, scenario 7 and FR-001. These tests pass at once and
must keep passing.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CORE_DIR = ROOT / "LoopStructural"


def test_core_imports_without_skills() -> None:
    """The core package imports when the loop_skills module is blocked.

    Setting ``sys.modules['loop_skills']`` to ``None`` makes any import of
    ``loop_skills`` fail. The core must still import in that state.
    """
    if importlib.util.find_spec("LoopStructural") is None:
        pytest.skip("LoopStructural is not installed in this environment")

    code = "import sys; sys.modules['loop_skills'] = None; import LoopStructural"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_core_does_not_name_skills() -> None:
    """No core source file and no root pyproject.toml names the skills package.

    The check reads text only. It looks for the import name ``loop_skills``
    and the distribution name ``loop-skills``.
    """
    if not CORE_DIR.is_dir():
        pytest.skip("LoopStructural/ is not present in the repository root")

    banned = ("loop_skills", "loop-skills")

    for py_file in CORE_DIR.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="replace")
        for name in banned:
            assert name not in text, f"{py_file} names {name!r}"

    pyproject = ROOT / "pyproject.toml"
    root_text = pyproject.read_text(encoding="utf-8", errors="replace")
    assert "loop-skills" not in root_text, f"{pyproject} names 'loop-skills'"
