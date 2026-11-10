"""Write skills as a managed block in the Copilot instructions file."""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path

from ._install import InstallError, InstallReport, SkillOutcome
from ._pin import check_pin
from ._skill import Skill

__all__ = ["BEGIN", "END", "install_block", "render_block", "uninstall_block"]

BEGIN = "<!-- loop-skills:begin -->"
END = "<!-- loop-skills:end -->"

# A marker counts only when it is the whole line. Text that quotes a marker
# inside a sentence is not a marker.
_BEGIN_RE = re.compile("^" + re.escape(BEGIN) + r"[ \t]*(?=\r?$)", re.MULTILINE)
_END_RE = re.compile("^" + re.escape(END) + r"[ \t]*(?=\r?$)", re.MULTILINE)


def render_block(skills: Sequence[Skill], version: str, newline: str = "\n") -> str:
    """Render the managed block.

    Parameters
    ----------
    skills : Sequence[Skill]
        Skills to write, in the given order.
    version : str
        Version of this package.
    newline : str
        Line end for every line of the block.

    Returns
    -------
    str
        The block, from the begin marker to the end marker. It has no final
        line end.
    """
    lines = [
        BEGIN,
        f"<!-- Managed by loop-skills {version}. Change text outside these markers only. -->",
        "",
    ]
    for skill in skills:
        for line in [*skill.description.splitlines(), *skill.body.splitlines()]:
            if line.strip() in (BEGIN, END):
                raise InstallError(f"skill {skill.name} has a line that equals a marker line")
        lines.append(f"## Skill: {skill.name}")
        lines.append("")
        lines.extend(skill.description.splitlines())
        lines.append("")
        lines.extend(skill.body.strip("\r\n").strip().splitlines())
        lines.append("")
    lines.append(END)
    return newline.join(lines)


def _path(base: Path) -> Path:
    """Return the path of the Copilot file.

    Parameters
    ----------
    base : Path
        Base folder of the project.

    Returns
    -------
    Path
        Path of ``.github/copilot-instructions.md`` below the base folder.
    """
    return Path(base) / ".github" / "copilot-instructions.md"


def _read(path: Path) -> str:
    """Read a file without a change of the line ends.

    Parameters
    ----------
    path : Path
        The file to read.

    Returns
    -------
    str
        The text, or an empty text if the file is missing.
    """
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read()
    except FileNotFoundError:
        return ""


def _write(path: Path, text: str) -> None:
    """Write a file through a temporary file.

    Parameters
    ----------
    path : Path
        The file to write.
    text : str
        The text. The line ends are written as they are.

    Raises
    ------
    InstallError
        If the write fails.
    """
    temp = path.with_name(path.name + ".loop-skills-tmp")
    try:
        with open(temp, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temp, path)
    except OSError as exc:
        try:
            temp.unlink()
        except OSError:
            pass
        raise InstallError(f"cannot write {path}: {exc}. Nothing changed.") from exc


def _marker_stop(match: re.Match[str]) -> int:
    """Return the end of the marker text of a match.

    Parameters
    ----------
    match : re.Match[str]
        A match of the end marker pattern.

    Returns
    -------
    int
        Index after the marker text. Spaces and tabs after the marker are
        part of the replaced range. The line end is not.
    """
    return match.end()


def install_block(base: Path, skills: Sequence[Skill], version: str) -> InstallReport:
    """Write or replace the managed block.

    Parameters
    ----------
    base : Path
        Base folder of the project.
    skills : Sequence[Skill]
        Skills to write.
    version : str
        Version of this package.

    Returns
    -------
    InstallReport
        The result.

    Raises
    ------
    InstallError
        If the markers are damaged or the write fails.
    """
    path = _path(base)
    report = InstallReport(agent="copilot", location=path)
    try:
        text = _read(path)
    except OSError as exc:
        raise InstallError(f"cannot read {path}: {exc}. Nothing changed.") from exc
    newline = "\r\n" if "\r\n" in text else "\n"
    block = render_block(skills, version, newline)

    begin_match = _BEGIN_RE.search(text)
    if begin_match:
        end_match = _END_RE.search(text, begin_match.end())
    else:
        end_match = _END_RE.search(text)
    if begin_match and end_match:
        new_text = text[: begin_match.start()] + block + text[_marker_stop(end_match) :]
        action = "replaced"
    elif begin_match or end_match:
        raise InstallError(f"the markers in {path} are damaged. Nothing changed.")
    else:
        new_text = text
        if text and not text.endswith(newline * 2):
            new_text += newline
        new_text += block + newline
        action = "installed"

    folder = path.parent
    made: list[Path] = []
    if not folder.exists():
        try:
            folder.mkdir(parents=True)
        except OSError as exc:
            raise InstallError(f"cannot write to {folder}: {exc}. Nothing changed.") from exc
        made.append(folder)
    if not path.exists():
        made.append(path)
    try:
        _write(path, new_text)
    except InstallError:
        if folder in made:
            try:
                folder.rmdir()
            except OSError:
                pass
        raise
    report.created.extend(made)

    for skill in skills:
        result = check_pin(skill.requires)
        if result.status != "ok":
            report.warnings.append(result.message)
        report.outcomes.append(SkillOutcome(skill.name, action))
    return report


def uninstall_block(base: Path) -> InstallReport:
    """Remove the managed block and keep the file.

    Parameters
    ----------
    base : Path
        Base folder of the project.

    Returns
    -------
    InstallReport
        The result. It is empty if the file or the markers are missing.

    Raises
    ------
    InstallError
        If the write fails.
    """
    path = _path(base)
    report = InstallReport(agent="copilot", location=path)
    try:
        text = _read(path)
    except OSError as exc:
        raise InstallError(f"cannot read {path}: {exc}. Nothing changed.") from exc
    begin_match = _BEGIN_RE.search(text)
    end_match = _END_RE.search(text, begin_match.end()) if begin_match else None
    if not begin_match or not end_match:
        return report
    begin = begin_match.start()
    newline = "\r\n" if "\r\n" in text else "\n"
    stop = _marker_stop(end_match)
    if text.startswith(newline, stop):
        stop += len(newline)
    start = begin
    if text[:start].endswith(newline * 2):
        start -= len(newline)
    _write(path, text[:start] + text[stop:])
    report.outcomes.append(SkillOutcome("copilot-block", "removed"))
    return report
