"""Load skill files (SKILL.md) that have a YAML frontmatter block."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from packaging.requirements import Requirement

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Skill:
    """One skill that was loaded from a SKILL.md file.

    Attributes
    ----------
    name : str
        Skill name. It equals the name of the skill folder.
    description : str
        Short description of the skill.
    requires : str
        Requirement string for the version pin.
    path : Path
        Path to the SKILL.md file.
    body : str
        Text after the frontmatter block.
    """

    name: str
    description: str
    requires: str
    path: Path
    body: str


class SkillError(ValueError):
    """Raise when a skill file is not valid. The message names the file."""


def skills_root() -> Path:
    """Return the folder that holds the skills of the package.

    Returns
    -------
    Path
        Path to the ``skills`` folder next to this module.
    """
    return Path(__file__).parent / "skills"


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a text into the frontmatter mapping and the body.

    Parameters
    ----------
    text : str
        Full text of a skill file. Both LF and CRLF line endings work.

    Returns
    -------
    tuple[dict[str, Any], str]
        The frontmatter mapping and the text after the closing line.

    Raises
    ------
    SkillError
        If the frontmatter is missing, not closed, not valid YAML, or not
        a mapping. The message has no file path.
    """
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise SkillError("the first line must be '---'")
    end = None
    for index in range(1, len(lines)):
        if lines[index] == "---":
            end = index
            break
    if end is None:
        raise SkillError("the frontmatter has no closing '---' line")
    try:
        data = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise SkillError(f"the frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SkillError("the frontmatter must be a mapping")
    return data, "\n".join(lines[end + 1 :])


def _check(path: Path, text: str) -> Skill:
    """Build a Skill from the text of a file.

    Parameters
    ----------
    path : Path
        Path to the SKILL.md file.
    text : str
        Text of the file.

    Returns
    -------
    Skill
        The loaded skill.

    Raises
    ------
    SkillError
        If a check fails. The message has no file path.
    """
    meta, body = split_frontmatter(text)
    values: dict[str, str] = {}
    for key in ("name", "description", "requires"):
        value = meta.get(key)
        if not isinstance(value, str) or not value.strip():
            raise SkillError(f"the key '{key}' must be a non-empty string")
        values[key] = value
    name = values["name"]
    if not _NAME_RE.match(name):
        raise SkillError(f"the name '{name}' is not valid")
    if name != path.parent.name:
        raise SkillError(f"the name '{name}' differs from the folder name '{path.parent.name}'")
    try:
        Requirement(values["requires"])
    except Exception as exc:
        raise SkillError(f"requires '{values['requires']}' is not valid: {exc}") from exc
    return Skill(
        name=name,
        description=values["description"],
        requires=values["requires"],
        path=path,
        body=body,
    )


def load_skill(path: Path) -> Skill:
    """Load one skill from a SKILL.md file.

    Parameters
    ----------
    path : Path
        Path to the SKILL.md file.

    Returns
    -------
    Skill
        The loaded skill.

    Raises
    ------
    SkillError
        If the file is not valid. The message starts with the file path.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
        return _check(Path(path), text)
    except SkillError as exc:
        raise SkillError(f"{path}: {exc}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise SkillError(f"{path}: cannot read the file: {exc}") from exc


def iter_skills(root: Path | None = None) -> list[Skill]:
    """Load all skills in a folder, sorted by folder name.

    Parameters
    ----------
    root : Path | None
        Folder that holds the skill folders. The default is the skills
        folder of the package.

    Returns
    -------
    list[Skill]
        The loaded skills. The list is empty when the folder is missing.

    Raises
    ------
    SkillError
        If one skill file is not valid.
    """
    base = skills_root() if root is None else Path(root)
    if not base.is_dir():
        return []
    skills: list[Skill] = []
    for folder in sorted(base.iterdir(), key=lambda item: item.name):
        skill_file = folder / "SKILL.md"
        if folder.is_dir() and skill_file.is_file():
            skills.append(load_skill(skill_file))
    return skills
