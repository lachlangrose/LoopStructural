"""Tests for the Python block and syntax checks of skill bodies (spec scenario 14, FR-012)."""

from __future__ import annotations

from pathlib import Path

from loop_skills._check import (
    CodeBlock,
    Problem,
    check_frontmatter_set,
    check_syntax,
    python_blocks,
)
from loop_skills._skill import load_skill


def _write_text_fence_skill(tmp_path: Path) -> Path:
    """Write a skill whose only fenced block is a ``text`` block.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.

    Returns
    -------
    Path
        The path of the written ``SKILL.md`` file.
    """
    folder = tmp_path / "text-fence"
    folder.mkdir()
    skill_file = folder / "SKILL.md"
    skill_file.write_text(
        "---\n"
        "name: text-fence\n"
        "description: Skill with a text fence only.\n"
        "requires: json>=0\n"
        "---\n"
        "\n"
        "```text\n"
        "print('not python')\n"
        "```\n",
        encoding="utf-8",
    )
    return skill_file


def test_python_blocks_returns_one_block_with_fence_line(fixture_skills: Path) -> None:
    """Find the one Python block of the good skill and its opening fence line.

    Parameters
    ----------
    fixture_skills : Path
        Copy of the fixture skills.
    """
    skill_file = fixture_skills / "good-skill" / "SKILL.md"
    good = load_skill(skill_file)
    lines = skill_file.read_text(encoding="utf-8").splitlines()
    fence_line = next(
        number for number, text in enumerate(lines, start=1) if text.strip().startswith("```python")
    )

    blocks = python_blocks(good)

    assert len(blocks) == 1
    assert isinstance(blocks[0], CodeBlock)
    assert blocks[0].index == 1
    assert blocks[0].line == fence_line


def test_check_syntax_passes_for_good_skill(fixture_skills: Path) -> None:
    """Report no syntax problem for the good skill.

    Parameters
    ----------
    fixture_skills : Path
        Copy of the fixture skills.
    """
    good = load_skill(fixture_skills / "good-skill" / "SKILL.md")

    assert check_syntax(good) == []


def test_check_syntax_reports_bad_block(fixture_skills: Path) -> None:
    """Report one syntax problem, with the block number, for the bad skill.

    Parameters
    ----------
    fixture_skills : Path
        Copy of the fixture skills.
    """
    bad = load_skill(fixture_skills / "bad-syntax" / "SKILL.md")

    problems = check_syntax(bad)

    assert len(problems) == 1
    problem = problems[0]
    assert isinstance(problem, Problem)
    assert problem.kind == "syntax"
    assert problem.skill == "bad-syntax"
    assert "block 1" in problem.detail


def test_text_fence_is_not_a_python_block(tmp_path: Path) -> None:
    """Ignore a fenced block that is not marked as Python.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.
    """
    skill = load_skill(_write_text_fence_skill(tmp_path))

    assert python_blocks(skill) == []


def test_check_frontmatter_set_reports_duplicate_name(fixture_skills: Path) -> None:
    """Report a uniqueness problem that names the duplicated skill.

    Parameters
    ----------
    fixture_skills : Path
        Copy of the fixture skills.
    """
    good = load_skill(fixture_skills / "good-skill" / "SKILL.md")

    problems = check_frontmatter_set([good, good])

    assert len(problems) == 1
    assert problems[0].kind == "unique"
    assert "good-skill" in problems[0].detail


def test_check_frontmatter_set_passes_single_skill(fixture_skills: Path) -> None:
    """Report no uniqueness problem for one skill.

    Parameters
    ----------
    fixture_skills : Path
        Copy of the fixture skills.
    """
    good = load_skill(fixture_skills / "good-skill" / "SKILL.md")

    assert check_frontmatter_set([good]) == []
