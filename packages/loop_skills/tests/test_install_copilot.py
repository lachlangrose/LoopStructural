"""Tests for the Copilot instructions block (spec scenarios 12 and 17, FR-018)."""

from __future__ import annotations

from pathlib import Path

import pytest
from loop_skills._copilot import (
    BEGIN,
    END,
    install_block,
    render_block,
    uninstall_block,
)
from loop_skills._install import InstallError
from loop_skills._skill import Skill, iter_skills, load_skill

OLD_TEXT = "My rules\n"


@pytest.fixture
def skills(fixture_skills: Path) -> list[Skill]:
    """Load the good fixture skill.

    Parameters
    ----------
    fixture_skills : Path
        Folder that holds the fixture skills.

    Returns
    -------
    list[Skill]
        A list with the good skill only.
    """
    return [load_skill(fixture_skills / "good-skill" / "SKILL.md")]


def _target(base: Path) -> Path:
    """Return the path of the Copilot file.

    Parameters
    ----------
    base : Path
        Base folder.

    Returns
    -------
    Path
        Path of `.github/copilot-instructions.md` below the base folder.
    """
    return base / ".github" / "copilot-instructions.md"


def test_markers() -> None:
    """The marker constants have the documented text."""
    assert BEGIN == "<!-- loop-skills:begin -->"
    assert END == "<!-- loop-skills:end -->"


def test_install_creates_file(tmp_path: Path, skills: list[Skill]) -> None:
    """Install with no file creates the file and the folder."""
    report = install_block(tmp_path, skills, "0.1.0")
    target = _target(tmp_path)
    assert target.is_file()
    text = target.read_bytes().decode("utf-8")
    assert text.startswith(BEGIN)
    assert text.rstrip("\r\n").endswith(END)
    assert text.replace(render_block(skills, "0.1.0", "\n"), "").strip() == ""
    assert target in report.created
    assert target.parent in report.created
    assert [o.action for o in report.outcomes] == ["installed"]


def test_install_keeps_old_text(tmp_path: Path, skills: list[Skill]) -> None:
    """Text outside the markers stays byte-equal, and the block follows."""
    target = _target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(OLD_TEXT.encode("utf-8"))
    install_block(tmp_path, skills, "0.1.0")
    text = target.read_bytes().decode("utf-8")
    block = render_block(skills, "0.1.0", "\n")
    assert text.startswith(OLD_TEXT)
    assert text[len(OLD_TEXT) :].startswith("\n" + BEGIN)
    assert text.replace(block, "") == OLD_TEXT + "\n\n"


def test_second_install_replaces_block(tmp_path: Path, skills: list[Skill]) -> None:
    """A second install changes only the text between the markers."""
    target = _target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(OLD_TEXT.encode("utf-8"))
    install_block(tmp_path, skills, "0.1.0")
    first = target.read_bytes().decode("utf-8")
    start = first.index(BEGIN)
    stop = first.index(END) + len(END)
    before, after = first[:start], first[stop:]
    report = install_block(tmp_path, skills, "0.2.0")
    second = target.read_bytes().decode("utf-8")
    assert second.startswith(before)
    assert second.endswith(after)
    assert "Managed by loop-skills 0.2.0." in second
    assert "Managed by loop-skills 0.1.0." not in second
    assert [o.action for o in report.outcomes] == ["replaced"]


def test_begin_without_end_raises(tmp_path: Path, skills: list[Skill]) -> None:
    """A file with BEGIN and no END raises an error and stays unchanged."""
    target = _target(tmp_path)
    target.parent.mkdir(parents=True)
    data = f"{OLD_TEXT}{BEGIN}\nhalf a block\n".encode()
    target.write_bytes(data)
    with pytest.raises(InstallError, match="markers"):
        install_block(tmp_path, skills, "0.1.0")
    assert target.read_bytes() == data


def test_crlf_is_kept(tmp_path: Path, skills: list[Skill]) -> None:
    """A CRLF file keeps CRLF in the old text and in the block."""
    target = _target(tmp_path)
    target.parent.mkdir(parents=True)
    old = b"My rules\r\nSecond line\r\n"
    target.write_bytes(old)
    install_block(tmp_path, skills, "0.1.0")
    data = target.read_bytes()
    assert data.startswith(old)
    assert data.count(b"\n") == data.count(b"\r\n")
    assert b"\r\n" + BEGIN.encode() in data


def test_block_content(skills: list[Skill]) -> None:
    """The block holds the name, the description, the body and the version line."""
    block = render_block(skills, "0.1.0", "\n")
    skill = skills[0]
    assert block.startswith(BEGIN)
    assert block.rstrip("\n").endswith(END)
    assert "## Skill: good-skill" in block
    assert skill.description in block
    assert skill.body.strip() in block
    assert (
        "<!-- Managed by loop-skills 0.1.0. Change text outside these markers only. -->"
        in block.split("\n")
    )


