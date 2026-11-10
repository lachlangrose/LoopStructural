"""Check that ROADMAP.md names the loop-skills package (spec 007, FR-015)."""

from pathlib import Path

import pytest

# This file sits at packages/loop_skills/tests/, so index 3 is the repository root.
ROOT = Path(__file__).resolve().parents[3]
ROADMAP = ROOT / "ROADMAP.md"


def test_roadmap_names_package() -> None:
    """Assert that ROADMAP.md names the package and its spec folder.

    Notes
    -----
    The test skips when ROADMAP.md is not in the repository root.

    Raises
    ------
    AssertionError
        If ROADMAP.md does not contain one of the required names.
    """
    if not ROADMAP.is_file():
        pytest.skip("ROADMAP.md is not in the repository root")
    text = ROADMAP.read_text(encoding="utf-8")
    for name in ("packages/loop_skills", "loop-skills", "specs/007-loop-skills"):
        assert name in text, f"ROADMAP.md does not name {name!r}"
