"""Deterministic quadrature in the declared physical prior coordinates."""

import time

import numpy as np
from scipy.special import logsumexp


def normalise(log_weights):
    if not np.isfinite(log_weights).any():
        raise ValueError("No candidate has finite likelihood and prior support")
    return np.exp(log_weights - logsumexp(log_weights))


def weighted_quantile(values, weights, probabilities):
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order]) - 0.5 * weights[order]
    return np.interp(probabilities, cumulative, np.asarray(values)[order])


def moments(vectors, weights):
    mean = weights @ vectors
    delta = vectors - mean
    covariance = (delta * weights[:, None]).T @ delta
    return mean, covariance


def summarise(vectors, weights):
    mean, cov = moments(vectors, weights)
    return {
        "mean_ab_m": mean.tolist(),
        "sd_ab_m": np.sqrt(np.diag(cov)).tolist(),
        "covariance_ab_m2": cov.tolist(),
        "interval90_ab_m": [
            weighted_quantile(vectors[:, j], weights, [0.05, 0.95]).tolist() for j in range(2)
        ],
        "interval90_D_m": weighted_quantile(
            np.linalg.norm(vectors, axis=1), weights, [0.05, 0.95]
        ).tolist(),
    }


def polar_grid(problem, constraints, nd, nt, amplitude=(0, 600)):
    lo, hi = amplitude
    d = lo + (np.arange(nd) + 0.5) * (hi - lo) / nd
    if "pitch_radians" in constraints["fixed"]:
        pitch = np.array([constraints["fixed"]["pitch_radians"]])
    else:
        start, stop = constraints["pitch_bounds"]
        pitch = start + (np.arange(nt) + 0.5) * (stop - start) / nt
    dd, pp = np.meshgrid(d, pitch, indexing="ij")
    vectors = np.column_stack([(dd * np.cos(pp)).ravel(), (dd * np.sin(pp)).ravel()])
    # Midpoint cells have equal dD*dpitch measure. There is no Cartesian Jacobian here.
    weights = normalise(problem.log_likelihood(vectors))
    return vectors, weights


def refine_grid(problem, constraints, budget):
    start = time.perf_counter()
    history, previous = [], None
    total = 0
    for level in range(budget["max_levels"]):
        nd = budget["initial_D"] * 2**level
        nt = budget["initial_pitch"] * 2**level
        nodes = nd * (1 if "pitch_radians" in constraints["fixed"] else nt)
        if nodes > budget["max_nodes"] or time.perf_counter() - start > budget["seconds_per_fold"]:
            break
        vectors, weights = polar_grid(problem, constraints, nd, nt)
        summary = summarise(vectors, weights)
        mean, covariance = moments(vectors, weights)
        sd = np.sqrt(np.diag(covariance))
        # Include identifiable separation: large null-space SD cannot hide prediction error.
        projected = vectors @ problem.matrix[0]
        qmean = float(weights @ projected)
        qsd = float(np.sqrt(weights @ (projected - qmean) ** 2))
        width = np.diff(np.asarray(summary["interval90_ab_m"]), axis=1).ravel()
        qinterval = weighted_quantile(projected, weights, [0.05, 0.95])
        total += nodes
        current = (np.r_[mean, qmean], np.r_[sd, qsd], np.r_[width, np.diff(qinterval)])
        converged = False
        if previous is not None:
            mean_error = float(
                np.max(np.abs(current[0] - previous[0]) / np.maximum(current[1], 1e-10))
            )
            sd_error = float(
                np.max(np.abs(current[1] - previous[1]) / np.maximum(current[1], 1e-10))
            )
            width_error = float(
                np.max(np.abs(current[2] - previous[2]) / np.maximum(current[2], 1e-10))
            )
            converged = (
                mean_error <= budget["mean_tolerance_sd"]
                and max(sd_error, width_error) <= budget["sd_relative_tolerance"]
            )
        else:
            mean_error = sd_error = width_error = None
        history.append(
            {
                "nd": nd,
                "nt": nt if nodes != nd else 1,
                "nodes": nodes,
                "mean_change_sd": mean_error,
                "sd_relative_change": sd_error,
                "interval_width_relative_change": width_error,
            }
        )
        previous = current
        if converged:
            radii = np.linalg.norm(vectors, axis=1)
            return (
                vectors,
                weights,
                {
                    "status": "converged",
                    "history": history,
                    "full_evaluations": total,
                    "proxy_evaluations": 0,
                    "elapsed_seconds": time.perf_counter() - start,
                    "physical_prior_upper_boundary_mass_10m": float(weights[radii > 590].sum()),
                    "boundary_note": "600 m is prior support, not a data constraint",
                },
            )
    raise RuntimeError(f"Grid reference did not converge within its frozen budget: {history}")


def cartesian_gaussian_grid(problem, mean, covariance, axes):
    """Independent-prior verification target; distinct from the polar dataset prior."""
    xx, yy = np.meshgrid(*axes, indexing="ij")
    vectors = np.column_stack([xx.ravel(), yy.ravel()])
    delta = vectors - mean
    logprior = -0.5 * np.einsum("ij,jk,ik->i", delta, np.linalg.inv(covariance), delta)
    # Trapezoidal weights also support nonuniform validation axes.
    cells = []
    for axis in axes:
        weights = np.empty(len(axis))
        weights[1:-1] = (axis[2:] - axis[:-2]) / 2
        weights[0], weights[-1] = (axis[1] - axis[0]) / 2, (axis[-1] - axis[-2]) / 2
        cells.append(weights)
    measure = np.outer(*cells).ravel()
    return vectors, normalise(problem.log_likelihood(vectors) + logprior + np.log(measure))
