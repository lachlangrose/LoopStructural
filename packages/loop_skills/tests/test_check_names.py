"""Tests for the check_names step of loop_skills (spec 007, FR-013).

The tests use the fixture skills and small skills made in a temporary
folder. They do not need any heavy package, because the version lookup
is a fake and the root distribution is ``json``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loop_skills._check import NameReport, check_names
from loop_skills._skill import Skill, load_skill

if TYPE_CHECKING:
    from .conftest import FakeLookup

FENCE = "`" * 3
ROOTS = ("json",)


def _make_skill(
    base: Path,
    name: str,
    requires: str,
    code: str,
) -> Skill:
    """Write a skill folder with one python block and load it.

    Parameters
    ----------
    base : Path
        Folder that holds the new skill folder.
    name : str
        Skill name. It is also the folder name.
    requires : str
        Pin for the ``requires`` frontmatter key.
    code : str
        Source code for the python block of the body.

    Returns
    -------
    Skill
        The loaded skill.
    """
    folder = base / name
    folder.mkdir(parents=True)
    text = (
        "---\n"
        f"name: {name}\n"
        "description: Test skill for check_names.\n"
        f"requires: {requires}\n"
        "---\n"
        "\n"
        f"{FENCE}python\n"
        f"{code}"
        f"{FENCE}\n"
    )
    (folder / "SKILL.md").write_text(text, encoding="utf-8")
    return load_skill(folder / "SKILL.md")


def test_good_skill_has_no_problem(fixture_skills: Path, fake_lookup: FakeLookup) -> None:
    """A correct skill gives status checked and no problem.

    Parameters
    ----------
    fixture_skills : Path
        Copy of the fixture skills.
    fake_lookup : FakeLookup
        Fake version lookup.
    """
    fake_lookup.versions = {"json": "1.0"}
    skill = load_skill(fixture_skills / "good-skill" / "SKILL.md")
    report: NameReport = check_names(skill, roots=ROOTS, lookup=fake_lookup)
    assert report.status == "checked"
    assert report.problems == []
    assert report.checked >= 1


def test_bad_name_skill_gives_two_problems(fixture_skills: Path, fake_lookup: FakeLookup) -> None:
    """A skill with two wrong names gives two name problems.

    Parameters
    ----------
    fixture_skills : Path
        Copy of the fixture skills.
    fake_lookup : FakeLookup
        Fake version lookup.
    """
    fake_lookup.versions = {"json": "1.0"}
    skill = load_skill(fixture_skills / "bad-name" / "SKILL.md")
    report: NameReport = check_names(skill, roots=ROOTS, lookup=fake_lookup)
    assert len(report.problems) == 2
    assert all(p.kind == "name" for p in report.problems)
    details = " ".join(p.detail for p in report.problems)
    assert "not_a_function" in details
    assert "NotAName" in details


def test_block_import_and_method_call_is_ok(tmp_path: Path, fake_lookup: FakeLookup) -> None:
    """A method call on an object from a real json name gives no problem.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.
    fake_lookup : FakeLookup
        Fake version lookup.
    """
    fake_lookup.versions = {"json": "1.0"}
    code = "import json\nd = json.JSONDecoder()\nd.decode('1')\n"
    skill = _make_skill(tmp_path, "ok-method", "json>=0", code)
    report: NameReport = check_names(skill, roots=ROOTS, lookup=fake_lookup)
    assert report.problems == []


def test_unknown_method_call_is_a_problem(tmp_path: Path, fake_lookup: FakeLookup) -> None:
    """A call to a method that does not exist gives a problem naming it.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.
    fake_lookup : FakeLookup
        Fake version lookup.
    """
    fake_lookup.versions = {"json": "1.0"}
    code = "import json\nd = json.JSONDecoder()\nd.nope()\n"
    skill = _make_skill(tmp_path, "bad-method", "json>=0", code)
    report: NameReport = check_names(skill, roots=ROOTS, lookup=fake_lookup)
    assert len(report.problems) == 1
    assert report.problems[0].kind == "name"
    assert "nope" in report.problems[0].detail


def test_non_call_attribute_is_unchecked(tmp_path: Path, fake_lookup: FakeLookup) -> None:
    """A read of an attribute that is not called counts as unchecked.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.
    fake_lookup : FakeLookup
        Fake version lookup.
    """
    fake_lookup.versions = {"json": "1.0"}
    code = "import json\nd = json.JSONDecoder()\nx = d.object_hook\n"
    skill = _make_skill(tmp_path, "attr-read", "json>=0", code)
    report: NameReport = check_names(skill, roots=ROOTS, lookup=fake_lookup)
    assert report.unchecked >= 1
    assert report.problems == []


def test_pin_above_installed_version_is_skipped(tmp_path: Path, fake_lookup: FakeLookup) -> None:
    """A pin that the installed version does not meet gives status skipped.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.
    fake_lookup : FakeLookup
        Fake version lookup.
    """
    fake_lookup.versions = {"json": "1.0"}
    skill = _make_skill(tmp_path, "pin-high", "json>=5", "import json\n")
    report: NameReport = check_names(skill, roots=ROOTS, lookup=fake_lookup)
    assert report.status == "skipped"
    assert report.reason


def test_pin_outside_roots_is_skipped(tmp_path: Path, fake_lookup: FakeLookup) -> None:
    """A pin on a distribution that is not in roots gives status skipped.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.
    fake_lookup : FakeLookup
        Fake version lookup.
    """
    fake_lookup.versions = {"json": "1.0", "numpy": "2.0"}
    skill = _make_skill(tmp_path, "pin-other", "numpy>=1", "import numpy\n")
    report: NameReport = check_names(skill, roots=ROOTS, lookup=fake_lookup)
    assert report.status == "skipped"


def test_block_that_does_not_parse_is_ignored(tmp_path: Path, fake_lookup: FakeLookup) -> None:
    """A python block with a syntax error gives no problem from check_names.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory.
    fake_lookup : FakeLookup
        Fake version lookup.
    """
    fake_lookup.versions = {"json": "1.0"}
    skill = _make_skill(tmp_path, "broken", "json>=0", "def (:\n")
    report: NameReport = check_names(skill, roots=ROOTS, lookup=fake_lookup)
    assert report.problems == []
