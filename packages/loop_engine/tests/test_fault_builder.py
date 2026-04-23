from __future__ import annotations

import numpy as np

from loop_common.geometry import BoundingBox
from loop_common.observations import Orientation, PointSet
from loop_engine.features.fault import FaultBuilder


class _LinkedObs:
    def __init__(self, observation):
        self.observation = observation


class _LinkedData:
    def __init__(self, by_role):
        self.feature_id = "fault-1"
        self.feature_name = "Fault 1"
        self.feature_type = "Fault"
        self.point_constraints = np.empty((0, 3), dtype=float)
        self.gradient_constraints = np.empty((0, 6), dtype=float)
        self.tangent_constraints = np.empty((0, 6), dtype=float)
        self.by_role = by_role
        self.missing_observation_ids = []


class _Feature:
    build_params = {
        "trace_iso": 0.0,
        "hanging_wall_iso": 2.0,
        "footwall_iso": -2.0,
    }


class _Schema:
    def __init__(self):
        self.bounding_box = BoundingBox(
            origin=np.array([-1.0, -1.0, -1.0]),
            maximum=np.array([2.0, 2.0, 2.0]),
        )


class _Model:
    def __init__(self):
        self.schema = _Schema()
        self.interpolatortype = "FDI"
        self.nelements = 100


class _FakeInterpolatorBuilder:
    instances = []

    def __init__(self, interpolatortype, bounding_box, nelements):
        self.interpolatortype = interpolatortype
        self.bounding_box = bounding_box
        self.nelements = nelements
        self.value_constraints = None
        self.normal_constraints = None
        self.tangent_constraints = None
        _FakeInterpolatorBuilder.instances.append(self)

    def add_value_constraints(self, constraints):
        self.value_constraints = constraints

    def add_normal_constraints(self, constraints):
        self.normal_constraints = constraints

    def add_tangent_constraints(self, constraints):
        self.tangent_constraints = constraints

    def setup_interpolator(self):
        return self

    def solve(self):
        return self

    def build(self):
        return "fault-interpolator"


def test_fault_builder_uses_role_specific_constraints(monkeypatch):
    monkeypatch.setattr(
        "loop_interpolation.InterpolatorBuilder",
        _FakeInterpolatorBuilder,
    )

    trace = PointSet(name="trace", coords=np.array([[0.0, 0.0, 0.0]]))
    hanging = PointSet(name="hw", coords=np.array([[0.0, 1.0, 0.0]]))
    footwall = PointSet(name="fw", coords=np.array([[0.0, -1.0, 0.0]]))
    orientation = Orientation(
        name="ori",
        coords=np.array([[0.0, 0.0, 0.0]]),
        vector=np.array([[0.0, 0.0, 1.0]]),
        magnitude=np.array([1.0]),
        polarity=np.array([1.0]),
        type="plane",
    )
    slip = Orientation(
        name="slip",
        coords=np.array([[0.0, 0.0, 0.0]]),
        vector=np.array([[1.0, 0.0, 0.0]]),
        magnitude=np.array([1.0]),
        polarity=np.array([1.0]),
        type="lineation",
    )

    linked_data = _LinkedData(
        by_role={
            "trace": [_LinkedObs(trace)],
            "hanging_wall": [_LinkedObs(hanging)],
            "footwall": [_LinkedObs(footwall)],
            "orientation": [_LinkedObs(orientation)],
            "slip_vector": [_LinkedObs(slip)],
        }
    )
    payload = {
        "feature_id": "fault-1",
        "feature": _Feature(),
        "linked_data": linked_data,
    }

    result = FaultBuilder(_Model()).build(payload)

    assert result == "fault-interpolator"
    builder = _FakeInterpolatorBuilder.instances[-1]

    assert builder.value_constraints.shape == (3, 4)
    assert set(builder.value_constraints[:, 3]) == {0.0, 2.0, -2.0}

    assert builder.normal_constraints.shape == (1, 6)
    assert np.allclose(builder.normal_constraints[0, 3:], np.array([0.0, 0.0, 1.0]))

    assert builder.tangent_constraints.shape == (1, 6)
    assert np.allclose(builder.tangent_constraints[0, 3:], np.array([1.0, 0.0, 0.0]))
