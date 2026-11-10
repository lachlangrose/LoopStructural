"""Check that the package README names the agent install targets."""

from __future__ import annotations

from pathlib import Path

import pytest

README_PATH: Path = Path(__file__).resolve().parents[1] / "README.md"


@pytest.mark.parametrize(
    "expected",
    [
        ".claude/skills",
        ".agents/skills",
        ".github/copilot-instructions.md",
        "loop-skills install",
        "loop-skills uninstall",
    ],
)
def test_readme_names_agent_target(expected: str) -> None:
    """Assert that the README mentions one agent target or CLI command.

    Parameters
    ----------
    expected : str
        The text that the README must contain.

    Returns
    -------
    None
        The test passes when the text is in the README.
    """
    text: str = README_PATH.read_text(encoding="utf-8")
    assert expected in text, f"README.md does not name {expected!r}"
