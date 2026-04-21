"""Input validation helpers for loop_interpolation.

This module provides centralized validation for constraint inputs to ensure
consistent error handling, clear error messages, and early detection of
invalid constraint combinations.

NaN handling contract
---------------------
- **Weight column NaN** → silently replaced with 1.0 (default weight).
  This lets callers pass ``np.nan`` as a sentinel for "use default weight",
  which is a common pattern when assembling constraints from DataFrames.
- **Position / data column NaN or inf** → rows are silently dropped with a
  warning.  This preserves backward-compatible behaviour where constraints
  that fall outside the model or contain missing values are ignored.
"""

import logging
from typing import Tuple, Union
import numpy as np

_logger = logging.getLogger(__name__)


def _fill_nan_weights(points: np.ndarray, weight_col: int) -> np.ndarray:
    """Replace NaN values in the weight column with 1.0 (default weight).

    Parameters
    ----------
    points : np.ndarray
        Constraint array, already converted to float64.
    weight_col : int
        Column index of the weight column.

    Returns
    -------
    np.ndarray
        Array with NaN weights replaced; a copy is returned only if any
        replacements were made.
    """
    nan_mask = ~np.isfinite(points[:, weight_col])
    if np.any(nan_mask):
        n_replaced = int(np.sum(nan_mask))
        _logger.warning(
            "%d NaN weight value(s) replaced with 1.0 (default weight). "
            "Provide explicit finite weights to suppress this warning.",
            n_replaced,
        )
        points = points.copy()
        points[nan_mask, weight_col] = 1.0
    return points


def _drop_nan_data_rows(points: np.ndarray, data_cols: slice, name: str) -> np.ndarray:
    """Drop rows that contain NaN or inf in the position / data columns.

    Weight columns are intentionally excluded from this check because NaN
    weights are handled separately by :func:`_fill_nan_weights`.

    Parameters
    ----------
    points : np.ndarray
        Constraint array, already converted to float64.
    data_cols : slice
        Slice selecting the position / data columns (excluding weight).
    name : str
        Human-readable constraint type name used in the warning message.

    Returns
    -------
    np.ndarray
        Array with invalid rows removed; the original array is returned
        unchanged when no rows are dropped.
    """
    bad_rows = ~np.isfinite(points[:, data_cols]).all(axis=1)
    if np.any(bad_rows):
        n_dropped = int(np.sum(bad_rows))
        _logger.warning(
            "%d %s row(s) dropped: position or data columns contain NaN or inf. "
            "Provide finite values to include them.",
            n_dropped,
            name,
        )
        points = points[~bad_rows]
    return points


class ValidationError(ValueError):
    """Base exception for constraint validation errors."""

    pass


class ShapeError(ValidationError):
    """Exception for shape mismatches in constraint arrays."""

    pass


class DtypeError(ValidationError):
    """Exception for data type mismatches in constraint arrays."""

    pass


class FiniteValueError(ValidationError):
    """Exception for non-finite values in constraint arrays."""

    pass


class VectorError(ValidationError):
    """Exception for invalid vector/direction constraints."""

    pass


class WeightError(ValidationError):
    """Exception for invalid weight values."""

    pass


class UnsupportedCombinationError(ValidationError):
    """Exception for unsupported constraint combinations."""

    pass


def _ensure_float_array(arr: np.ndarray, name: str = "array") -> np.ndarray:
    """Convert array to float type with error handling.

    Parameters
    ----------
    arr : np.ndarray
        Input array to convert
    name : str
        Name of array for error messages

    Returns
    -------
    np.ndarray
        Array converted to float64

    Raises
    ------
    DtypeError
        If array cannot be converted to float
    """
    try:
        return np.asarray(arr, dtype=np.float64)
    except (TypeError, ValueError) as e:
        raise DtypeError(
            f"{name} could not be converted to float64. "
            f"All constraint arrays must contain numeric values. Error: {e}"
        )


