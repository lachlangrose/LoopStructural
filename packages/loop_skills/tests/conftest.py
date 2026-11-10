"""Shared fixtures for the loop_skills tests."""

from __future__ import annotations

import shutil
import socket
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "skills"


class FakeLookup:
    """Fake version lookup that reads a dict.

    Attributes
    ----------
    versions : dict
        Map from distribution name to version string.
    """

    def __init__(self) -> None:
        """Create a lookup with no versions."""
        self.versions: dict[str, str] = {}

    def __call__(self, dist: str) -> str | None:
        """Return the version of a distribution.

        Parameters
        ----------
        dist : str
            Distribution name.

        Returns
        -------
        str | None
            The version, or None if the name is not in the dict.
        """
        return self.versions.get(dist)


@pytest.fixture
def fixture_skills(tmp_path: Path) -> Path:
    """Copy the fixture skills to a temporary directory.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.

    Returns
    -------
    Path
        The copied skills directory.
    """
    dest = tmp_path / "skills"
    shutil.copytree(FIXTURES_DIR, dest)
    return dest


@pytest.fixture
def fake_lookup() -> FakeLookup:
    """Return a fake version lookup.

    Returns
    -------
    FakeLookup
        Callable. Set `versions` to control the result.
    """
    return FakeLookup()


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any socket creation raise an error.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest monkeypatch fixture.
    """

    def _blocked(*args: object, **kwargs: object) -> None:
        """Raise an error for every network call.

        Parameters
        ----------
        *args : object
            Ignored.
        **kwargs : object
            Ignored.
        """
        raise RuntimeError("network call")

    monkeypatch.setattr(socket, "socket", _blocked)
