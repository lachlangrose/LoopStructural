"""Tests for loading skill files with load_skill and iter_skills."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from loop_skills._skill import (
    Skill,
    SkillError,
    iter_skills,
    load_skill,
    split_frontmatter,
)


def _write_skill_bytes(folder: Path, data: bytes) -> Path:
    """Write the bytes of a SKILL.md file into a folder.

    Parameters
    ----------
    folder : Path
        Skill folder. The folder is created when it does not exist.
    data : bytes
        File content to write.

    Returns
    -------
    Path
        Path to the written SKILL.md file.
    """
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "SKILL.md"
    path.write_bytes(data)
    return path


def _copy_good_skill(root: Path, name: str) -> Path:
    """Copy the good-skill folder to a new folder with another name.

    Parameters
    ----------
    root : Path
        Skills directory that receives the copy.
    name : str
        Name of the new skill. The folder name and the name line of
        SKILL.md both use this value.

    Returns
    -------
    Path
        Path to the new SKILL.md file.
    """
    dest = root / name
    shutil.copytree(root / "good-skill", dest)
    data = (dest / "SKILL.md").read_bytes().replace(b"good-skill", name.encode("utf-8"))
    return _write_skill_bytes(dest, data)


def test_load_skill_reads_good_skill(fixture_skills: Path) -> None:
    """Load a valid skill file and check its fields.

    Parameters
    ----------
    fixture_skills : Path
        Copy of the fixture skills directory.
    """
    skill = load_skill(fixture_skills / "good-skill" / "SKILL.md")
    assert isinstance(skill, Skill)
    assert skill.name == "good-skill"
    assert skill.requires == "json>=0"
    assert skill.body.strip()


def test_load_skill_without_pin_names_file(fixture_skills: Path) -> None:
    """Raise SkillError for a skill with no version pin, and name the file.

    Parameters
    ----------
    fixture_skills : Path
        Copy of the fixture skills directory.
    """
    with pytest.raises(SkillError) as info:
        load_skill(fixture_skills / "no-pin" / "SKILL.md")
    assert "SKILL.md" in str(info.value)


def test_load_skill_rejects_name_that_differs_from_folder(
    tmp_path: Path, fixture_skills: Path
) -> None:
    """Raise SkillError when the name does not match the folder name.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.
    fixture_skills : Path
        Copy of the fixture skills directory.
    """
    dest = tmp_path / "renamed-skill"
    shutil.copytree(fixture_skills / "good-skill", dest)
    with pytest.raises(SkillError):
        load_skill(dest / "SKILL.md")


def test_load_skill_rejects_missing_frontmatter(tmp_path: Path) -> None:
    """Raise SkillError when the first line is not a frontmatter rule.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.
    """
    path = _write_skill_bytes(tmp_path / "plain-skill", b"# Plain skill\n\nNo header here.\n")
    with pytest.raises(SkillError):
        load_skill(path)


def test_split_frontmatter_requires_opening_rule() -> None:
    """Raise SkillError when the text has no opening frontmatter rule."""
    with pytest.raises(SkillError):
        split_frontmatter("# No header\n")


def test_load_skill_rejects_bad_requires_range(tmp_path: Path, fixture_skills: Path) -> None:
    """Raise SkillError when the requires value is not a version range.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.
    fixture_skills : Path
        Copy of the fixture skills directory.
    """
    data = (fixture_skills / "good-skill" / "SKILL.md").read_bytes()
    bad = data.replace(b"json>=0", b"not a range")
    path = _write_skill_bytes(tmp_path / "range" / "good-skill", bad)
    with pytest.raises(SkillError):
        load_skill(path)


def test_iter_skills_returns_skills_in_name_order(fixture_skills: Path) -> None:
    """Return the skills that load, sorted by name.

    Parameters
    ----------
    fixture_skills : Path
        Copy of the fixture skills directory.
    """
    # Remove every folder that does not load, so that iter_skills
    # does not raise.
    for bad in ("no-pin", "bad-syntax", "bad-name"):
        shutil.rmtree(fixture_skills / bad)
    _copy_good_skill(fixture_skills, "zeta-skill")
    _copy_good_skill(fixture_skills, "alpha-skill")
    names = [skill.name for skill in iter_skills(fixture_skills)]
    assert names == ["alpha-skill", "good-skill", "zeta-skill"]


def test_iter_skills_raises_for_skill_without_pin(fixture_skills: Path) -> None:
    """Raise SkillError when a skill in the directory has no version pin.

    Parameters
    ----------
    fixture_skills : Path
        Copy of the fixture skills directory.
    """
    with pytest.raises(SkillError):
        list(iter_skills(fixture_skills))


def test_iter_skills_default_root_returns_list() -> None:
    """Return a list when iter_skills is called with no argument."""
    result = iter_skills()
    assert isinstance(result, list)


def test_load_skill_accepts_crlf_line_endings(tmp_path: Path, fixture_skills: Path) -> None:
    """Load a skill file that uses CRLF line endings.

    Git can check out files with CRLF endings on Windows, so the loader
    must read them the same way as LF files.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.
    fixture_skills : Path
        Copy of the fixture skills directory.
    """
    original = load_skill(fixture_skills / "good-skill" / "SKILL.md")
    data = (fixture_skills / "good-skill" / "SKILL.md").read_bytes()
    crlf = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    path = _write_skill_bytes(tmp_path / "crlf" / "good-skill", crlf)
    skill = load_skill(path)
    assert skill.name == original.name
    assert skill.requires == original.requires
