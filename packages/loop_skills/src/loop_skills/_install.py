"""Install and remove skills for an agent."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from . import __version__
from ._agents import AGENTS, AgentTarget
from ._pin import check_pin
from ._skill import Skill

__all__ = ["InstallError", "InstallReport", "SkillOutcome", "install", "uninstall"]

_OWNER_FILE = ".loop-skills.json"
_PACKAGE = "loop-skills"
_BLOCK_MESSAGE = "Copilot support is added in stage S3"


class InstallError(RuntimeError):
    """Raise when an install or uninstall cannot finish."""


@dataclass
class SkillOutcome:
    """Result for one skill.

    Attributes
    ----------
    name : str
        Skill name.
    action : Literal["installed", "replaced", "skipped", "removed"]
        What the installer did.
    detail : str
        Extra text for the user.
    """

    name: str
    action: Literal["installed", "replaced", "skipped", "removed"]
    detail: str = ""


@dataclass
class InstallReport:
    """Result of an install or uninstall.

    Attributes
    ----------
    agent : str
        Agent name.
    location : Path
        The target folder.
    outcomes : list[SkillOutcome]
        One outcome for each skill.
    warnings : list[str]
        Warnings for the user.
    created : list[Path]
        Folders that the installer made.
    """

    agent: str
    location: Path
    outcomes: list[SkillOutcome] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created: list[Path] = field(default_factory=list)

    @property
    def any_skipped(self) -> bool:
        """Tell if the installer skipped at least one skill.

        Returns
        -------
        bool
            True if one outcome has the action ``skipped``.
        """
        return any(item.action == "skipped" for item in self.outcomes)


def _target(agent: str) -> AgentTarget:
    """Find the target row of an agent.

    Parameters
    ----------
    agent : str
        Agent name.

    Returns
    -------
    AgentTarget
        The row for the agent.

    Raises
    ------
    InstallError
        If the agent is not known or its kind is ``block``.
    """
    try:
        row = AGENTS[agent]
    except KeyError:
        raise InstallError(f"unknown agent: {agent}") from None
    if row.kind == "block":
        raise InstallError(_BLOCK_MESSAGE)
    return row


def _remove_created(created: Sequence[Path]) -> None:
    """Remove the folders that the installer made, deepest first.

    Parameters
    ----------
    created : Sequence[Path]
        Folders that the installer made. Only empty folders are removed.
    """
    for folder in sorted(created, key=lambda item: len(item.parts), reverse=True):
        try:
            folder.rmdir()
        except OSError:
            pass


def _write_owner(folder: Path) -> None:
    """Write the owner file in a skill folder.

    Parameters
    ----------
    folder : Path
        The skill folder.
    """
    data = {"package": _PACKAGE, "version": __version__}
    (folder / _OWNER_FILE).write_text(json.dumps(data), encoding="utf-8")


def _install_one(skill: Skill, target: Path, replacing: bool) -> None:
    """Copy one skill folder to the target.

    Parameters
    ----------
    skill : Skill
        The skill to copy.
    target : Path
        The skills folder.
    replacing : bool
        True if a folder with the same name exists.

    Raises
    ------
    InstallError
        If the copy fails. The old folder is restored.
    """
    final = target / skill.name
    new = target / f".loop-skills-new-{skill.name}"
    old = target / f".loop-skills-old-{skill.name}"
    try:
        if new.exists():
            shutil.rmtree(new)
        shutil.copytree(skill.path.parent, new)
        _write_owner(new)
    except OSError as exc:
        shutil.rmtree(new, ignore_errors=True)
        raise InstallError(f"cannot copy skill {skill.name}: {exc}") from exc
    if not replacing:
        try:
            os.rename(new, final)
        except OSError as exc:
            shutil.rmtree(new, ignore_errors=True)
            raise InstallError(f"cannot install skill {skill.name}: {exc}") from exc
        return
    try:
        os.rename(final, old)
    except OSError as exc:
        shutil.rmtree(new, ignore_errors=True)
        raise InstallError(f"cannot replace skill {skill.name}: {exc}") from exc
    try:
        os.rename(new, final)
    except OSError as exc:
        shutil.rmtree(new, ignore_errors=True)
        try:
            os.rename(old, final)
        except OSError:
            pass
        raise InstallError(f"cannot replace skill {skill.name}: {exc}") from exc
    shutil.rmtree(old, ignore_errors=True)


def install(
    agent: str,
    base: Path,
    skills: Sequence[Skill],
    *,
    force: bool = False,
    confirm: Callable[[str], bool] | None = None,
    lookup: Callable[[str], str | None] | None = None,
) -> InstallReport:
    """Install skills as folders for an agent.

    Parameters
    ----------
    agent : str
        Agent name.
    base : Path
        Base folder of the project.
    skills : Sequence[Skill]
        Skills to install.
    force : bool
        Replace existing skill folders without a question.
    confirm : Callable[[str], bool] | None
        Function that tells if an existing skill can be replaced.
    lookup : Callable[[str], str | None] | None
        Function that gives the installed version of a distribution.

    Returns
    -------
    InstallReport
        The result.

    Raises
    ------
    InstallError
        If the target is not writable or a copy fails.
    """
    row = _target(agent)
    base = Path(base)
    target = base / row.relpath
    report = InstallReport(agent=agent, location=target)

    missing: list[Path] = []
    probe = target
    while not probe.exists() and probe != base and probe != probe.parent:
        missing.append(probe)
        probe = probe.parent
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.mkdir(exist_ok=True)
        test = target / ".loop-skills-write-test"
        test.mkdir()
        test.rmdir()
    except OSError as exc:
        _remove_created(missing)
        raise InstallError(f"cannot write to {target}: {exc}. Nothing changed.") from exc
    report.created.extend(missing)

    for skill in sorted(skills, key=lambda item: item.name):
        result = check_pin(skill.requires, lookup)
        if result.status != "ok":
            report.warnings.append(result.message)
        exists = (target / skill.name).exists()
        if exists and not (force or (confirm is not None and confirm(skill.name))):
            report.outcomes.append(SkillOutcome(skill.name, "skipped", "exists; use --force"))
            continue
        _install_one(skill, target, exists)
        report.outcomes.append(SkillOutcome(skill.name, "replaced" if exists else "installed"))
    return report


def _owned(folder: Path) -> bool:
    """Tell if a folder has a valid owner file of this package.

    Parameters
    ----------
    folder : Path
        The folder to check.

    Returns
    -------
    bool
        True if the owner file is valid and names this package.
    """
    try:
        data = json.loads((folder / _OWNER_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("package") == _PACKAGE


def uninstall(agent: str, base: Path) -> InstallReport:
    """Remove the skill folders that this package installed.

    Parameters
    ----------
    agent : str
        Agent name.
    base : Path
        Base folder of the project.

    Returns
    -------
    InstallReport
        The result. It is empty if the target is missing.

    Raises
    ------
    InstallError
        If a folder cannot be removed.
    """
    row = _target(agent)
    base = Path(base)
    target = base / row.relpath
    report = InstallReport(agent=agent, location=target)
    if not target.is_dir():
        return report
    for folder in sorted(target.iterdir(), key=lambda item: item.name):
        if folder.is_dir() and _owned(folder):
            try:
                shutil.rmtree(folder)
            except OSError as exc:
                raise InstallError(f"cannot remove {folder}: {exc}") from exc
            report.outcomes.append(SkillOutcome(folder.name, "removed"))
    current = target
    while current != base and current != current.parent:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent
    return report