def _check_shape(
    arr: np.ndarray,
    expected_shape: Tuple[Union[int, None], ...],
    name: str = "array",
) -> None:
    """Validate array shape matches expectations.

    Parameters
    ----------
    arr : np.ndarray
        Array to validate
    expected_shape : tuple
        Expected shape. Use None for variable dimensions.
    name : str
        Name of array for error messages

    Raises
    ------
    ShapeError
        If shape doesn't match expected shape
    """
    if arr.ndim != len(expected_shape):
        raise ShapeError(
            f"{name} has {arr.ndim} dimensions, but {len(expected_shape)} expected. "
            f"Expected shape: {expected_shape}, got {arr.shape}"
        )

    for i, (actual, expected) in enumerate(zip(arr.shape, expected_shape)):
        if expected is not None and actual != expected:
            raise ShapeError(
                f"{name} dimension {i}: expected {expected}, got {actual}. "
                f"Expected shape: {expected_shape}, got {arr.shape}"
            )


def _check_finite(arr: np.ndarray, name: str = "array") -> None:
    """Validate all values in array are finite (not NaN or inf).

    Parameters
    ----------
    arr : np.ndarray
        Array to validate
    name : str
        Name of array for error messages

    Raises
    ------
    FiniteValueError
        If any non-finite values are found
    """
    non_finite = ~np.isfinite(arr)
    if np.any(non_finite):
        n_invalid = int(np.sum(non_finite))
        invalid_indices = np.where(non_finite)
        raise FiniteValueError(
            f"{name} contains {n_invalid} non-finite values (NaN or inf). "
            f"All constraint values must be finite. "
            f"Found at indices: {invalid_indices}"
        )


def validate_value_constraint(
    points: np.ndarray,
    dimensions: int = 3,
) -> np.ndarray:
    """Validate value constraint input array.

    Value constraints specify scalar field values at points.
    Expected format: [X, Y, Z, value] or [X, Y, Z, value, weight]

    Parameters
    ----------
    points : np.ndarray
        Input point array to validate
    dimensions : int
        Number of spatial dimensions (default 3)

    Returns
    -------
    np.ndarray
        Validated array (float64 dtype).  Rows with NaN/inf in position or
        value columns are silently dropped; NaN weights are replaced with 1.0.

    Raises
    ------
    ShapeError
        If points has wrong number of dimensions or columns
    DtypeError
        If points cannot be converted to float
    FiniteValueError
        If any coordinates or values are non-finite after NaN rows are dropped
    """
    points = _ensure_float_array(points, "Value constraint points")
    _check_shape(points, (None, None), "Value constraint points")

    min_cols = dimensions + 1
    actual_cols = points.shape[1]
    if actual_cols < min_cols:
        raise ShapeError(
            f"Value constraint points have {actual_cols} columns, but at least "
            f"{min_cols} required (X, Y, Z, value). "
            f"Shape: {points.shape}"
        )

    if actual_cols > dimensions + 2:
        raise ShapeError(
            f"Value constraint points have {actual_cols} columns, but maximum "
            f"{dimensions + 2} supported (X, Y, Z, value, weight). "
            f"Shape: {points.shape}"
        )

    # NaN weight → default 1.0; NaN position/value rows → drop
    if actual_cols == dimensions + 2:
        points = _fill_nan_weights(points, weight_col=dimensions + 1)
    points = _drop_nan_data_rows(points, slice(0, dimensions + 1), "value constraint")

    if points.shape[0] == 0:
        return points

    _check_finite(points[:, :dimensions], "Position (X, Y, Z)")
    _check_finite(points[:, dimensions], "Value column")

    if actual_cols == dimensions + 2:
        _check_finite(points[:, dimensions + 1], "Weight column")

    return points