def test_uninstall_removes_block(tmp_path: Path, skills: list[Skill]) -> None:
    """Uninstall removes the block and the blank line before it."""
    target = _target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(OLD_TEXT.encode("utf-8"))
    install_block(tmp_path, skills, "0.1.0")
    uninstall_block(tmp_path)
    assert target.read_bytes() == OLD_TEXT.encode("utf-8")


def test_uninstall_block_only_leaves_empty_file(tmp_path: Path, skills: list[Skill]) -> None:
    """Uninstall leaves an empty file when only the block was there."""
    install_block(tmp_path, skills, "0.1.0")
    target = _target(tmp_path)
    uninstall_block(tmp_path)
    assert target.is_file()
    assert target.read_bytes() == b""


def test_uninstall_without_markers_changes_nothing(tmp_path: Path) -> None:
    """Uninstall with no markers or no file returns an empty report."""
    report = uninstall_block(tmp_path)
    assert report.outcomes == []
    assert not _target(tmp_path).exists()
    target = _target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(OLD_TEXT.encode("utf-8"))
    report = uninstall_block(tmp_path)
    assert report.outcomes == []
    assert target.read_bytes() == OLD_TEXT.encode("utf-8")


def _write_user_file(base: Path, data: bytes) -> Path:
    """Write the user text of the Copilot file.

    Parameters
    ----------
    base : Path
        Base folder.
    data : bytes
        The bytes of the user text.

    Returns
    -------
    Path
        Path of the Copilot file.
    """
    target = _target(base)
    target.parent.mkdir(parents=True)
    target.write_bytes(data)
    return target


def test_shipped_skills_round_trip(tmp_path: Path) -> None:
    """The shipped skills install, install again and uninstall without damage."""
    user = b"# My rules\n\nUse tabs.\n"
    target = _write_user_file(tmp_path, user)
    shipped = iter_skills()
    install_block(tmp_path, shipped, "0.1.0")
    once = target.read_bytes()
    install_block(tmp_path, shipped, "0.1.0")
    assert target.read_bytes() == once
    uninstall_block(tmp_path)
    assert END not in target.read_bytes().decode("utf-8")
    assert target.read_bytes() == user


def test_quoted_marker_in_user_text_is_ignored(tmp_path: Path) -> None:
    """A marker that the user quotes inside a sentence is not a marker."""
    user = (
        b"Do not remove the line `<!-- loop-skills:end -->` "
        b"or `<!-- loop-skills:begin -->` by hand.\n"
    )
    target = _write_user_file(tmp_path, user)
    shipped = iter_skills()
    install_block(tmp_path, shipped, "0.1.0")
    once = target.read_bytes()
    assert once.startswith(user)
    install_block(tmp_path, shipped, "0.1.0")
    assert target.read_bytes() == once
    uninstall_block(tmp_path)
    assert target.read_bytes() == user


def test_shipped_skills_round_trip_crlf(tmp_path: Path) -> None:
    """The round trip keeps CRLF line ends."""
    user = b"# My rules\r\n\r\nUse tabs.\r\n"
    target = _write_user_file(tmp_path, user)
    shipped = iter_skills()
    install_block(tmp_path, shipped, "0.1.0")
    once = target.read_bytes()
    assert once.count(b"\n") == once.count(b"\r\n")
    install_block(tmp_path, shipped, "0.1.0")
    assert target.read_bytes() == once
    uninstall_block(tmp_path)
    assert target.read_bytes() == user


def _skill_with_body(fixture_skills: Path, tmp_path: Path, body: str) -> Skill:
    """Make a copy of the good fixture skill with a new body.

    Parameters
    ----------
    fixture_skills : Path
        Folder that holds the fixture skills.
    tmp_path : Path
        Folder for the copy.
    body : str
        The new body text.

    Returns
    -------
    Skill
        The loaded skill.
    """
    source = (fixture_skills / "good-skill" / "SKILL.md").read_text(encoding="utf-8")
    head = source.split("---", 2)
    folder = tmp_path / "copy" / "good-skill"
    folder.mkdir(parents=True)
    path = folder / "SKILL.md"
    path.write_bytes(f"---{head[1]}---\n\n{body}\n".encode())
    return load_skill(path)


def test_render_block_rejects_marker_line(fixture_skills: Path, tmp_path: Path) -> None:
    """A body line that equals a marker is refused. A marker in a sentence is fine."""
    bad = _skill_with_body(fixture_skills, tmp_path, f"Text.\n\n{END}\n\nMore.")
    with pytest.raises(InstallError, match="marker"):
        render_block([bad], "0.1.0")
    other = tmp_path / "other"
    other.mkdir()
    fine = _skill_with_body(fixture_skills, other, f"It ends with the line `{END}`.")
    assert fine.body.strip() in render_block([fine], "0.1.0")
