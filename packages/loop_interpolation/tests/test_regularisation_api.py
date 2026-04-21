import numpy as np
import pytest

from loop_interpolation import (
    DirectionalRegularisation,
    DiscreteFoldInterpolator,
    FiniteDifferenceInterpolator,
    PiecewiseLinearInterpolator,
    RegularisationConfig,
    StructuredGrid,
    TetMesh,
)


def _constant_direction(points: np.ndarray, direction=(0.0, 0.0, 1.0)) -> np.ndarray:
    vector = np.asarray(direction, dtype=float)
    vector /= np.linalg.norm(vector)
    return np.tile(vector, (points.shape[0], 1))


def _make_structured_grid() -> StructuredGrid:
    return StructuredGrid(
        origin=np.array([0.0, 0.0, 0.0]),
        nsteps=np.array([5, 5, 5]),
        step_vector=np.array([1.0, 1.0, 1.0]),
    )


def _make_tet_mesh() -> TetMesh:
    return TetMesh(
        origin=np.array([0.0, 0.0, 0.0]),
        nsteps=np.array([5, 5, 5]),
        step_vector=np.array([1.0, 1.0, 1.0]),
    )


@pytest.mark.parametrize(
    ("factory", "setup_kwargs"),
    (
        (lambda: FiniteDifferenceInterpolator(_make_structured_grid()), {"dxx": 0.0, "dyy": 0.0, "dzz": 0.0, "dxy": 0.0, "dyz": 0.0, "dxz": 0.0}),
        (lambda: PiecewiseLinearInterpolator(_make_tet_mesh()), {"cgw": 0.0}),
    ),
)
def test_shared_directional_regularisation_dict_works_across_support_types(factory, setup_kwargs):
    interpolator = factory()
    regularisation = {
        "isotropic": 0.0,
        "directional": [
            {
                "weight": 2.5,
                "direction": lambda points: _constant_direction(points, direction=(0.0, 0.0, 1.0)),
                "name": "shared vertical smoothing",
            }
        ],
    }

    interpolator.setup_interpolator(
        regularisation=regularisation,
        cpw=0.0,
        gpw=0.0,
        npw=0.0,
        tpw=0.0,
        ipw=0.0,
        **setup_kwargs,
    )

    matching = [name for name in interpolator.constraints if name.startswith("shared vertical smoothing")]
    assert matching
    assert all(interpolator.constraints[name]["matrix"].shape[0] > 0 for name in matching)


def test_shared_directional_regularisation_config_object_is_accepted():
    interpolator = PiecewiseLinearInterpolator(_make_tet_mesh())
    regularisation = RegularisationConfig(
        isotropic=0.0,
        directional=(
            DirectionalRegularisation(
                weight=1.0,
                direction=lambda points: _constant_direction(points, direction=(1.0, 0.0, 0.0)),
                name="config object smoothing",
            ),
        ),
    )

    interpolator.setup_interpolator(
        regularisation=regularisation,
        cpw=0.0,
        gpw=0.0,
        npw=0.0,
        tpw=0.0,
        ipw=0.0,
        cgw=0.0,
    )

    assert any(name.startswith("config object smoothing") for name in interpolator.constraints)


def test_discrete_fold_regularisation_uses_shared_directional_api():
    class _FoldStub:
        def get_deformed_orientation(self, points):
            deformed = _constant_direction(points, direction=(1.0, 0.0, 0.0))
            axis = _constant_direction(points, direction=(0.0, 1.0, 0.0))
            normal = _constant_direction(points, direction=(0.0, 0.0, 1.0))
            return deformed, axis, normal

    interpolator = DiscreteFoldInterpolator(_make_tet_mesh(), fold=_FoldStub())
    interpolator.setup_interpolator(
        cgw=0.0,
        cpw=0.0,
        gpw=0.0,
        npw=0.0,
        tpw=0.0,
        ipw=0.0,
        fold_weights={
            "fold_orientation": None,
            "fold_axis_w": None,
            "fold_normalisation": None,
            "fold_regularisation": [0.1, 0.01, 0.01],
        },
    )

    matching = [name for name in interpolator.constraints if "fold regularisation" in name]
    assert matching
    assert all(interpolator.constraints[name]["matrix"].shape[0] > 0 for name in matching)