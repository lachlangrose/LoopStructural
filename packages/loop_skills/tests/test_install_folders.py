"""Tests for the folder install and uninstall of skills (Claude Code and Codex)."""

from __future__ import annotations

import json
import os
import pathlib
from collections.abc import Callable
from pathlib import Path

import pytest
from loop_skills._install import InstallError, install, uninstall
from loop_skills._skill import Skill, load_skill

AGENTS = [
    pytest.param("claude", id="claude"),
    pytest.param("codex", id="codex"),
]

TARGETS = {"claude": Path(".claude") / "skills", "codex": Path(".agents") / "skills"}

PINNED_TEXT = """---
name: pinned-skill
description: A fixture skill with a version pin.
requires: LoopStructural>=1.11,<2
---

# Pinned skill

Short body.
"""


@pytest.fixture
def good(fixture_skills: Path) -> Skill:
    """Load the good fixture skill.

    Parameters
    ----------
    fixture_skills : Path
        Copy of the fixture skills.

    Returns
    -------
    Skill
        The good fixture skill.
    """
    return load_skill(fixture_skills / "good-skill" / "SKILL.md")


@pytest.fixture
def pinned(tmp_path: Path) -> Skill:
    """Load a skill that has the pin `LoopStructural>=1.11,<2`.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.

    Returns
    -------
    Skill
        The pinned skill.
    """
    folder = tmp_path / "src" / "pinned-skill"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(PINNED_TEXT, encoding="utf-8")
    return load_skill(folder / "SKILL.md")


@pytest.fixture
def base(tmp_path: Path) -> Path:
    """Make the empty base folder of the project.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.

    Returns
    -------
    Path
        The base folder.
    """
    path = tmp_path / "proj"
    path.mkdir()
    return path


def _listing(root: Path) -> list[str]:
    """List all paths under a folder, relative to it.

    Parameters
    ----------
    root : Path
        The folder to list.

    Returns
    -------
    list[str]
        Sorted relative paths in POSIX form.
    """
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


def _outcome(report: object, name: str) -> str:
    """Get the action of the outcome for one skill.

    Parameters
    ----------
    report : object
        An `InstallReport`.
    name : str
        The skill name.

    Returns
    -------
    str
        The action of the outcome.
    """
    for item in report.outcomes:  # type: ignore[attr-defined]
        if item.name == name:
            return item.action
    raise AssertionError(f"no outcome for {name}")


@pytest.mark.parametrize("agent", AGENTS)
def test_install_empty_base(agent: str, base: Path, good: Skill) -> None:
    """Install in an empty base makes the folder, the file and the owner file.

    Parameters
    ----------
    agent : str
        Agent name.
    base : Path
        The base folder.
    good : Skill
        The good fixture skill.
    """
    target = base / TARGETS[agent]
    report = install(agent, base, [good])
    skill_dir = target / "good-skill"
    assert (skill_dir / "SKILL.md").is_file()
    owner = json.loads((skill_dir / ".loop-skills.json").read_text(encoding="utf-8"))
    assert owner["package"] == "loop-skills"
    assert isinstance(owner["version"], str)
    assert target.is_dir()
    assert target in report.created
    assert _outcome(report, "good-skill") == "installed"


@pytest.mark.parametrize("agent", AGENTS)
def test_pin_outside_range_warns(agent: str, base: Path, pinned: Skill) -> None:
    """A version outside the pin gives one warning and the skill is installed.

    Parameters
    ----------
    agent : str
        Agent name.
    base : Path
        The base folder.
    pinned : Skill
        The pinned skill.
    """
    report = install(agent, base, [pinned], lookup=lambda d: "2.0.0")
    assert len(report.warnings) == 1
    assert "LoopStructural>=1.11,<2" in report.warnings[0]
    assert "2.0.0" in report.warnings[0]
    assert (base / TARGETS[agent] / "pinned-skill" / "SKILL.md").is_file()


@pytest.mark.parametrize("agent", AGENTS)
def test_pin_not_installed_warns(agent: str, base: Path, pinned: Skill) -> None:
    """A library that is not installed gives a warning with `pip install`.

    Parameters
    ----------
    agent : str
        Agent name.
    base : Path
        The base folder.
    pinned : Skill
        The pinned skill.
    """
    report = install(agent, base, [pinned], lookup=lambda d: None)
    assert any("pip install" in w for w in report.warnings)
    assert (base / TARGETS[agent] / "pinned-skill" / "SKILL.md").is_file()


@pytest.mark.parametrize("agent", AGENTS)
def test_existing_skipped_without_confirm(agent: str, base: Path, good: Skill) -> None:
    """An existing skill is skipped when there is no confirm function.

    Parameters
    ----------
    agent : str
        Agent name.
    base : Path
        The base folder.
    good : Skill
        The good fixture skill.
    """
    install(agent, base, [good])
    skill_file = base / TARGETS[agent] / "good-skill" / "SKILL.md"
    skill_file.write_text("changed", encoding="utf-8")
    report = install(agent, base, [good], confirm=None)
    assert _outcome(report, "good-skill") == "skipped"
    assert skill_file.read_text(encoding="utf-8") == "changed"
    assert report.any_skipped