def validate_gradient_constraint(
    points: np.ndarray,
    dimensions: int = 3,
) -> np.ndarray:
    """Validate gradient constraint input array.

    Gradient constraints specify field gradients at points.
    Expected format: [X, Y, Z, gx, gy, gz] or [X, Y, Z, gx, gy, gz, weight]

    Parameters
    ----------
    points : np.ndarray
        Input point array to validate
    dimensions : int
        Number of spatial dimensions (default 3)

    Returns
    -------
    np.ndarray
        Validated array (float64 dtype).  Rows with NaN/inf in position or
        gradient columns are silently dropped; NaN weights are replaced with 1.0.

    Raises
    ------
    ShapeError
        If points has wrong number of dimensions or columns
    DtypeError
        If points cannot be converted to float
    FiniteValueError
        If any coordinates or gradient values are non-finite after NaN rows are dropped
    VectorError
        If gradient vectors have zero magnitude (degenerate case)
    """
    points = _ensure_float_array(points, "Gradient constraint points")
    _check_shape(points, (None, None), "Gradient constraint points")

    min_cols = dimensions * 2
    actual_cols = points.shape[1]
    if actual_cols < min_cols:
        raise ShapeError(
            f"Gradient constraint points have {actual_cols} columns, but at least "
            f"{min_cols} required (X, Y, Z, gx, gy, gz). "
            f"Shape: {points.shape}"
        )

    if actual_cols > dimensions * 2 + 1:
        raise ShapeError(
            f"Gradient constraint points have {actual_cols} columns, but maximum "
            f"{dimensions * 2 + 1} supported (X, Y, Z, gx, gy, gz, weight). "
            f"Shape: {points.shape}"
        )

    # NaN weight → default 1.0; NaN position/vector rows → drop
    if actual_cols == dimensions * 2 + 1:
        points = _fill_nan_weights(points, weight_col=dimensions * 2)
    points = _drop_nan_data_rows(points, slice(0, dimensions * 2), "gradient constraint")

    if points.shape[0] == 0:
        return points

    _check_finite(points[:, :dimensions], "Position (X, Y, Z)")
    _check_finite(points[:, dimensions : dimensions * 2], "Gradient vector (gx, gy, gz)")

    if actual_cols == dimensions * 2 + 1:
        _check_finite(points[:, -1], "Weight column")

    # Warn about zero-magnitude gradients
    grad_vectors = points[:, dimensions : dimensions * 2]
    magnitudes = np.linalg.norm(grad_vectors, axis=1)
    zero_mag = magnitudes < 1e-14
    if np.any(zero_mag):
        n_zero = int(np.sum(zero_mag))
        zero_indices = np.where(zero_mag)[0]
        raise VectorError(
            f"Found {n_zero} gradient constraints with zero or near-zero magnitude. "
            f"Gradient vectors must have non-zero length. "
            f"Zero-magnitude vectors at indices: {zero_indices}"
        )

    return points


def validate_normal_constraint(
    points: np.ndarray,
    dimensions: int = 3,
) -> np.ndarray:
    """Validate normal constraint input array.

    Normal constraints specify surface normals at points.
    Expected format: [X, Y, Z, nx, ny, nz] or [X, Y, Z, nx, ny, nz, weight]

    Parameters
    ----------
    points : np.ndarray
        Input point array to validate
    dimensions : int
        Number of spatial dimensions (default 3)

    Returns
    -------
    np.ndarray
        Validated array (float64 dtype).  Rows with NaN/inf in position or
        normal columns are silently dropped; NaN weights are replaced with 1.0.

    Raises
    ------
    ShapeError
        If points has wrong number of dimensions or columns
    DtypeError
        If points cannot be converted to float
    FiniteValueError
        If any coordinates or normals are non-finite after NaN rows are dropped
    VectorError
        If normal vectors have zero magnitude
    """
    points = _ensure_float_array(points, "Normal constraint points")
    _check_shape(points, (None, None), "Normal constraint points")

    min_cols = dimensions * 2
    actual_cols = points.shape[1]
    if actual_cols < min_cols:
        raise ShapeError(
            f"Normal constraint points have {actual_cols} columns, but at least "
            f"{min_cols} required (X, Y, Z, nx, ny, nz). "
            f"Shape: {points.shape}"
        )

    if actual_cols > dimensions * 2 + 1:
        raise ShapeError(
            f"Normal constraint points have {actual_cols} columns, but maximum "
            f"{dimensions * 2 + 1} supported (X, Y, Z, nx, ny, nz, weight). "
            f"Shape: {points.shape}"
        )

    # NaN weight → default 1.0; NaN position/normal rows → drop
    if actual_cols == dimensions * 2 + 1:
        points = _fill_nan_weights(points, weight_col=dimensions * 2)
    points = _drop_nan_data_rows(points, slice(0, dimensions * 2), "normal constraint")

    if points.shape[0] == 0:
        return points

    _check_finite(points[:, :dimensions], "Position (X, Y, Z)")
    _check_finite(points[:, dimensions : dimensions * 2], "Normal vector (nx, ny, nz)")

    if actual_cols == dimensions * 2 + 1:
        _check_finite(points[:, -1], "Weight column")

    # Check for zero-magnitude normals
    normal_vectors = points[:, dimensions : dimensions * 2]
    magnitudes = np.linalg.norm(normal_vectors, axis=1)
    zero_mag = magnitudes < 1e-14
    if np.any(zero_mag):
        n_zero = int(np.sum(zero_mag))
        zero_indices = np.where(zero_mag)[0]
        raise VectorError(
            f"Found {n_zero} normal constraints with zero or near-zero magnitude. "
            f"Normal vectors must have non-zero length. "
            f"Zero-magnitude vectors at indices: {zero_indices}"
        )

    return points


