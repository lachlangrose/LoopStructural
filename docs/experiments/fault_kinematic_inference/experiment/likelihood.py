"""Gaussian marker contrasts and independent-prior analytical reference."""

from dataclasses import dataclass

import numpy as np

from .geometry import grouped_contacts


@dataclass
class LinearGaussian:
    matrix: np.ndarray
    values: np.ndarray
    sigma: np.ndarray

    def __post_init__(self):
        self.matrix = np.asarray(self.matrix, dtype=float)
        self.values = np.asarray(self.values, dtype=float)
        self.sigma = np.broadcast_to(np.asarray(self.sigma, dtype=float), self.values.shape)
        if (
            self.matrix.ndim != 2
            or self.matrix.shape[0] != len(self.values)
            or not np.isfinite(self.matrix).all()
            or not np.isfinite(self.values).all()
            or not np.isfinite(self.sigma).all()
            or np.any(self.sigma <= 0)
        ):
            raise ValueError("Missing/invalid prediction, measurement or Gaussian error scale")
        self.precision = (self.matrix / self.sigma[:, None]).T @ (self.matrix / self.sigma[:, None])
        self.information = self.matrix.T @ (self.values / self.sigma**2)

    def log_likelihood(self, candidates):
        candidates = np.atleast_2d(candidates)
        if not np.isfinite(candidates).all():
            raise ValueError("Nonfinite candidate/prediction")
        # Constants common to candidates are omitted; not an evidence estimator.
        return (
            -0.5 * np.einsum("ij,jk,ik->i", candidates, self.precision, candidates)
            + candidates @ self.information
        )

    def posterior(self, prior_mean, prior_covariance):
        prior_precision = np.linalg.inv(prior_covariance)
        covariance = np.linalg.inv(prior_precision + self.precision)
        mean = covariance @ (prior_precision @ prior_mean + self.information)
        return mean, covariance

    def diagnostics(self):
        singular = np.linalg.svd(self.matrix / self.sigma[:, None], compute_uv=False)
        rank = int(np.linalg.matrix_rank(self.matrix, tol=1e-9))
        return {
            "likelihood_rank": rank,
            "dimension": self.matrix.shape[1],
            "condition": (
                float(singular[0] / singular[-1]) if rank == self.matrix.shape[1] else None
            ),
            "singular_values": singular.tolist(),
            "weak_information": bool(np.max(singular) < 1e-8),
        }


def contact_likelihood(data, plane):
    groups = grouped_contacts(data, plane)
    contrasts, errors, nuisance = [], [], {}
    for horizon in plane.horizons:
        rows = [row for row in groups if row["horizon"] == horizon]
        weights = np.array([1 / r["variance"] for r in rows])
        means = np.array([r["mean"] for r in rows])
        walls = np.array([r["wall"] for r in rows])
        nuisance[horizon] = {
            "intercept": float(weights @ means / weights.sum()),
            "positive_fraction": float(weights @ walls / weights.sum()),
            "variance": float(1 / weights.sum()),
        }
        if set(walls) == {0, 1}:
            wall_means = [
                float(weights[walls == w] @ means[walls == w] / weights[walls == w].sum())
                for w in (0, 1)
            ]
            contrasts.append(wall_means[1] - wall_means[0])
            errors.append(np.sqrt(sum(1 / weights[walls == w].sum() for w in (0, 1))))
    if not contrasts:
        raise ValueError("No matched training horizon spans both walls")
    matrix = np.tile([plane.normal[1], -plane.normal[2]], (len(contrasts), 1))
    return LinearGaussian(matrix, contrasts, errors), nuisance, groups
