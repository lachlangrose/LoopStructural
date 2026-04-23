import numpy as np
import pytest

from loop_common.interfaces.representation import BaseRepresentation
from loop_interpolation import GeologicalInterpolator


def test_get_data_locations(interpolator, data):
    interpolator.set_value_constraints(
        data.loc[~data["val"].isna(), ["X", "Y", "Z", "val", "w"]].to_numpy()
    )
    interpolator.set_normal_constraints(
        data.loc[~data["nx"].isna(), ["X", "Y", "Z", "nx", "ny", "nz", "w"]].to_numpy()
    )
    locations = interpolator.get_data_locations()
    assert np.sum(locations - data[["X", "Y", "Z"]].to_numpy()) == 0


def test_get_value_constraints(interpolator, data):
    interpolator.set_value_constraints(
        data.loc[~data["val"].isna(), ["X", "Y", "Z", "val", "w"]].to_numpy()
    )
    interpolator.set_normal_constraints(
        data.loc[~data["nx"].isna(), ["X", "Y", "Z", "nx", "ny", "nz", "w"]].to_numpy()
    )
    val = interpolator.get_value_constraints()
    assert np.sum(val - data.loc[~data["val"].isna(), ["X", "Y", "Z", "val", "w"]].to_numpy()) == 0


def test_get_norm_constraints(interpolator, data):
    interpolator.set_value_constraints(
        data.loc[~data["val"].isna(), ["X", "Y", "Z", "val", "w"]].to_numpy()
    )
    interpolator.set_normal_constraints(
        data.loc[~data["nx"].isna(), ["X", "Y", "Z", "nx", "ny", "nz", "w"]].to_numpy()
    )
    val = interpolator.get_norm_constraints()
    assert (
        np.sum(
            val - data.loc[~data["nx"].isna(), ["X", "Y", "Z", "nx", "ny", "nz", "w"]].to_numpy()
        )
        == 0
    )


def test_reset(interpolator, data):
    interpolator.set_value_constraints(
        data.loc[~data["val"].isna(), ["X", "Y", "Z", "val", "w"]].to_numpy()
    )
    interpolator.set_normal_constraints(
        data.loc[~data["nx"].isna(), ["X", "Y", "Z", "nx", "ny", "nz", "w"]].to_numpy()
    )
    interpolator.clean()
    assert interpolator.get_data_locations().shape[0] == 0
    assert not interpolator.up_to_date


def test_interpolator_is_base_representation(interpolator):
    assert isinstance(interpolator, BaseRepresentation)


def test_geological_interpolator_from_dict_delegates_to_factory(monkeypatch):
    from loop_interpolation._interpolator_factory import InterpolatorFactory

    payload = {"type": "FDI", "custom": "value"}
    sentinel = object()
    calls = []

    def _fake_from_dict(data):
        calls.append(data)
        return sentinel

    monkeypatch.setattr(InterpolatorFactory, "from_dict", _fake_from_dict)

    result = GeologicalInterpolator.from_dict(payload)

    assert result is sentinel
    assert calls == [payload]


class _MinimalGeologicalInterpolator(GeologicalInterpolator):
    def __init__(self):
        super().__init__()

    def set_nelements(self, nelements: int) -> int:
        return nelements

    @property
    def n_elements(self) -> int:
        return 0

    def set_region(self, **kwargs):
        return None

    def setup_interpolator(self, **kwargs):
        return None

    def solve_system(self, solver, solver_kwargs: dict = {}) -> bool:
        return True

    def update(self) -> bool:
        return True

    def evaluate_value(self, locations: np.ndarray):
        return np.zeros(np.asarray(locations).shape[0])

    def evaluate_gradient(self, locations: np.ndarray):
        locations = np.asarray(locations)
        return np.zeros((locations.shape[0], locations.shape[1]))

    def reset(self):
        self.clean()

    def add_value_constraints(self, w: float = 1.0):
        return None

    def add_gradient_constraints(self, w: float = 1.0):
        return None

    def add_norm_constraints(self, w: float = 1.0):
        return None

    def add_tangent_constraints(self, w: float = 1.0):
        return None

    def add_interface_constraints(self, w: float = 1.0):
        return None

    def add_value_inequality_constraints(self, w: float = 1.0):
        return None

    def add_inequality_pairs_constraints(
        self,
        w: float = 1.0,
        upper_bound=np.finfo(float).eps,
        lower_bound=-np.inf,
        pairs=None,
    ):
        return None


def test_default_surfaces_raises_not_implemented():
    interpolator = _MinimalGeologicalInterpolator()

    with pytest.raises(NotImplementedError, match="Surface extraction not implemented"):
        interpolator.surfaces(0.0)