def validate_tangent_constraint(
    points: np.ndarray,
    dimensions: int = 3,
) -> np.ndarray:
    """Validate tangent constraint input array.

    Tangent constraints specify tangent directions at points.
    Expected format: [X, Y, Z, tx, ty, tz] or [X, Y, Z, tx, ty, tz, weight]

    Parameters
    ----------
    points : np.ndarray
        Input point array to validate
    dimensions : int
        Number of spatial dimensions (default 3)

    Returns
    -------
    np.ndarray
        Validated array (float64 dtype).  Rows with NaN/inf in position or
        tangent columns are silently dropped; NaN weights are replaced with 1.0.

    Raises
    ------
    ShapeError
        If points has wrong number of dimensions or columns
    DtypeError
        If points cannot be converted to float
    FiniteValueError
        If any coordinates or tangents are non-finite after NaN rows are dropped
    VectorError
        If tangent vectors have zero magnitude
    """
    points = _ensure_float_array(points, "Tangent constraint points")
    _check_shape(points, (None, None), "Tangent constraint points")

    min_cols = dimensions * 2
    actual_cols = points.shape[1]
    if actual_cols < min_cols:
        raise ShapeError(
            f"Tangent constraint points have {actual_cols} columns, but at least "
            f"{min_cols} required (X, Y, Z, tx, ty, tz). "
            f"Shape: {points.shape}"
        )

    if actual_cols > dimensions * 2 + 1:
        raise ShapeError(
            f"Tangent constraint points have {actual_cols} columns, but maximum "
            f"{dimensions * 2 + 1} supported (X, Y, Z, tx, ty, tz, weight). "
            f"Shape: {points.shape}"
        )

    # NaN weight → default 1.0; NaN position/tangent rows → drop
    if actual_cols == dimensions * 2 + 1:
        points = _fill_nan_weights(points, weight_col=dimensions * 2)
    points = _drop_nan_data_rows(points, slice(0, dimensions * 2), "tangent constraint")

    if points.shape[0] == 0:
        return points

    _check_finite(points[:, :dimensions], "Position (X, Y, Z)")
    _check_finite(points[:, dimensions : dimensions * 2], "Tangent vector (tx, ty, tz)")

    if actual_cols == dimensions * 2 + 1:
        _check_finite(points[:, -1], "Weight column")

    # Check for zero-magnitude tangents
    tangent_vectors = points[:, dimensions : dimensions * 2]
    magnitudes = np.linalg.norm(tangent_vectors, axis=1)
    zero_mag = magnitudes < 1e-14
    if np.any(zero_mag):
        n_zero = int(np.sum(zero_mag))
        zero_indices = np.where(zero_mag)[0]
        raise VectorError(
            f"Found {n_zero} tangent constraints with zero or near-zero magnitude. "
            f"Tangent vectors must have non-zero length. "
            f"Zero-magnitude vectors at indices: {zero_indices}"
        )

    return points


