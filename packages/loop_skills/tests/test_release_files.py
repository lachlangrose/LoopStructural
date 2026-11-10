"""Check that the release files list the loop-skills package.

This covers story 1, scenario 6 of the release consistency checks.
The checks read the release-please files at the repository root.
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_KEY = "packages/loop_skills"
CONFIG_PATH = REPO_ROOT / ".release-please-config.json"
MANIFEST_PATH = REPO_ROOT / ".release-please-manifest.json"
PYPROJECT_PATH = REPO_ROOT / PACKAGE_KEY / "pyproject.toml"

# Python 3.9 has no tomllib, so the version is read with a regular expression.
VERSION_PATTERN = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


@pytest.fixture
def release_config() -> dict:
    """Return the parsed release-please config.

    Skip the test when the file is not present, as in an sdist build.

    Returns
    -------
    dict
        The parsed contents of ``.release-please-config.json``.
    """
    if not CONFIG_PATH.is_file():
        pytest.skip("release-please config is not present (sdist build)")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def release_manifest() -> dict:
    """Return the parsed release-please manifest.

    Skip the test when the file is not present, as in an sdist build.

    Returns
    -------
    dict
        The parsed contents of ``.release-please-manifest.json``.
    """
    if not MANIFEST_PATH.is_file():
        pytest.skip("release-please manifest is not present (sdist build)")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_config_lists_package_with_component_and_type(release_config: dict) -> None:
    """The config has a python package entry for loop-skills.

    Parameters
    ----------
    release_config : dict
        The parsed release-please config.
    """
    packages = release_config["packages"]
    assert PACKAGE_KEY in packages, f"{PACKAGE_KEY} is missing from packages"
    entry = packages[PACKAGE_KEY]
    assert entry.get("component") == "loop-skills"
    assert entry.get("release-type") == "python"


def test_root_package_excludes_loop_skills(release_config: dict) -> None:
    """The root package excludes the loop-skills path.

    Without this exclusion, loop-skills commits change the root version.

    Parameters
    ----------
    release_config : dict
        The parsed release-please config.
    """
    exclude_paths = release_config["packages"]["."]["exclude-paths"]
    assert PACKAGE_KEY in exclude_paths


def test_manifest_lists_package_at_initial_version(release_manifest: dict) -> None:
    """The manifest has loop-skills at version 0.1.0.

    Parameters
    ----------
    release_manifest : dict
        The parsed release-please manifest.
    """
    assert PACKAGE_KEY in release_manifest, f"{PACKAGE_KEY} is missing from manifest"
    assert release_manifest[PACKAGE_KEY] == "0.1.0"


def test_pyproject_version_matches_manifest(release_manifest: dict) -> None:
    """The pyproject version equals the manifest version.

    Parameters
    ----------
    release_manifest : dict
        The parsed release-please manifest.
    """
    if not PYPROJECT_PATH.is_file():
        pytest.skip("loop-skills pyproject.toml is not present (sdist build)")
    assert PACKAGE_KEY in release_manifest, f"{PACKAGE_KEY} is missing from manifest"
    match = VERSION_PATTERN.search(PYPROJECT_PATH.read_text(encoding="utf-8"))
    assert match is not None, "no version line found in pyproject.toml"
    assert match.group(1) == release_manifest[PACKAGE_KEY]
