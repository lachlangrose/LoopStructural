from __future__ import annotations

from pathlib import Path

import pytest

from loop_api import from_yaml
from loop_api.diagnostics import LoopApiValidationError


FIXTURES = Path(__file__).parent / "fixtures"


def test_normalization_populates_contract_sections():
    payload = """
metadata:
  name: Test
features: []
observations: []
topology: []
"""
    assembly = from_yaml(payload, validation_mode="strict")
    assert set(assembly.spec) == {
        "metadata",
        "bounding_box",
        "solve",
        "observations",
        "features",
        "topology",
    }


def test_strict_fails_for_missing_observation_link():
    payload = {
        "observations": [{"id": "o1", "type": "pointset", "inline": {"coords": [[0.0, 0.0, 0.0]]}}],
        "features": [
            {
                "id": "u1",
                "type": "unit",
                "name": "U1",
                "data_links": {"basal": ["does-not-exist"]},
            }
        ],
        "topology": [],
    }
    with pytest.raises(LoopApiValidationError, match="missing-observation-link"):
        from_yaml(payload, validation_mode="strict")


def test_warn_mode_collects_missing_observation_link_diagnostic():
    payload = {
        "observations": [{"id": "o1", "type": "pointset", "inline": {"coords": [[0.0, 0.0, 0.0]]}}],
        "features": [
            {
                "id": "u1",
                "type": "unit",
                "name": "U1",
                "data_links": {"basal": ["does-not-exist"]},
            }
        ],
        "topology": [],
    }
    assembly = from_yaml(payload, validation_mode="warn")
    codes = {item["code"] for item in assembly.diagnostics}
    assert "missing-observation-link" in codes


def test_strict_fails_for_cycle_in_topology():
    payload = {
        "observations": [
            {"id": "o1", "type": "pointset", "inline": {"coords": [[0.0, 0.0, 0.0]]}},
            {"id": "o2", "type": "pointset", "inline": {"coords": [[1.0, 0.0, 0.0]]}},
        ],
        "features": [
            {"id": "u1", "type": "unit", "name": "U1", "data_links": {"basal": ["o1"]}},
            {"id": "u2", "type": "unit", "name": "U2", "data_links": {"basal": ["o2"]}},
        ],
        "topology": [
            {"type": "overlies", "master": "u1", "slave": "u2"},
            {"type": "overlies", "master": "u2", "slave": "u1"},
        ],
    }
    with pytest.raises(LoopApiValidationError, match="invalid-dag"):
        from_yaml(payload, validation_mode="strict")


def test_warn_mode_drops_cycle_edge_and_continues():
    payload = {
        "observations": [
            {"id": "o1", "type": "pointset", "inline": {"coords": [[0.0, 0.0, 0.0]]}},
            {"id": "o2", "type": "pointset", "inline": {"coords": [[1.0, 0.0, 0.0]]}},
        ],
        "features": [
            {"id": "u1", "type": "unit", "name": "U1", "data_links": {"basal": ["o1"]}},
            {"id": "u2", "type": "unit", "name": "U2", "data_links": {"basal": ["o2"]}},
        ],
        "topology": [
            {"type": "overlies", "master": "u1", "slave": "u2"},
            {"type": "overlies", "master": "u2", "slave": "u1"},
        ],
    }
    assembly = from_yaml(payload, validation_mode="warn")
    assert len(assembly.spec["topology"]) == 1
    codes = {item["code"] for item in assembly.diagnostics}
    assert "invalid-dag" in codes


def test_relative_file_observations_resolve_from_yaml_directory():
    model_path = FIXTURES / "model.yaml"
    assembly = from_yaml(model_path, validation_mode="strict")
    project = assembly.to_project()
    assert len(project.observations) >= 3
