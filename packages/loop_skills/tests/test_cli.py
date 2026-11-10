"""Tests for the loop_skills command line."""

from __future__ import annotations

import builtins
import sys
from pathlib import Path

import pytest
from loop_skills._copilot import BEGIN, END
from loop_skills._skill import Skill, load_skill
from loop_skills.cli import main

from .conftest import FakeLookup


@pytest.fixture
def cli_env(
    monkeypatch: pytest.MonkeyPatch,
    fixture_skills: Path,
    fake_lookup: FakeLookup,
) -> list[Skill]:
    """Patch the skill source and the version lookup of the CLI.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest monkeypatch fixture.
    fixture_skills : Path
        Folder with the fixture skills.
    fake_lookup : FakeLookup
        Fake version lookup.

    Returns
    -------
    list[Skill]
        The skills that the CLI sees.
    """
    fake_lookup.versions = {"json": "1.0"}
    skills = [load_skill(fixture_skills / "good-skill" / "SKILL.md")]
    monkeypatch.setattr("loop_skills.cli.iter_skills", lambda: skills)
    monkeypatch.setattr("loop_skills.cli.version_lookup", fake_lookup)
    return skills


def _set_tty(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    """Make stdin and stdout report a terminal or no terminal.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest monkeypatch fixture.
    value : bool
        The result of `isatty` for stdin and stdout.
    """
    monkeypatch.setattr(sys.stdin, "isatty", lambda: value, raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: value, raising=False)


def _skill_dirs(target: Path) -> list[Path]:
    """Find the installed folders of the good skill.

    Parameters
    ----------
    target : Path
        The target folder of the install.

    Returns
    -------
    list[Path]
        The folders named `good-skill` under the target.
    """
    return [p for p in target.rglob("good-skill") if p.is_dir()]


def test_install_claude(cli_env: list[Skill], tmp_path: Path) -> None:
    """Install for Claude Code returns 0 and makes the skill folder."""
    target = tmp_path / "target"
    target.mkdir()
    code = main(["install", "--agent", "claude", "--dir", str(target)])
    assert code == 0
    assert _skill_dirs(target)


def test_install_codex(cli_env: list[Skill], tmp_path: Path) -> None:
    """Install for Codex returns 0 and makes the skill folder."""
    target = tmp_path / "target"
    target.mkdir()
    code = main(["install", "--agent", "codex", "--dir", str(target)])
    assert code == 0
    assert _skill_dirs(target)


def test_second_install_without_terminal_skips(
    cli_env: list[Skill],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A second install with no terminal skips the skill and returns 3."""
    target = tmp_path / "target"
    target.mkdir()
    assert main(["install", "--agent", "claude", "--dir", str(target)]) == 0
    capsys.readouterr()
    _set_tty(monkeypatch, False)
    code = main(["install", "--agent", "claude", "--dir", str(target)])
    out = capsys.readouterr()
    text = out.out + out.err
    assert code == 3
    assert "good-skill" in text
    assert "skipped" in text


def test_force_install_replaces(
    cli_env: list[Skill],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Install with --force returns 0 when the skill exists."""
    target = tmp_path / "target"
    target.mkdir()
    assert main(["install", "--agent", "claude", "--dir", str(target)]) == 0
    _set_tty(monkeypatch, False)
    code = main(["install", "--agent", "claude", "--force", "--dir", str(target)])
    assert code == 0


def test_install_error_returns_1(
    cli_env: list[Skill],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An InstallError gives exit code 1 and the message in the output."""
    from loop_skills._install import InstallError

    def _boom(*args: object, **kwargs: object) -> None:
        """Raise an InstallError.

        Parameters
        ----------
        *args : object
            Ignored.
        **kwargs : object
            Ignored.
        """
        raise InstallError("boom")

    monkeypatch.setattr("loop_skills._install.install", _boom)
    code = main(["install", "--agent", "claude", "--dir", str(tmp_path)])
    out = capsys.readouterr()
    assert code == 1
    assert "boom" in out.out + out.err


def test_missing_agent_is_usage_error(cli_env: list[Skill]) -> None:
    """A missing --agent gives SystemExit with code 2."""
    with pytest.raises(SystemExit) as info:
        main(["install"])
    assert info.value.code == 2


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    """--version prints the version and exits with code 0."""
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    out = capsys.readouterr()
    assert "loop-skills" in out.out + out.err


def test_existing_skill_replaced_with_terminal(
    cli_env: list[Skill],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a terminal and answer y, an existing skill is replaced."""
    target = tmp_path / "target"
    target.mkdir()
    assert main(["install", "--agent", "claude", "--dir", str(target)]) == 0
    _set_tty(monkeypatch, True)
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "y")
    code = main(["install", "--agent", "claude", "--dir", str(target)])
    assert code == 0
    assert _skill_dirs(target)


def test_uninstall_claude(cli_env: list[Skill], tmp_path: Path) -> None:
    """Uninstall returns 0 and removes the skill folder."""
    target = tmp_path / "target"
    target.mkdir()
    assert main(["install", "--agent", "claude", "--dir", str(target)]) == 0
    assert _skill_dirs(target)
    code = main(["uninstall", "--agent", "claude", "--dir", str(target)])
    assert code == 0
    assert not _skill_dirs(target)


def _copilot_file(target: Path) -> Path:
    """Return the path of the Copilot instructions file.

    Parameters
    ----------
    target : Path
        The target folder of the install.

    Returns
    -------
    Path
        The path of ``.github/copilot-instructions.md`` below the target.
    """
    return target / ".github" / "copilot-instructions.md"


def test_install_copilot(cli_env: list[Skill], tmp_path: Path) -> None:
    """Install for Copilot returns 0 and writes the managed block."""
    target = tmp_path / "target"
    target.mkdir()
    code = main(["install", "--agent", "copilot", "--dir", str(target)])
    assert code == 0
    text = _copilot_file(target).read_text(encoding="utf-8")
    assert BEGIN in text
    assert END in text


def test_install_all_agents_includes_copilot(cli_env: list[Skill], tmp_path: Path) -> None:
    """Install for all agents returns 0 and writes every target."""
    target = tmp_path / "target"
    target.mkdir()
    code = main(["install", "--agent", "all", "--dir", str(target)])
    assert code == 0
    assert (target / ".claude" / "skills" / "good-skill").is_dir()
    assert (target / ".agents" / "skills" / "good-skill").is_dir()
    text = _copilot_file(target).read_text(encoding="utf-8")
    assert BEGIN in text
    assert END in text


def test_uninstall_all_agents_removes_copilot_block(
    cli_env: list[Skill],
    tmp_path: Path,
) -> None:
    """Uninstall for all agents removes the skill folders and the Copilot block."""
    target = tmp_path / "target"
    target.mkdir()
    assert main(["install", "--agent", "all", "--dir", str(target)]) == 0
    code = main(["uninstall", "--agent", "all", "--dir", str(target)])
    assert code == 0
    assert not (target / ".claude" / "skills" / "good-skill").exists()
    assert not (target / ".agents" / "skills" / "good-skill").exists()
    copilot = _copilot_file(target)
    assert copilot.exists()
    assert BEGIN not in copilot.read_text(encoding="utf-8")


def test_damaged_copilot_marker_returns_1(
    cli_env: list[Skill],
    tmp_path: Path,
) -> None:
    """A Copilot file with a begin marker and no end marker gives exit code 1."""
    target = tmp_path / "target"
    copilot = _copilot_file(target)
    copilot.parent.mkdir(parents=True)
    original = f"# Notes\n\n{BEGIN}\n"
    copilot.write_text(original, encoding="utf-8", newline="")
    code = main(["install", "--agent", "copilot", "--dir", str(target)])
    assert code == 1
    assert copilot.read_text(encoding="utf-8") == original


def _tilde_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, Path]:
    """Set a temporary home folder and a different working folder.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest monkeypatch fixture.
    tmp_path : Path
        Temporary folder of the test.

    Returns
    -------
    tuple[Path, Path]
        The home folder and the working folder.
    """
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    # Path.expanduser reads HOME on POSIX and USERPROFILE on Windows.
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(work)
    return home, work


def test_dir_tilde_is_expanded(
    cli_env: list[Skill],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A leading ~ in --dir is the home folder, as PowerShell does not expand it."""
    home, work = _tilde_env(monkeypatch, tmp_path)
    code = main(["install", "--agent", "claude", "--dir", "~"])
    assert code == 0
    assert (home / ".claude" / "skills" / "good-skill").is_dir()
    assert not (work / "~").exists()


def test_dir_tilde_subfolder_is_expanded(
    cli_env: list[Skill],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A leading ~/ in --dir is expanded to a subfolder of the home folder."""
    home, work = _tilde_env(monkeypatch, tmp_path)
    (home / "proj").mkdir()
    code = main(["install", "--agent", "claude", "--dir", "~/proj"])
    assert code == 0
    assert (home / "proj" / ".claude" / "skills" / "good-skill").is_dir()
    assert not (work / "~").exists()
