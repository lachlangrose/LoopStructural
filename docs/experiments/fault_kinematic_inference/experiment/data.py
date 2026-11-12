"""Allow-listed training access. Evaluation observations have a separate loader."""

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd
import rasterio
from scipy.interpolate import RectBivariateSpline

from .constraints import compile_constraints
from .schema import BASE, digest


class Terrain:
    """Bilinear height and surface gradients; Z is not independent XY evidence."""

    def __init__(self, path):
        with rasterio.open(path) as src:
            values = src.read(1, masked=True)
            if values.mask.any() or src.tags().get("vertical_units") != "metres":
                raise ValueError("Terrain must be complete and in metres")
            if src.crs is not None or src.transform.b != 0 or src.transform.d != 0:
                raise ValueError("Stage A requires unrotated local Cartesian terrain")
            self.x = src.transform.c + (np.arange(src.width) + 0.5) * src.transform.a
            self.y = (src.transform.f + (np.arange(src.height) + 0.5) * src.transform.e)[::-1]
            self.values = np.asarray(values)[::-1]
        self.spline = RectBivariateSpline(self.y, self.x, self.values, kx=1, ky=1)

    def height(self, x, y):
        result = self.spline.ev(y, x)
        return result.item() if np.ndim(x) == 0 and np.ndim(y) == 0 else result

    def gradient(self, x, y):
        # Central differences avoid unsupported derivatives of linear FITPACK splines.
        h = 0.5
        gx = (self.height(x + h, y) - self.height(x - h, y)) / (2 * h)
        gy = (self.height(x, y + h) - self.height(x, y - h)) / (2 * h)
        return np.column_stack([gx, gy])


@dataclass
class TrainingData:
    contacts: pd.DataFrame
    bedding: pd.DataFrame
    terrain: Terrain
    constraints: dict
    bounds: list
    hashes: dict
    fold: int


def validate_table(table, kind, bounds):
    required = ["observation_id", "source_group", "X", "Y", "Z"]
    required += (
        ["contact_id", "wall", "position_sigma_m"]
        if kind == "contacts"
        else ["nx", "ny", "nz", "orientation_sigma_degrees"]
    )
    if not set(required).issubset(table.columns) or table[required].isna().any().any():
        raise ValueError(f"{kind}: missing values/columns")
    if table.empty or not table.observation_id.is_unique:
        raise ValueError(f"{kind}: empty observations or duplicate IDs")
    numeric = [c for c in required if c not in ("observation_id", "source_group", "contact_id")]
    if not np.isfinite(table[numeric].to_numpy(dtype=float)).all():
        raise ValueError(f"{kind}: nonfinite values")
    if not (table.X.between(bounds[0], bounds[2]) & table.Y.between(bounds[1], bounds[3])).all():
        raise ValueError(f"{kind}: coordinates outside declared metre bounds")
    if kind == "contacts":
        if not table.wall.isin([-1, 1]).all() or not (table.position_sigma_m > 0).all():
            raise ValueError("Invalid wall or position error")
        if not (table.wall.to_numpy() == np.where(table.X > 0, 1, -1)).all():
            raise ValueError("Wall labels contradict the known fault")
        if (table.groupby("source_group").contact_id.nunique() > 1).any():
            raise ValueError("A source trace cannot refer to two horizons")
        if (table.groupby("source_group").wall.nunique() > 1).any():
            raise ValueError("A source trace cannot cross walls")
    else:
        if not np.allclose(np.linalg.norm(table[["nx", "ny", "nz"]], axis=1), 1, atol=1e-6):
            raise ValueError("Bedding normals must be unit length")
        if not table.orientation_sigma_degrees.between(0.01, 20).all():
            raise ValueError("Invalid bedding error")


def load_training(config, fold, dataset_root=None):
    """Read no complete source maps, held-out observations or generating coefficients."""
    root = dataset_root or BASE / "datasets" / config["dataset"]
    names = ["manifest.json", "constraints.json", "faults.geojson", "dem.tif"]
    prefix = f"splits/fold_{fold}/"
    names += [prefix + n for n in ("mask.json", "contacts_train.csv", "bedding_train.csv")]
    expected = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))
    hashes = {}
    for name in names:
        hashes[name] = digest(root / name)
        if hashes[name] != expected[name]:
            raise ValueError(f"Source hash mismatch: {name}")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["dataset_id"] != config["dataset"] or manifest["horizontal_crs"] != (
        "local Cartesian metres; not a geographic location"
    ):
        raise ValueError("Wrong dataset or physical units")
    fault = json.loads((root / "faults.geojson").read_text(encoding="utf-8"))
    if (
        fault["crs"]["properties"]["name"] != "LOCAL_CARTESIAN_METRES"
        or len(fault["features"]) != 1
        or fault["features"][0]["properties"]["geometry"] != "vertical plane x=0"
    ):
        raise ValueError("Known fault geometry does not match Stage A")
    xy = np.asarray(fault["features"][0]["geometry"]["coordinates"])
    if not np.allclose(xy[:, 0], 0):
        raise ValueError("Fault coordinates contradict x=0")
    bounds = manifest["bounds_xy_m"]
    mask = json.loads((root / prefix / "mask.json").read_text(encoding="utf-8"))
    lo, hi = mask["test_y_interval_m"]
    tables = [pd.read_csv(root / prefix / f"{kind}_train.csv") for kind in ("contacts", "bedding")]
    terrain = Terrain(root / "dem.tif")
    for kind, table in zip(("contacts", "bedding"), tables):
        validate_table(table, kind, bounds)
        if not ((table.Y < lo - mask["buffer_m"]) | (table.Y > hi + mask["buffer_m"])).all():
            raise ValueError("Training observation falls inside the held-out exclusion buffer")
        if not np.allclose(table.Z, terrain.height(table.X, table.Y), atol=0.05, rtol=0):
            raise ValueError("XY and DEM-derived Z are inconsistent")
    card = json.loads((root / "constraints.json").read_text(encoding="utf-8"))
    return TrainingData(*tables, terrain, compile_constraints(config, card), bounds, hashes, fold)
