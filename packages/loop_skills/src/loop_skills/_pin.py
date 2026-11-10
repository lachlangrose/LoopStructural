"""Version pin check for a skill.

A skill names the distribution that it needs, for example
``LoopStructural>=1.11,<2``. This module compares that pin with the
installed version.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from typing import Callable, Literal

from packaging.requirements import Requirement

__all__ = ["PinResult", "check_pin"]


@dataclass(frozen=True)
class PinResult:
    """Result of a version pin check.

    Attributes
    ----------
    requirement : str
        The pin string that was checked.
    distribution : str
        The distribution name, as written in the pin.
    installed : str | None
        The installed version, or ``None`` if the distribution is missing.
    status : Literal["ok", "outside", "missing"]
        ``ok`` if the version is in the range, ``outside`` if it is not,
        ``missing`` if the distribution is not installed.
    message : str
        A text for the user that explains the status.
    """

    requirement: str
    distribution: str
    installed: str | None
    status: Literal["ok", "outside", "missing"]
    message: str


def _default_lookup(dist: str) -> str | None:
    """Get the installed version of a distribution.

    Parameters
    ----------
    dist : str
        The distribution name.

    Returns
    -------
    str | None
        The installed version, or ``None`` if the distribution is not
        installed.
    """
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return None


def check_pin(
    requires: str,
    lookup: Callable[[str], str | None] | None = None,
) -> PinResult:
    """Compare the installed version of a distribution with a pin.

    Parameters
    ----------
    requires : str
        The pin, for example ``"LoopStructural>=1.11,<2"``.
    lookup : Callable[[str], str | None] | None
        A function that gives the installed version of a distribution, or
        ``None`` if it is not installed. The default uses
        ``importlib.metadata``.

    Returns
    -------
    PinResult
        The result of the check.
    """
    req = Requirement(requires)
    dist = req.name
    find = lookup if lookup is not None else _default_lookup
    installed = find(dist)

    if installed is None:
        return PinResult(
            requirement=requires,
            distribution=dist,
            installed=None,
            status="missing",
            message=f"{dist} is not installed. Install it with: pip install '{requires}'",
        )
    if req.specifier.contains(installed, prereleases=True):
        return PinResult(
            requirement=requires,
            distribution=dist,
            installed=installed,
            status="ok",
            message=f"{dist} {installed} satisfies '{requires}'",
        )
    return PinResult(
        requirement=requires,
        distribution=dist,
        installed=installed,
        status="outside",
        message=f"{dist} {installed} is outside the pin '{requires}' of this skill",
    )
