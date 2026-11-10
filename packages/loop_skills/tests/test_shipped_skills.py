"""Tests for the skills that the loop-skills package ships."""

from __future__ import annotations

import pytest
from loop_skills._check import check_frontmatter_set, check_syntax, python_blocks
from loop_skills._skill import Skill, iter_skills, skills_root
from packaging.requirements import Requirement

EXPECTED_PINS: dict[str, str] = {
    "build-model": "LoopStructural",
    "inspect-model": "LoopStructural",
    "map2loop-prepare": "map2loop",
    "install-help": "loop-skills",
}
NAMES: list[str] = list(EXPECTED_PINS)
PYTHON_NAMES: list[str] = ["build-model", "inspect-model", "map2loop-prepare"]
MAX_LINES = 500


def _get(name: str) -> Skill:
    """Find a shipped skill by name.

    Parameters
    ----------
    name : str
        Name of the skill.

    Returns
    -------
    Skill
        The skill with this name.
    """
    for skill in iter_skills():
        if skill.name == name:
            return skill
    pytest.fail(f"skill '{name}' is not shipped")


def test_skill_set_is_exact() -> None:
    """The package ships exactly the expected skills."""
    assert [s.name for s in iter_skills()] == sorted(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_skill_valid(name: str) -> None:
    """The skill loads and its pin names the expected distribution.

    Parameters
    ----------
    name : str
        Name of the skill.
    """
    skill = _get(name)
    assert Requirement(skill.requires).name == EXPECTED_PINS[name]


@pytest.mark.parametrize("name", NAMES)
def test_skill_size(name: str) -> None:
    """The SKILL.md file has fewer than 500 lines.

    Parameters
    ----------
    name : str
        Name of the skill.
    """
    skill = _get(name)
    lines = skill.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) < MAX_LINES


@pytest.mark.parametrize("name", NAMES)
def test_skill_folder_has_only_skill_md(name: str) -> None:
    """The skill folder holds one entry, the SKILL.md file.

    Parameters
    ----------
    name : str
        Name of the skill.
    """
    folder = skills_root() / name
    if not folder.is_dir():
        pytest.fail(f"skill folder '{name}' is missing")
    assert [p.name for p in folder.iterdir()] == ["SKILL.md"]


@pytest.mark.parametrize("name", NAMES)
def test_skill_code_parses(name: str) -> None:
    """The Python blocks of the skill have valid syntax.

    Parameters
    ----------
    name : str
        Name of the skill.
    """
    skill = _get(name)
    assert check_syntax(skill) == []
    if name in PYTHON_NAMES:
        assert len(python_blocks(skill)) >= 1


def test_names_unique() -> None:
    """The shipped skills have valid and unique front matter."""
    assert check_frontmatter_set(iter_skills()) == []
