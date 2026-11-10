"""Tests that install, uninstall and the checks make no network call."""

from __future__ import annotations

from pathlib import Path

from loop_skills._check import check_names, check_syntax
from loop_skills._install import install, uninstall
from loop_skills._skill import load_skill


def test_install_uninstall_and_checks_run_offline(
    fixture_skills: Path,
    no_network: None,
    tmp_path: Path,
) -> None:
    """Run install, uninstall and the checks with all sockets blocked.

    The fixture ``no_network`` makes any socket creation raise an error.
    The test passes when no exception is raised.

    Parameters
    ----------
    fixture_skills : Path
        Folder that holds a copy of the fixture skills.
    no_network : None
        Fixture that blocks network calls.
    tmp_path : Path
        Pytest temporary directory.
    """
    # Load the good fixture skill. No network is used.
    skill = load_skill(fixture_skills / "good-skill" / "SKILL.md")

    # Install and uninstall the skill in a project folder.
    project = tmp_path / "p"
    install("claude", project, [skill], lookup=lambda d: "1.0")
    uninstall("claude", project)

    # Run the checks. They must not reach the network.
    check_syntax(skill)
    check_names(skill, roots=("json",), lookup=lambda d: "1.0")