@pytest.mark.parametrize("agent", AGENTS)
@pytest.mark.parametrize(
    ("confirm", "force", "expected"),
    [
        (lambda n: True, False, "replaced"),
        (lambda n: False, False, "skipped"),
        (None, True, "replaced"),
    ],
    ids=["confirm-yes", "confirm-no", "force"],
)
def test_existing_with_confirm_or_force(
    agent: str,
    base: Path,
    good: Skill,
    confirm: Callable[[str], bool] | None,
    force: bool,
    expected: str,
) -> None:
    """An existing skill follows the confirm answer or the force flag.

    Parameters
    ----------
    agent : str
        Agent name.
    base : Path
        The base folder.
    good : Skill
        The good fixture skill.
    confirm : Callable[[str], bool] | None
        The confirm function.
    force : bool
        The force flag.
    expected : str
        The expected action.
    """
    install(agent, base, [good])
    skill_file = base / TARGETS[agent] / "good-skill" / "SKILL.md"
    skill_file.write_text("changed", encoding="utf-8")
    report = install(agent, base, [good], force=force, confirm=confirm)
    assert _outcome(report, "good-skill") == expected
    if expected == "replaced":
        assert skill_file.read_text(encoding="utf-8") == good.path.read_text(encoding="utf-8")
    else:
        assert skill_file.read_text(encoding="utf-8") == "changed"


@pytest.mark.parametrize("agent", AGENTS)
def test_uninstall_only_owned(agent: str, base: Path, good: Skill) -> None:
    """Uninstall removes only folders that have the owner file.

    Parameters
    ----------
    agent : str
        Agent name.
    base : Path
        The base folder.
    good : Skill
        The good fixture skill.
    """
    install(agent, base, [good])
    target = base / TARGETS[agent]
    other = target / "other-skill"
    other.mkdir()
    (other / "SKILL.md").write_text("mine", encoding="utf-8")
    report = uninstall(agent, base)
    assert not (target / "good-skill").exists()
    assert (other / "SKILL.md").is_file()
    assert _outcome(report, "good-skill") == "removed"


@pytest.mark.parametrize("agent", AGENTS)
def test_write_failure_leaves_nothing(
    agent: str, base: Path, good: Skill, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed rename gives `InstallError` and leaves no temporary folder.

    Parameters
    ----------
    agent : str
        Agent name.
    base : Path
        The base folder.
    good : Skill
        The good fixture skill.
    monkeypatch : pytest.MonkeyPatch
        Pytest monkeypatch fixture.
    """
    real_rename = os.rename
    calls: list[int] = []

    def _raise_once(src: object, dst: object, *args: object, **kwargs: object) -> None:
        """Raise `OSError` on the first call, then rename as normal.

        Parameters
        ----------
        src : object
            Source path.
        dst : object
            Destination path.
        *args : object
            Extra arguments.
        **kwargs : object
            Extra keyword arguments.
        """
        if not calls:
            calls.append(1)
            raise OSError("boom")
        real_rename(src, dst, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("loop_skills._install.os.rename", _raise_once)
    with pytest.raises(InstallError):
        install(agent, base, [good])
    names = [p.name for p in base.rglob("*")]
    assert not any(n.startswith((".loop-skills-new-", ".loop-skills-old-")) for n in names)
    assert "good-skill" not in names


@pytest.mark.parametrize("agent", AGENTS)
def test_unwritable_target(
    agent: str, base: Path, good: Skill, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unwritable target gives `InstallError` with `Nothing changed`.

    Parameters
    ----------
    agent : str
        Agent name.
    base : Path
        The base folder.
    good : Skill
        The good fixture skill.
    monkeypatch : pytest.MonkeyPatch
        Pytest monkeypatch fixture.
    """
    real_mkdir = pathlib.Path.mkdir
    target = base / TARGETS[agent]

    def _deny(self: Path, *args: object, **kwargs: object) -> None:
        """Raise `PermissionError` for the target folder.

        Parameters
        ----------
        self : Path
            The path to make.
        *args : object
            Extra arguments.
        **kwargs : object
            Extra keyword arguments.
        """
        if self == target:
            raise PermissionError("denied")
        real_mkdir(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pathlib.Path, "mkdir", _deny)
    with pytest.raises(InstallError, match="Nothing changed"):
        install(agent, base, [good])
    assert _listing(base) == [p for p in _listing(base) if not p.endswith("good-skill")]
    assert not target.exists()


@pytest.mark.parametrize("agent", AGENTS)
def test_install_then_uninstall_restores_listing(agent: str, base: Path, good: Skill) -> None:
    """Install then uninstall leaves the base as it was.

    Parameters
    ----------
    agent : str
        Agent name.
    base : Path
        The base folder.
    good : Skill
        The good fixture skill.
    """
    (base / "keep.txt").write_text("keep", encoding="utf-8")
    before = _listing(base)
    install(agent, base, [good])
    uninstall(agent, base)
    assert _listing(base) == before