def validate_interface_constraint(
    points: np.ndarray,
    dimensions: int = 3,
) -> np.ndarray:
    """Validate interface constraint input array.

    Interface constraints mark surface boundaries.
    Expected format: [X, Y, Z, id] or [X, Y, Z, id, weight]

    Parameters
    ----------
    points : np.ndarray
        Input point array to validate
    dimensions : int
        Number of spatial dimensions (default 3)

    Returns
    -------
    np.ndarray
        Validated array (float64 dtype).  Rows with NaN/inf in position or
        id columns are silently dropped; NaN weights are replaced with 1.0.

    Raises
    ------
    ShapeError
        If points has wrong number of dimensions or columns
    DtypeError
        If points cannot be converted to float
    FiniteValueError
        If any coordinates are non-finite after NaN rows are dropped
    """
    points = _ensure_float_array(points, "Interface constraint points")
    _check_shape(points, (None, None), "Interface constraint points")

    min_cols = dimensions + 1
    actual_cols = points.shape[1]
    if actual_cols < min_cols:
        raise ShapeError(
            f"Interface constraint points have {actual_cols} columns, but at least "
            f"{min_cols} required (X, Y, Z, interface_id). "
            f"Shape: {points.shape}"
        )

    if actual_cols > dimensions + 2:
        raise ShapeError(
            f"Interface constraint points have {actual_cols} columns, but maximum "
            f"{dimensions + 2} supported (X, Y, Z, interface_id, weight). "
            f"Shape: {points.shape}"
        )

    # NaN weight → default 1.0; NaN position/id rows → drop
    if actual_cols == dimensions + 2:
        points = _fill_nan_weights(points, weight_col=dimensions + 1)
    points = _drop_nan_data_rows(points, slice(0, dimensions + 1), "interface constraint")

    if points.shape[0] == 0:
        return points

    _check_finite(points[:, :dimensions], "Position (X, Y, Z)")
    if actual_cols == dimensions + 2:
        _check_finite(points[:, -1], "Weight column")

    return points


def validate_inequality_value_constraint(
    points: np.ndarray,
    dimensions: int = 3,
) -> np.ndarray:
    """Validate inequality value constraint input array.

    Inequality constraints specify bounds on scalar field values.
    Expected format: [X, Y, Z, lower_bound, upper_bound] or [X, Y, Z, lower_bound, upper_bound, weight]

    Parameters
    ----------
    points : np.ndarray
        Input point array to validate
    dimensions : int
        Number of spatial dimensions (default 3)

    Returns
    -------
    np.ndarray
        Validated array (float64 dtype)

    Raises
    ------
    ShapeError
        If points has wrong number of dimensions or columns
    DtypeError
        If points cannot be converted to float
    FiniteValueError
        If any coordinates or bounds are non-finite
    ValueError
        If lower bound >= upper bound for any constraint
    """
    points = _ensure_float_array(points, "Inequality constraint points")
    _check_shape(points, (None, None), "Inequality constraint points")

    min_cols = dimensions + 2
    actual_cols = points.shape[1]
    if actual_cols < min_cols:
        raise ShapeError(
            f"Inequality constraint points have {actual_cols} columns, but at least "
            f"{min_cols} required (X, Y, Z, lower_bound, upper_bound). "
            f"Shape: {points.shape}"
        )

    if actual_cols > dimensions + 3:
        raise ShapeError(
            f"Inequality constraint points have {actual_cols} columns, but maximum "
            f"{dimensions + 3} supported (X, Y, Z, lower_bound, upper_bound, weight). "
            f"Shape: {points.shape}"
        )

    _check_finite(points, "Inequality constraint points and bounds")

    # Validate position
    _check_finite(points[:, :dimensions], "Position (X, Y, Z)")
    _check_finite(points[:, dimensions : dimensions + 2], "Bound values")
    if actual_cols == dimensions + 3:
        _check_finite(points[:, -1], "Weight column")

    # Check lower_bound < upper_bound
    lower_bounds = points[:, dimensions]
    upper_bounds = points[:, dimensions + 1]
    invalid_bounds = lower_bounds >= upper_bounds
    if np.any(invalid_bounds):
        n_invalid = int(np.sum(invalid_bounds))
        invalid_indices = np.where(invalid_bounds)[0]
        raise ValidationError(
            f"Found {n_invalid} inequality constraints with lower_bound >= upper_bound. "
            f"For each constraint, lower_bound must be strictly less than upper_bound. "
            f"Invalid constraints at indices: {invalid_indices}"
        )

    return points


