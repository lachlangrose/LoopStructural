"""Small signed slip equations and training-only planar nuisance estimation."""

from dataclasses import dataclass

import numpy as np

BASIS = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, -1.0]])


def restore(points, components, positive_wall, basis=BASIS):
    return np.asarray(points) - np.asarray(positive_wall)[:, None] * (basis @ components)


def solve_slip(normals, separation, sigma, basis=BASIS, direction=None):
    """Solve n.s=c. A rank-deficient minimum norm is a representative, not a unique slip."""
    matrix = np.asarray(normals) @ basis
    if direction is not None:
        unit = np.asarray(direction, dtype=float)
        unit /= np.linalg.norm(unit)
        matrix = (matrix @ unit)[:, None]
    weights = 1 / np.asarray(sigma, dtype=float)
    if not np.isfinite(matrix).all() or not (weights > 0).all():
        raise ValueError("Invalid equation or error scale")
    scaled = matrix * weights[:, None]
    solution, _, rank, singular = np.linalg.lstsq(scaled, separation * weights, rcond=1e-10)
    _, _, vt = np.linalg.svd(scaled, full_matrices=True)
    return {
        "solution": solution,
        "rank": int(rank),
        "singular_values": singular,
        "condition": float(singular[0] / singular[-1]) if rank == matrix.shape[1] else None,
        "null_basis": vt[rank:].T,
        "dimension": matrix.shape[1],
    }


@dataclass
class Plane:
    normal: np.ndarray  # nz=1 fixes the arbitrary implicit-field scale.
    slope_covariance: np.ndarray
    horizons: list


def surface_gradient(terrain, normal, x, y):
    return normal[:2] + normal[2] * terrain.gradient(np.asarray(x), np.asarray(y))


def fit_plane(data):
    """Fit plane slopes, category levels and a free separation from training evidence.

    Separation is a nuisance here: it does not select a slip direction. Synthetic
    numeric `val` labels are deliberately unused. Bedding pseudo-observation errors
    use a first-order delta method; the later likelihood is conditional on this fit.
    """
    contacts, bedding = data.contacts, data.bedding
    poles = bedding[["nx", "ny", "nz"]].to_numpy().copy()
    poles[poles[:, 2] < 0] *= -1
    if np.min(poles[:, 2]) < 0.2:
        raise ValueError("Stage A z-as-height plane is unstable for near-vertical bedding")
    slopes = poles[:, :2] / poles[:, 2, None]
    normal = np.r_[np.median(slopes, axis=0), 1.0]
    horizons = sorted(contacts.contact_id.unique())
    indices = {key: j for j, key in enumerate(horizons)}
    design = np.zeros((len(contacts), len(horizons) + 3))
    design[:, :2] = contacts[["X", "Y"]]
    design[np.arange(len(contacts)), [2 + indices[key] for key in contacts.contact_id]] = -1
    design[:, -1] = -(contacts.wall > 0).to_numpy(dtype=float)
    counts = contacts.groupby("source_group").observation_id.transform("count").to_numpy()
    bed_rows, bed_values = [], []
    for pole, slope, degrees in zip(poles, slopes, bedding.orientation_sigma_degrees):
        jac = np.array(
            [[1 / pole[2], 0, -pole[0] / pole[2] ** 2], [0, 1 / pole[2], -pole[1] / pole[2] ** 2]]
        )
        covariance = np.deg2rad(degrees) ** 2 * jac @ jac.T
        whiten = np.linalg.inv(np.linalg.cholesky(covariance))
        rows = np.zeros((2, design.shape[1]))
        rows[:, :2] = whiten
        bed_rows.extend(rows)
        bed_values.extend(whiten @ slope)
    for _ in range(5):
        gradient = surface_gradient(data.terrain, normal, contacts.X, contacts.Y)
        errors = np.sqrt(
            (contacts.position_sigma_m.to_numpy() * np.linalg.norm(gradient, axis=1)) ** 2 + 0.05**2
        ) * np.sqrt(counts)
        matrix = np.vstack([design / errors[:, None], bed_rows])
        values = np.r_[-contacts.Z.to_numpy() / errors, bed_values]
        fit, _, rank, _ = np.linalg.lstsq(matrix, values, rcond=None)
        if rank != design.shape[1]:
            raise ValueError("Training horizons do not identify a common plane and separation")
        normal = np.r_[fit[:2], 1.0]
    covariance = np.linalg.inv(matrix.T @ matrix)[:2, :2]
    return Plane(normal, covariance, horizons)


def grouped_contacts(data, plane):
    """One Gaussian trace mean per source; digitisation density is not extra evidence."""
    table = data.contacts.copy()
    gradient = surface_gradient(data.terrain, plane.normal, table.X, table.Y)
    table["field"] = table[["X", "Y", "Z"]].to_numpy() @ plane.normal
    table["variance"] = (
        table.position_sigma_m.to_numpy() * np.linalg.norm(gradient, axis=1)
    ) ** 2 + 0.05**2
    rows = []
    for source, group in table.groupby("source_group", sort=True):
        rows.append(
            {
                "source": source,
                "horizon": group.contact_id.iloc[0],
                "wall": int(group.wall.iloc[0] > 0),
                "mean": float(group.field.mean()),
                "variance": float(group.variance.mean()),
            }
        )
    return rows
