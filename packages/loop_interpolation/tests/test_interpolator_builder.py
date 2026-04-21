import pytest
import numpy as np
from loop_common.geometry import BoundingBox
from loop_interpolation import InterpolatorBuilder, InterpolatorType


@pytest.fixture
def setup_builder():
    bounding_box = BoundingBox(np.array([0, 0, 0]), np.array([1, 1, 1]))
    nelements = 1000
    buffer = 0.2
    builder = InterpolatorBuilder(
        interpolatortype=InterpolatorType.FINITE_DIFFERENCE,
        bounding_box=bounding_box,
        nelements=nelements,
        buffer=buffer,
    )
    return builder


def test_create_interpolator(setup_builder):
    builder = setup_builder
    builder.build()
    assert builder.interpolator is not None, "Interpolator should be created"


def test_set_value_constraints(setup_builder):
    builder = setup_builder
    builder.build()
    value_constraints = np.array([[0.5, 0.5, 0.5, 1.0, 1.0]])
    builder.add_value_constraints(value_constraints)
    assert np.array_equal(builder.interpolator.data["value"], value_constraints), (
        "Value constraints should be set correctly"
    )


def test_set_gradient_constraints(setup_builder):
    builder = setup_builder
    gradient_constraints = np.array([[0.5, 0.5, 0.5, 1.0, 0.0, 0.0, 1.0]])
    builder.add_gradient_constraints(gradient_constraints)
    assert np.array_equal(builder.interpolator.data["gradient"], gradient_constraints), (
        "Gradient constraints should be set correctly"
    )


def test_set_normal_constraints(setup_builder):
    builder = setup_builder
    normal_constraints = np.array([[0.5, 0.5, 0.5, 1.0, 0.0, 0.0, 1.0]])
    builder.add_normal_constraints(normal_constraints)
    assert np.array_equal(builder.interpolator.data["normal"], normal_constraints), (
        "Normal constraints should be set correctly"
    )


def test_setup_interpolator(setup_builder):
    builder = setup_builder
    builder.build()
    value_constraints = np.array([[0.5, 0.5, 0.5, 1.0, 1.0]])
    interpolator = builder.add_value_constraints(value_constraints).setup_interpolator().build()
    assert interpolator is not None, "Interpolator should be set up"
    assert np.array_equal(interpolator.data["value"], value_constraints), (
        "Value constraints should be set correctly after setup"
    )


def test_evaluate_scalar_value(setup_builder):
    builder = setup_builder
    builder.build()
    value_constraints = np.array([[0.5, 0.5, 0.5, 1.0]])
    interpolator = builder.add_value_constraints(value_constraints).setup_interpolator().build()
    locations = np.array([[0.5, 0.5, 0.5]])
    values = interpolator.evaluate_value(locations)
    assert values is not None, "Evaluation should return values"
    assert values.shape == (1,), "Evaluation should return correct shape"


def test_builder_regularisation_weight_scale_passthrough(setup_builder):
    builder = setup_builder
    value_constraints = np.array([[0.5, 0.5, 0.5, 1.0, 1.0]])
    interpolator = (
        builder.use_regularisation_weight_scale(True)
        .add_value_constraints(value_constraints)
        .setup_interpolator()
        .build()
    )
    assert interpolator.use_regularisation_weight_scale is True


def test_builder_regularisation_weight_sigma_passthrough(setup_builder):
    builder = setup_builder
    value_constraints = np.array([[0.5, 0.5, 0.5, 1.0, 1.0]])
    interpolator = (
        builder.use_regularisation_weight_scale(True)
        .regularisation_weight_sigma(0.25)
        .add_value_constraints(value_constraints)
        .setup_interpolator()
        .build()
    )
    assert interpolator.regularisation_weight_sigma == pytest.approx(0.25)
