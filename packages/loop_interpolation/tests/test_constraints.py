import numpy as np
import pytest
from loop_interpolation.constrains import (
    ValueConstraint,
    GradientConstraint,
    InequalityConstraint,
    InequalityPair,
    InterfaceConstraint,
)


def test_value_constraint():
    points = np.array([[0, 0, 0], [1, 1, 1]])
    values = np.array([10, 20])
    weights = np.array([1.0, 0.5])
    constraint = ValueConstraint(points=points, values=values, weights=weights)

    assert np.array_equal(constraint.points, points)
    assert np.array_equal(constraint.values, values)
    assert np.array_equal(constraint.weights, weights)


def test_gradient_constraint():
    points = np.array([[0, 0, 0], [1, 1, 1]])
    vectors = np.array([[1, 0, 0], [0, 1, 0]])
    weights = np.array([1.0, 0.5])
    constraint = GradientConstraint(points=points, vectors=vectors, weights=weights, is_normal=True)

    assert np.array_equal(constraint.points, points)
    assert np.array_equal(constraint.vectors, vectors)
    assert np.array_equal(constraint.weights, weights)
    assert constraint.is_normal


def test_inequality_constraint():
    points = np.array([[0, 0, 0], [1, 1, 1]])
    bounds = np.array([[0, 10], [5, 15]])
    weights = np.array([1.0, 0.5])
    constraint = InequalityConstraint(points=points, bounds=bounds, weights=weights)

    assert np.array_equal(constraint.points, points)
    assert np.array_equal(constraint.bounds, bounds)
    assert np.array_equal(constraint.weights, weights)


def test_inequality_pair():
    point_a = np.array([0, 0, 0])
    point_b = np.array([1, 1, 1])
    weight = 1.0
    constraint = InequalityPair(point_a=point_a, point_b=point_b, weight=weight)

    assert np.array_equal(constraint.point_a, point_a)
    assert np.array_equal(constraint.point_b, point_b)
    assert constraint.weight == weight


def test_interface_constraint():
    points = np.array([[0, 0, 0], [1, 1, 1]])
    value = 10.0
    weights = np.array([1.0, 0.5])
    constraint = InterfaceConstraint(points=points, value=value, weights=weights)

    assert np.array_equal(constraint.points, points)
    assert constraint.value == value
    assert np.array_equal(constraint.weights, weights)
