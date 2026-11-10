"""Tests for the version pin check.

Spec 007-loop-skills, scenarios 3, 4 and 11. The check reads the pin
string of a distribution and compares it with the installed version.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loop_skills._pin import PinResult, check_pin

if TYPE_CHECKING:
    from .conftest import FakeLookup


def test_pin_ok_inside_range(fake_lookup: FakeLookup) -> None:
    """A version inside the pin range gives status ``ok``.

    Parameters
    ----------
    fake_lookup : FakeLookup
        Fake version lookup from conftest.
    """
    fake_lookup.versions = {"LoopStructural": "1.11.0"}
    result: PinResult = check_pin("LoopStructural>=1.11,<2", fake_lookup)
    assert result.status == "ok"


def test_pin_outside_range_names_both_versions(fake_lookup: FakeLookup) -> None:
    """A version outside the pin range gives status ``outside``.

    The message must name the pin and the installed version.

    Parameters
    ----------
    fake_lookup : FakeLookup
        Fake version lookup from conftest.
    """
    fake_lookup.versions = {"LoopStructural": "2.0.0"}
    result: PinResult = check_pin("LoopStructural>=1.11,<2", fake_lookup)
    assert result.status == "outside"
    assert "LoopStructural>=1.11,<2" in result.message
    assert "2.0.0" in result.message


def test_pin_missing_gives_install_hint(fake_lookup: FakeLookup) -> None:
    """A distribution that is not installed gives status ``missing``.

    The message must contain the install command for the pin.

    Parameters
    ----------
    fake_lookup : FakeLookup
        Fake version lookup from conftest.
    """
    fake_lookup.versions = {}
    result: PinResult = check_pin("LoopStructural>=1.11,<2", fake_lookup)
    assert result.status == "missing"
    assert "pip install 'LoopStructural>=1.11,<2'" in result.message


def test_pin_allows_pre_release(fake_lookup: FakeLookup) -> None:
    """A pre-release inside the range gives status ``ok``.

    Parameters
    ----------
    fake_lookup : FakeLookup
        Fake version lookup from conftest.
    """
    fake_lookup.versions = {"LoopStructural": "1.12.0.dev3"}
    result: PinResult = check_pin("LoopStructural>=1.11,<2", fake_lookup)
    assert result.status == "ok"


def test_pin_result_fields(fake_lookup: FakeLookup) -> None:
    """The result names the distribution and the installed version.

    Parameters
    ----------
    fake_lookup : FakeLookup
        Fake version lookup from conftest.
    """
    fake_lookup.versions = {"LoopStructural": "1.11.0"}
    result: PinResult = check_pin("LoopStructural>=1.11,<2", fake_lookup)
    assert result.distribution == "LoopStructural"
    assert result.installed == "1.11.0"


def test_pin_name_with_hyphen(fake_lookup: FakeLookup) -> None:
    """A distribution name with a hyphen is parsed and checked.

    Parameters
    ----------
    fake_lookup : FakeLookup
        Fake version lookup from conftest.
    """
    fake_lookup.versions = {"loop-skills": "0.1.0"}
    result: PinResult = check_pin("loop-skills>=0.1,<1", fake_lookup)
    assert result.status == "ok"
    assert result.distribution == "loop-skills"
