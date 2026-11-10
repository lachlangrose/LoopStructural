"""Tests for the loop-skills plugin files.

These tests cover spec 007, scenario 1 and requirement FR-005. They check
the plugin manifest, the skills folder, the version values and the
marketplace entry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PACKAGE_ROOT: Path = Path(__file__).resolve().parents[1]
PLUGIN_ROOT: Path = PACKAGE_ROOT / "src" / "loop_skills"
REPO_ROOT: Path = Path(__file__).resolve().parents[3]
SKILL_NAMES: frozenset[str] = frozenset(
    {"build-model", "inspect-model", "map2loop-prepare", "install-help"}
)
VERSION_PATTERN: re.Pattern[str] = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def _read_plugin_manifest() -> dict:
    """Read and parse the plugin manifest.

    Returns
    -------
    dict
        The parsed content of ``plugin.json``.
    """
    path = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    assert path.is_file(), f"plugin manifest is missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_plugin_manifest_is_valid() -> None:
    """The plugin manifest is valid JSON with name, version and description."""
    manifest = _read_plugin_manifest()
    assert manifest.get("name") == "loop-skills"
    assert manifest.get("version"), "plugin manifest has no version"
    assert manifest.get("description"), "plugin manifest has no description"


def test_plugin_skills_folder_holds_four_skills() -> None:
    """The skills folder holds exactly the four skill folders."""
    skills_root = PLUGIN_ROOT / "skills"
    assert skills_root.is_dir(), f"skills folder is missing: {skills_root}"
    names = {path.name for path in skills_root.iterdir() if path.is_dir()}
    assert names == SKILL_NAMES


def test_plugin_version_matches_package_and_manifest() -> None:
    """The plugin version equals the package and release-please versions."""
    manifest_path = REPO_ROOT / ".release-please-manifest.json"
    if not manifest_path.is_file():
        pytest.skip("release-please manifest not found (sdist case)")

    plugin_version = _read_plugin_manifest().get("version")

    pyproject_path = PACKAGE_ROOT / "pyproject.toml"
    assert pyproject_path.is_file(), f"pyproject.toml is missing: {pyproject_path}"
    match = VERSION_PATTERN.search(pyproject_path.read_text(encoding="utf-8"))
    assert match is not None, "pyproject.toml has no version line"
    assert plugin_version == match.group(1)

    release_versions = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert plugin_version == release_versions["packages/loop_skills"]


def test_marketplace_lists_loop_skills_plugin() -> None:
    """The repository marketplace lists the loop-skills plugin source."""
    if not (REPO_ROOT / "packages" / "loop_skills").is_dir():
        pytest.skip("packages/loop_skills not found (sdist case)")

    marketplace_path = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    assert marketplace_path.is_file(), f"marketplace file is missing: {marketplace_path}"
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    plugins = marketplace.get("plugins")
    assert isinstance(plugins, list), "marketplace has no plugins list"

    entries = [entry for entry in plugins if entry.get("name") == "loop-skills"]
    assert entries, "marketplace has no loop-skills entry"
    assert any(entry.get("source") == "./packages/loop_skills/src/loop_skills" for entry in entries)
