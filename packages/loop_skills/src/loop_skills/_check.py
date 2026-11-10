"""Check the frontmatter set and the Python code blocks of skills."""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from ._skill import Skill


@dataclass(frozen=True)
class CodeBlock:
    """One fenced Python block of a skill body.

    Attributes
    ----------
    index : int
        Number of the block in the skill. The first block is 1.
    line : int
        1-based line of the opening fence in the SKILL.md file.
    source : str
        Code text between the fences.
    """

    index: int
    line: int
    source: str


@dataclass(frozen=True)
class Problem:
    """One problem that a check found.

    Attributes
    ----------
    skill : str
        Name of the skill.
    kind : Literal["frontmatter", "unique", "syntax", "name", "pin"]
        Type of the check that failed.
    detail : str
        Text that explains the problem.
    """

    skill: str
    kind: Literal["frontmatter", "unique", "syntax", "name", "pin"]
    detail: str


@dataclass(frozen=True)
class NameReport:
    """Result of the name check.

    Attributes
    ----------
    status : Literal["checked", "skipped"]
        Whether the check ran.
    reason : str
        Reason for a skipped check. Empty when the check ran.
    problems : list[Problem]
        Problems that the check found.
    checked : int
        Number of names that the check verified.
    unchecked : int
        Number of names that the check could not verify.
    """

    status: Literal["checked", "skipped"]
    reason: str
    problems: list[Problem]
    checked: int
    unchecked: int


def _closing_rule_line(skill: Skill) -> int:
    """Find the 1-based file line of the closing frontmatter rule.

    Parameters
    ----------
    skill : Skill
        The skill to inspect.

    Returns
    -------
    int
        Line number of the closing ``---`` line.
    """
    lines = skill.path.read_text(encoding="utf-8").splitlines()
    for number, text in enumerate(lines[1:], start=2):
        if text == "---":
            return number
    return 1


def python_blocks(skill: Skill) -> list[CodeBlock]:
    """Find the fenced Python blocks in the body of a skill.

    A block opens at a line that is ``` ```python ``` and closes at the next
    line that is ``` ``` ```. Trailing spaces are ignored.

    Parameters
    ----------
    skill : Skill
        The skill to scan.

    Returns
    -------
    list[CodeBlock]
        The blocks in file order.
    """
    offset = _closing_rule_line(skill)
    blocks: list[CodeBlock] = []
    open_line: int | None = None
    source: list[str] = []
    for number, text in enumerate(skill.body.splitlines(), start=1):
        stripped = text.strip()
        if open_line is None:
            if stripped == "```python":
                open_line = number
                source = []
        elif stripped == "```":
            blocks.append(
                CodeBlock(
                    index=len(blocks) + 1,
                    line=offset + open_line,
                    source="\n".join(source),
                )
            )
            open_line = None
        else:
            source.append(text)
    return blocks


def check_frontmatter_set(skills: Sequence[Skill]) -> list[Problem]:
    """Check that each skill name is unique in a set of skills.

    Parameters
    ----------
    skills : Sequence[Skill]
        The skills to check.

    Returns
    -------
    list[Problem]
        One ``unique`` problem for each repeated name.
    """
    counts = Counter(skill.name for skill in skills)
    return [
        Problem(name, "unique", f"the name '{name}' is used {count} times")
        for name, count in counts.items()
        if count > 1
    ]


def check_syntax(skill: Skill) -> list[Problem]:
    """Check that each Python block of a skill parses.

    Parameters
    ----------
    skill : Skill
        The skill to check.

    Returns
    -------
    list[Problem]
        One ``syntax`` problem for each block that does not parse.
    """
    problems: list[Problem] = []
    for block in python_blocks(skill):
        try:
            ast.parse(block.source)
        except SyntaxError as err:
            problems.append(
                Problem(
                    skill.name,
                    "syntax",
                    f"block {block.index} (line {block.line}): {err.msg}",
                )
            )
    return problems