def validate_inequality_pairs_constraint(
    points: np.ndarray,
    dimensions: int = 3,
) -> np.ndarray:
    """Validate inequality pairs constraint input array.

    Inequality pairs enforce ordering between pairs of points.
    Expected format: [X, Y, Z, rock_id] or [X, Y, Z, rock_id, weight]

    Parameters
    ----------
    points : np.ndarray
        Input point array to validate
    dimensions : int
        Number of spatial dimensions (default 3)

    Returns
    -------
    np.ndarray
        Validated array (float64 dtype)

    Raises
    ------
    ShapeError
        If points has wrong number of dimensions or columns
    DtypeError
        If points cannot be converted to float
    FiniteValueError
        If any coordinates are non-finite
    """
    points = _ensure_float_array(points, "Inequality pairs constraint points")
    _check_shape(points, (None, None), "Inequality pairs constraint points")

    min_cols = dimensions + 1
    actual_cols = points.shape[1]
    if actual_cols < min_cols:
        raise ShapeError(
            f"Inequality pairs constraint points have {actual_cols} columns, but at least "
            f"{min_cols} required (X, Y, Z, rock_id). "
            f"Shape: {points.shape}"
        )

    if actual_cols > dimensions + 2:
        raise ShapeError(
            f"Inequality pairs constraint points have {actual_cols} columns, but maximum "
            f"{dimensions + 2} supported (X, Y, Z, rock_id, weight). "
            f"Shape: {points.shape}"
        )

    _check_finite(points, "Inequality pairs constraint points")

    # Validate position
    _check_finite(points[:, :dimensions], "Position (X, Y, Z)")
    if actual_cols == dimensions + 2:
        _check_finite(points[:, -1], "Weight column")

    return points


def validate_weights(
    weights: Union[float, np.ndarray],
    n_constraints: int,
    constraint_name: str = "constraint",
) -> Union[float, np.ndarray]:
    """Validate weight values for constraints.

    Weights must be positive scalars or arrays.

    Parameters
    ----------
    weights : float or np.ndarray
        Weight value(s) to validate
    n_constraints : int
        Number of constraints (for array validation)
    constraint_name : str
        Name of constraint type for error messages

    Returns
    -------
    float or np.ndarray
        Validated weights

    Raises
    ------
    DtypeError
        If weights cannot be converted to float
    FiniteValueError
        If weights contain non-finite values
    WeightError
        If weights are non-positive or wrong shape
    """
    if isinstance(weights, (int, float)):
        if not np.isfinite(weights):
            raise FiniteValueError(
                f"{constraint_name} weight is non-finite. "
                f"Weight must be a finite positive number. Got: {weights}"
            )
        if weights <= 0:
            raise WeightError(f"{constraint_name} weight must be positive. Got: {weights}")
        return float(weights)

    weights_arr = _ensure_float_array(weights, f"{constraint_name} weights array")

    if weights_arr.ndim == 1:
        if weights_arr.shape[0] != n_constraints:
            raise ShapeError(
                f"{constraint_name} weights array has {weights_arr.shape[0]} elements, "
                f"but {n_constraints} constraints provided. "
                f"Weight array length must match number of constraints."
            )
    else:
        raise ShapeError(
            f"{constraint_name} weights array must be 1D. Got shape: {weights_arr.shape}"
        )

    _check_finite(weights_arr, f"{constraint_name} weights")

    if np.any(weights_arr <= 0):
        n_invalid = int(np.sum(weights_arr <= 0))
        invalid_indices = np.where(weights_arr <= 0)[0]
        raise WeightError(
            f"Found {n_invalid} non-positive weights in {constraint_name} array. "
            f"All weights must be positive. "
            f"Non-positive weights at indices: {invalid_indices}"
        )

    return weights_arr


def check_unsupported_combinations(
    data: dict,
    constraint_type: str,
) -> None:
    """Check for unsupported constraint combinations.

    Parameters
    ----------
    data : dict
        Dictionary of all constraints
    constraint_type : str
        Type of constraint being added

    Raises
    ------
    UnsupportedCombinationError
        If unsupported combinations are detected
    """
    supported_constraint_types = {
        "value",
        "gradient",
        "normal",
        "tangent",
        "interface",
        "inequality",
        "inequality_pairs",
    }

    if constraint_type not in supported_constraint_types:
        raise UnsupportedCombinationError(
            f"Unsupported constraint type '{constraint_type}'. "
            f"Supported types are: {sorted(supported_constraint_types)}"
        )

    # Future extension point for solver-specific constraint incompatibilities.
    if not isinstance(data, dict):
        raise UnsupportedCombinationError(
            "Constraint container must be a dict mapping constraint families to arrays."
        )
