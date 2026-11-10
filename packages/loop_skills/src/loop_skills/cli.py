"""Command line of loop-skills."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from . import __version__, _install
from ._agents import AGENTS
from ._install import InstallError, InstallReport
from ._skill import iter_skills

__all__ = ["main"]

version_lookup: Callable[[str], str | None] | None = None


def _agents_for(choice: str) -> list[str]:
    """Give the agent names for a value of ``--agent``.

    Parameters
    ----------
    choice : str
        An agent name or ``all``.

    Returns
    -------
    list[str]
        The agent names, in the order of ``AGENTS``.
    """
    if choice == "all":
        return list(AGENTS)
    return [choice]


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns
    -------
    argparse.ArgumentParser
        The parser with the sub commands ``install`` and ``uninstall``.
    """
    parser = argparse.ArgumentParser(
        prog="loop-skills", description="Install Loop skills for coding agents."
    )
    parser.add_argument("--version", action="version", version=f"loop-skills {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    choices = ["claude", "codex", "copilot", "all"]
    for name, text in (("install", "Install the skills."), ("uninstall", "Remove the skills.")):
        cmd = sub.add_parser(name, help=text, description=text)
        cmd.add_argument("--agent", required=True, choices=choices, help="Target agent.")
        cmd.add_argument(
            "--dir", default=".", help="Base folder of the project. A leading ~ is the home folder."
        )
        if name == "install":
            cmd.add_argument(
                "--force", action="store_true", help="Replace existing skills without a question."
            )
    return parser


def _ask(name: str) -> bool:
    """Ask the user if a skill can be replaced.

    Parameters
    ----------
    name : str
        Skill name.

    Returns
    -------
    bool
        True if the user answers ``y`` or ``yes``.
    """
    answer = input(f"Replace skill '{name}'? [y/N] ")
    return answer.strip().lower() in ("y", "yes")


def _print_report(report: InstallReport) -> None:
    """Print the outcomes and warnings of one report.

    Parameters
    ----------
    report : InstallReport
        The report to print.
    """
    for outcome in report.outcomes:
        print(f"{report.agent}: {outcome.action} {outcome.name} {outcome.detail}".rstrip())
    for text in report.warnings:
        print(f"warning: {text}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line.

    Parameters
    ----------
    argv : Sequence[str] | None
        The arguments. If None, use ``sys.argv``.

    Returns
    -------
    int
        0 for done, 1 for an install error, 3 if a skill was skipped.
        A usage error raises ``SystemExit`` with code 2.
    """
    args = _build_parser().parse_args(argv)
    base = Path(args.dir).expanduser()
    confirm = _ask if sys.stdin.isatty() and sys.stdout.isatty() else None
    reports: list[InstallReport] = []
    try:
        for agent in _agents_for(args.agent):
            if args.command == "install":
                report = _install.install(
                    agent,
                    base,
                    iter_skills(),
                    force=args.force,
                    confirm=confirm,
                    lookup=version_lookup,
                )
            else:
                report = _install.uninstall(agent, base)
            reports.append(report)
            _print_report(report)
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    skipped = sum(1 for r in reports for o in r.outcomes if o.action == "skipped")
    done = sum(len(r.outcomes) for r in reports) - skipped
    print(f"{done} skill(s) done, {skipped} skipped")
    return 3 if any(r.any_skipped for r in reports) else 0
