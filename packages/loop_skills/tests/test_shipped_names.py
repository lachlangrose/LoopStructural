"""Name checks for the shipped skills (SC-004, FR-013).

Each shipped skill must pass the name check. A skipped check counts as a
failure, so the result always shows a real verdict.
"""

from __future__ import annotations

import pytest
from loop_skills._check import check_names
from loop_skills._skill import iter_skills

pytestmark = pytest.mark.names

SHIPPED_NAMES = ["build-model", "inspect-model", "map2loop-prepare"]


@pytest.mark.parametrize("name", SHIPPED_NAMES, ids=SHIPPED_NAMES)
def test_shipped_skill_names(name: str) -> None:
    """Check that one shipped skill passes the name check.

    Parameters
    ----------
    name : str
        The name of the shipped skill to check.
    """
    skills = {skill.name: skill for skill in iter_skills()}
    if name not in skills:
        pytest.fail(f"skill {name!r} is not shipped")

    report = check_names(skills[name])

    if report.status != "checked":
        pytest.fail(f"name check was skipped for {name!r}: {report.reason}")
    print(report.checked)
    print(report.unchecked)
    assert report.problems == []
