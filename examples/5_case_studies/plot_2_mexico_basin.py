"""
5b. Mexico Basin: section offsets and meshing demonstration models
===============================================================
Build any of the ten published Mexico Basin submodels using LoopStructural.
The default is North_2. This is a new interpretation of published section
contacts, not a conversion of the GemPy interpolation or a validated slip
history. Source coordinates are WGS84 / UTM 14N (EPSG:32614), in metres.

Sources: Montaño-Caro and Morales-Casique, DOI:10.1007/s12145-025-02064-9;
dataset DOI:10.5281/zenodo.16423799; and the pinned v1.0 source repository:
https://github.com/Nauj29/GemPy_Model_Mexico_Basin . The download is about
30 MB. Source data stay in a local cache. Upstream LICENSE and Zenodo say
CC BY 4.0, but the README also says noncommercial and the paper says MIT
for code. This example does not resolve that inconsistency or redistribute
the dataset. Source code is not executed.

Fault displacement is estimated separately for each horizon from paired
cutoffs in the ORIGINAL sections. Continuous contacts and synthetic fault
extensions have zero offset. No arbitrary uniform throw is assigned.
Dip slip is inferred assuming the apparent section bedding dip has no
transverse component; strike slip cannot be determined from these inputs.
Offsets are interpolated along strike, with a 5 km taper beyond the last
section. Missing cutoff evidence is recorded as unresolved, with zero slip.
Independent horizons allow growth-fault offsets without fabricated unit
thicknesses. Their age order follows the source notebooks, and younger
units truncate older ones. Faults do not displace one another; simultaneous
restoration uses their listed order, an explicit modelling assumption.

Install ``pyshp tifffile matplotlib pyvista`` alongside LoopStructural.
Run ``python examples/5_case_studies/plot_2_mexico_basin.py --output validation/mexico``.
Use ``--zone North_3`` for another case, or ``--all`` for the suite. No
network access occurs on import; cached runs also work with ``--offline``.
Exports include implicit fields, unit IDs, fault-block IDs, fault meshes,
separate contact meshes, section figures and displacement diagnostics.
Contact meshes omit cells crossing an active fault, leaving resolution-
dependent gaps instead of triangles bridging a scalar discontinuity.
They are meshing INPUTS, not conforming tetrahedral volume meshes.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import gettempdir
from urllib.request import urlopen
from zipfile import ZipFile

import numpy as np
import pandas as pd
from scipy.interpolate import RegularGridInterpolator

from LoopStructural import GeologicalModel
from LoopStructural.modelling.features import AnalyticalGeologicalFeature
from LoopStructural.modelling.features.fault import FaultDisplacement, FaultSegment

COMMIT = "32e1ee55a656690150c3a1cce399e809611e263d"
ARCHIVE_SHA256 = "f33f9c8e61d2f9dd7d258d9267b0698ffd180345678fd34aa40efefe9d692bc4"
SOURCE_URL = f"https://codeload.github.com/Nauj29/GemPy_Model_Mexico_Basin/zip/{COMMIT}"
# Youngest to oldest; the first tuple is the horizon order, the second the faults.
ZONES = {
    "Extra": (("Neogene_pyro", "Neogene_Volcanic", "Paleogene_Volcanic"), ("ToF", "F6")),
    "North_1": (
        (
            "Quaternary_Lac",
            "Quaternary_alluvial",
            "Neogene_Lac",
            "Quaternary_Pyro2",
            "Quaternary_volcanic",
            "Neogene_pyro",
            "Neogene_Volcanic",
            "Paleogene_Volcanic",
        ),
        ("MxF", "ToF", "NF", "TF", "F9", "F10", "F6"),
    ),
    "North_2": (
        (
            "Quaternary_Lac",
            "Quaternary_alluvial",
            "Neogene_Lac",
            "Quaternary_volcanic",
            "Quaternary_Pyro2",
            "Neogene_Volcanic",
            "Paleogene_Volcanic",
        ),
        ("ToF", "TF", "NF", "TxF", "ATF"),
    ),
    "North_3": (
        (
            "Quaternary_alluvial",
            "Neogene_Lac",
            "Quaternary_Pyro2",
            "Quaternary_volcanic",
            "Neogene_Volcanic",
            "Paleogene_Volcanic",
        ),
        ("ATF", "HF", "ChF"),
    ),
    "North_4": (
        (
            "Quaternary_alluvial",
            "Neogene_Lac",
            "Quaternary_Pyro",
            "Quaternary_volcanic",
            "Neogene_Volcanic",
            "Paleogene_Volcanic",
        ),
        ("TxF", "ATF"),
    ),
    "North_5": (
        (
            "Quaternary_alluvial",
            "Neogene_Lac",
            "Quaternary_Pyro",
            "Quaternary_volcanic",
            "Neogene_Volcanic",
            "Paleogene_Volcanic",
        ),
        ("TF", "ToF", "NF"),
    ),
    "Middle_1": (
        (
            "Quaternary_Lac",
            "Quaternary_alluvial",
            "Quaternary_volcanic",
            "Quaternary_Pyro2",
            "Neogene_pyro",
            "Neogene_Volcanic",
            "Paleogene_Volcanic",
        ),
        ("MxF", "F8", "F1", "F2", "F3", "F4", "F7"),
    ),
    "Middle_2": (
        (
            "Quaternary_Lac",
            "Quaternary_alluvial",
            "Quaternary_volcanic",
            "Quaternary_Pyro2",
            "Neogene_pyro",
            "Neogene_Volcanic",
            "Paleogene_Volcanic",
        ),
        ("F1", "F2", "F3", "F4", "F7", "F8"),
    ),
    "South_1": (
        ("Quaternary_volcanic", "Neogene_pyro", "Neogene_Volcanic", "Paleogene_Volcanic"),
        ("XiF", "XoF", "F11", "F12", "F13"),
    ),
    "South_2": (
        (
            "Quaternary_Lac",
            "Quaternary_alluvial",
            "Quaternary_volcanic",
            "Quaternary_Pyro2",
            "Neogene_pyro",
            "Neogene_Volcanic",
            "Paleogene_Volcanic",
        ),
        ("XiF", "XoF", "F11", "F12", "F13"),
    ),
}
XYZ = ["X", "Y", "Z"]
COLOURS = {
    "Quaternary_Lac": "#fee08b",
    "Quaternary_alluvial": "#fdae61",
    "Neogene_Lac": "#e6f598",
    "Quaternary_Pyro": "#d53e4f",
    "Quaternary_Pyro2": "#d53e4f",
    "Quaternary_volcanic": "#abdda4",
    "Neogene_pyro": "#f46d43",
    "Neogene_Volcanic": "#3288bd",
    "Paleogene_Volcanic": "#5e4fa2",
    "Older_substrate": "#999999",
}


def pole(dip, azimuth):
    """Return upward unit normals from dip and clockwise-from-north dip direction."""
    dip, azimuth = np.deg2rad(dip), np.deg2rad(azimuth)
    return np.column_stack(
        [np.sin(dip) * np.sin(azimuth), np.sin(dip) * np.cos(azimuth), np.cos(dip)]
    )


@dataclass
class Inputs:
    """Published inputs and section geometries for one demonstration domain."""

    zone: str
    contacts: pd.DataFrame
    orientations: pd.DataFrame
    dips: list
    traces: dict
    sections: dict
    origin: np.ndarray
    maximum: np.ndarray
    terrain: object
    archive: Path


def load_inputs(zone="North_2", directory=None, *, offline=False):
    """Read a checksum-verified archive without executing or extracting source code."""
    if zone not in ZONES:
        raise ValueError(f"Unknown zone {zone}; choose one of {tuple(ZONES)}")
    directory = Path(directory or Path(gettempdir()) / "loopstructural-examples" / "mexico-basin")
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / f"{COMMIT}.zip"
    if not archive.exists():
        if offline:
            raise FileNotFoundError(
                f"Dataset is not cached at {archive}; run once without --offline"
            )
        print("Downloading the pinned Mexico Basin dataset (about 30 MB).", flush=True)
        with urlopen(SOURCE_URL, timeout=120) as response:
            content = response.read()
        if sha256(content).hexdigest() != ARCHIVE_SHA256:
            raise ValueError("Downloaded Mexico Basin archive has an unexpected SHA-256")
        archive.write_bytes(content)
    content = archive.read_bytes()
    if sha256(content).hexdigest() != ARCHIVE_SHA256:
        raise ValueError(f"Cached archive {archive} differs from the pinned source")
    import shapefile
    import tifffile

    region = "North" if zone == "Extra" else zone.split("_")[0]
    table_zone = "North_1" if zone == "Extra" else zone
    with ZipFile(BytesIO(content)) as zipped:
        prefix = f"GemPy_Model_Mexico_Basin-{COMMIT}/"

        def read(name):
            return zipped.read(prefix + name)

        def shapes(stem):
            with shapefile.Reader(
                shp=BytesIO(read(stem + ".shp")),
                dbf=BytesIO(read(stem + ".dbf")),
                encoding="utf-8",
                encodingErrors="replace",
            ) as reader:
                return [
                    (
                        record.record.as_dict(),
                        np.asarray(record.shape.points, float),
                        list(record.shape.parts),
                    )
                    for record in reader.iterShapeRecords()
                ]

        contacts = pd.read_csv(BytesIO(read(f"Tables/{region}/Clipped/{table_zone}_Int.txt")))
        orientations = pd.read_csv(BytesIO(read(f"Tables/{region}/Clipped/{table_zone}_Ori.txt")))
        dips = [record for record, _, _ in shapes(f"Shapefiles/{region}/Dip")]
        traces = {
            record["name"]: points for record, points, _ in shapes("Dataset/Surface/Sections")
        }
        sections = {
            name: shapes(f"Dataset/Hydrogeological_Units/Lineal/{name}")
            for name in sorted({d["section_id"] for d in dips})
            if prefix + f"Dataset/Hydrogeological_Units/Lineal/{name}.shp" in zipped.namelist()
        }
        boundary = next(
            points
            for record, points, _ in shapes("Shapefiles/Model_Zones")
            if record["Zones"] == zone
        )
        origin = np.r_[boundary.min(axis=0), contacts.Z.min() - 50.0]
        maximum = np.r_[boundary.max(axis=0), contacts.Z.max() + 50.0]
        with tifffile.TiffFile(BytesIO(read("Dataset/Raster/cdmx.tif"))) as raster:
            page = raster.pages[0]
            elevation = page.asarray().astype(float)
            dx, dy, _ = page.tags["ModelPixelScaleTag"].value
            _, _, _, x0, y0, _ = page.tags["ModelTiepointTag"].value
            nodata = page.tags.get("GDAL_NODATA")
            if nodata is not None:
                # The source int16 raster declares 32767 as nodata. Some
                # tifffile versions warn while parsing that tag; use the
                # explicit tag value after converting elevations to float.
                elevation[elevation == float(nodata.value)] = np.nan
            x = x0 + (np.arange(elevation.shape[1]) + 0.5) * dx
            y = y0 - (np.arange(elevation.shape[0]) + 0.5) * dy
            interpolation = RegularGridInterpolator(
                (y[::-1], x), elevation[::-1], bounds_error=False, fill_value=np.nan
            )

    def terrain(xy):
        return interpolation(np.asarray(xy)[:, [1, 0]])

    return Inputs(
        zone, contacts, orientations, dips, traces, sections, origin, maximum, terrain, archive
    )


def section_xyz(points, trace):
    """Convert section distance/elevation to UTM coordinates along its trace."""
    direction = trace[-1] - trace[0]
    direction /= np.linalg.norm(direction)
    return np.column_stack(
        [trace[0] + np.asarray(points)[:, :1] * direction, np.asarray(points)[:, 1]]
    )


def cutoff_pair(lines, fault_name, unit, *, tolerance=200.0):
    """Find two wall cutoffs against an original section fault, or a continuous crossing.

    Return section coordinates and local bedding slopes. Endpoints are
    extrapolated along their adjacent contact segment to the original fault
    line, by no more than ``tolerance`` metres. Missing original faults are
    identified separately as synthetic extensions by the caller.
    """
    faults = [points for attrs, points, _ in lines if attrs.get("Uni") == fault_name]
    if not faults:
        return None
    fault = max(faults, key=lambda p: np.linalg.norm(p[-1] - p[0]))
    a, b = fault[0], fault[-1]
    tangent = (b - a) / np.linalg.norm(b - a)
    normal = np.array([-tangent[1], tangent[0]])
    if normal[0] < 0:
        normal *= -1
    cutoffs = {-1: [], 1: []}
    crossings = []
    for attrs, points, parts in lines:
        if attrs.get("Uni") != unit:
            continue
        for start, stop in zip(parts, [*parts[1:], len(points)]):
            vertices = points[start:stop]
            if len(vertices) < 2:
                continue
            distances = (vertices - a) @ normal
            for p, q, dp, dq in (
                (vertices[0], vertices[1], distances[0], distances[1]),
                (vertices[-1], vertices[-2], distances[-1], distances[-2]),
            ):
                delta = p - q
                denominator = delta @ normal
                if abs(dp) <= tolerance and abs(denominator) > 1e-8 and abs(delta[0]) > 1e-8:
                    cutoff = p - dp / denominator * delta
                    if np.linalg.norm(cutoff - p) <= tolerance:
                        side = 1 if dq > 0 else -1
                        cutoffs[side].append((cutoff, delta[1] / delta[0], abs(dp)))
            for p, q, dp, dq in zip(vertices[:-1], vertices[1:], distances[:-1], distances[1:]):
                if dp * dq < 0 and abs(q[0] - p[0]) > 1e-8:
                    crossings.append((p + dp / (dp - dq) * (q - p), (q[1] - p[1]) / (q[0] - p[0])))
    if cutoffs[-1] and cutoffs[1]:
        minus = min(cutoffs[-1], key=lambda p: p[2])
        plus = min(cutoffs[1], key=lambda p: p[2])
        return minus[0], plus[0], (minus[1] + plus[1]) / 2
    if crossings:
        point, slope = crossings[0]
        return point, point.copy(), slope
    return None


def restoration_slip(negative_cutoff, positive_cutoff, bedding_normal, updip):
    """Infer slip that restores paired contacts onto one local bedding plane.

    ``updip`` is the RESTORATION direction on the positive wall, rather
    than the forward normal-fault movement. Correcting for bedding dip
    accounts for horizontal heave; vertical throw alone is not net slip.
    """
    denominator = np.dot(bedding_normal, updip)
    if abs(denominator) <= 0.1:
        return np.nan
    return float(np.dot(bedding_normal, negative_cutoff - positive_cutoff) / denominator)


def estimate_displacements(inputs):
    """Estimate signed restoration slip, retaining measured zero and unresolved cases."""
    horizons, names = ZONES[inputs.zone]
    records = []
    for dip in inputs.dips:
        name, section = dip["fault_id"], dip["section_id"]
        if name not in names or section not in inputs.sections:
            continue
        trace = inputs.traces[section]
        direction = trace[-1] - trace[0]
        direction /= np.linalg.norm(direction)
        normal = pole([dip["true_dip"]], [dip["dip_direct"]])[0]
        updip = np.array([0.0, 0.0, 1.0]) - normal[2] * normal
        updip /= np.linalg.norm(updip)
        lines = inputs.sections[section]
        synthetic = not any(attrs.get("Uni") == name for attrs, _, _ in lines)
        for unit in horizons:
            pair = cutoff_pair(lines, name, unit) if not synthetic else None
            record = {
                "fault": name,
                "unit": unit,
                "section": section,
                "X": trace[0, 0] + dip["distance"] * direction[0],
                "Y": trace[0, 1] + dip["distance"] * direction[1],
                "Z": dip["elevation"],
                "status": "synthetic_zero" if synthetic else "unresolved",
                "slip_m": 0.0,
                "throw_m": 0.0,
            }
            if pair is not None:
                left, right, slope = pair
                xyz = section_xyz(np.array([left, right]), trace)
                # ``cutoff_pair``'s positive wall is on the +distance side.
                # Align it with the upward 3D fault normal used by LoopStructural.
                if normal[:2] @ direction < 0:
                    xyz = xyz[::-1]
                bedding_normal = np.r_[-slope * direction, 1.0]
                slip = restoration_slip(xyz[0], xyz[1], bedding_normal, updip)
                if np.isfinite(slip):
                    if abs(slip) <= 2.0:
                        slip = 0.0
                    record.update(
                        status="continuous" if slip == 0 else "paired_cutoffs",
                        slip_m=float(slip),
                        throw_m=float(slip * updip[2]),
                    )
                    record.update(
                        {
                            f"{wall}_{axis}": float(value)
                            for wall, point in zip(("negative_cutoff", "positive_cutoff"), xyz)
                            for axis, value in zip(XYZ, point)
                        }
                    )
            records.append(record)
    return pd.DataFrame(records)


@dataclass
class StrikeProfile:
    """Interpolate signed slip ratios along strike, tapering outside section coverage."""

    positions: np.ndarray
    values: np.ndarray
    taper: float = 5000.0

    def __call__(self, positions):
        x = np.r_[self.positions[0] - self.taper, self.positions, self.positions[-1] + self.taper]
        y = np.r_[0.0, self.values, 0.0]
        return np.interp(positions, x, y, left=0.0, right=0.0)


def positive_wall(values):
    """Move only the positive wall; there is no hidden factor of two in net slip."""
    return (np.asarray(values) > 0).astype(float)


@dataclass
class SurfaceOnlyFaultBuilder:
    """Keep the interpolated surface current when the other frame axes are analytical.

    The usual frame builder updates all three interpolants. Coordinates 1
    and 2 have been replaced with exact analytical fields here, so their
    unused interpolants must not be solved as fault dependencies.
    """

    frame_builder: object

    def up_to_date(self, callback=None):
        self.frame_builder.builders[0].up_to_date(callback=callback)

    def __getattr__(self, name):
        return getattr(self.frame_builder, name)


def build_model(inputs, *, nelements=30000):
    """Build independent basal fields with horizon-specific fault restorations."""
    horizons, fault_names = ZONES[inputs.zone]
    picks = estimate_displacements(inputs)
    contacts = inputs.contacts.drop_duplicates(subset=["formation", *XYZ]).copy()
    orientations = inputs.orientations.drop_duplicates(
        subset=["formation", *XYZ, "dip", "azimuth"]
    ).copy()
    normals = pole(orientations.dip.to_numpy(), orientations.azimuth.to_numpy())
    orientations[["nx", "ny", "nz"]] = normals * orientations.polarity.to_numpy()[:, None]
    orientations["feature_name"] = orientations.formation
    contacts["feature_name"] = contacts.formation
    contacts["val"] = 0.0
    # Retain a buffer of actual section constraints, as in the source submodels.
    data = pd.concat([contacts, orientations], ignore_index=True)
    model = GeologicalModel(inputs.origin, inputs.maximum)
    model.data = data
    model.dtm = inputs.terrain
    geometries = {}
    for name in fault_names:
        rows = orientations.loc[orientations.formation == name]
        if rows.empty:
            raise ValueError(f"No source orientation constrains fault {name}")
        normal = rows[["nx", "ny", "nz"]].mean().to_numpy(copy=True)
        normal /= np.linalg.norm(normal)
        updip = np.array([0.0, 0.0, 1.0]) - normal[2] * normal
        updip /= np.linalg.norm(updip)
        strike = np.cross(normal, updip)
        strike /= np.linalg.norm(strike)
        centre = rows[XYZ].mean().to_numpy()
        # Geometry-only faults carry zero slip. The actual events are the
        # horizon-specific FaultSegments attached to each foliation below.
        geometry = model.create_and_add_fault(
            name,
            0.0,
            faults=[],
            fault_normal_vector=normal,
            fault_slip_vector=updip,
            nelements=4000,
            force_mesh_geometry=True,
            fault_buffer=0.3,
            interpolatortype="FDI",
            solver="lsmr",
            tol=1e-7,
        )
        geometry[0].builder.up_to_date()
        # Keep the interpolated fault surface, but make slip and along-strike
        # coordinates exact. Up-dip movement leaves along-strike slip unchanged.
        geometry[1] = AnalyticalGeologicalFeature(name + "_updip", updip, centre)
        geometry[2] = AnalyticalGeologicalFeature(name + "_strike", strike, centre)
        geometry.builder = SurfaceOnlyFaultBuilder(geometry.builder)
        geometries[name] = geometry
    horizon_faults = {}
    for unit in horizons:
        active = []
        for name, geometry in geometries.items():
            rows = picks.loc[(picks.fault == name) & (picks.unit == unit)].copy()
            if rows.empty or not np.any(rows.slip_m != 0):
                continue
            positions = geometry[2].evaluate_value(rows[XYZ].to_numpy())
            # Convert section-local up-dip slip to the common mean up-dip frame
            # while retaining the inferred vertical throw.
            slips = rows.throw_m.to_numpy() / geometry[1].vector[2]
            profile_data = (
                pd.DataFrame({"position": positions, "slip": slips})
                .groupby("position", sort=True)
                .slip.median()
            )
            magnitude = float(np.max(np.abs(profile_data.to_numpy())))
            profile = StrikeProfile(
                profile_data.index.to_numpy(), profile_data.to_numpy() / magnitude
            )
            event = FaultSegment(
                f"{name}__{unit}",
                list(geometry.features),
                displacement=magnitude,
                steps=1,
                model=model,
            )
            event.builder = geometry.builder
            event.faultfunction = FaultDisplacement(gx=positive_wall, gz=profile, scale=1.0)
            active.append(event)
        horizon_faults[unit] = active
        print(f"Building {inputs.zone}: {unit} ({len(active)} displacement fields)", flush=True)
        feature = model.create_and_add_foliation(
            unit,
            faults=active,
            interpolatortype="FDI",
            nelements=nelements,
            buffer=0.3,
            solver="lsmr",
            tol=1e-7,
            cpw=20.0,
            npw=1.0,
        )
        if unit != horizons[-1]:
            model.add_unconformity(feature, 0.0)
        feature.builder.up_to_date()
    column = model.stratigraphic_column
    column.clear(basement=False)
    substrate = column.add_unit("Older_substrate", thickness=1.0, colour=COLOURS["Older_substrate"])
    base = column.add_unit(horizons[-1], thickness=np.inf, colour=COLOURS[horizons[-1]])
    for unit in reversed(horizons[:-1]):
        column.add_unconformity("Base " + unit)
        column.add_unit(unit, thickness=np.inf, colour=COLOURS[unit])
    groups = column.get_groups()
    for group, unit in zip(groups, horizons):
        column.group_mapping[group.name] = unit
    substrate.min_value, substrate.max_value = -np.inf, 0.0
    base.min_value, base.max_value = 0.0, np.inf
    return model, picks, horizon_faults


def unit_names(model):
    """Return names in the same ID order as GeologicalModel.evaluate_model."""
    return [
        unit.name
        for group in reversed(model.stratigraphic_column.get_groups())
        for unit in group.units
    ]


def displacement_checks(model, inputs, picks, horizon_faults):
    """Verify signed net movement across each active fault at section locations.

    Locate the interpolated fault by bracketing its zero along its mean
    normal. Probe both sides by one metre and check the actual restoration
    operator, including its along-strike profile, against its intended slip.
    This is a numerical check, not independent geological validation.
    """
    records = []
    for unit, events in horizon_faults.items():
        for event in events:
            name = event.name.split("__")[0]
            geometry = model[name]
            normal = geometry.builder.fault_normal_vector
            rows = picks.loc[(picks.fault == name) & (picks.unit == unit)]
            points = rows[XYZ].to_numpy()
            inside = (
                (points[:, :2] >= inputs.origin[:2]) & (points[:, :2] <= inputs.maximum[:2])
            ).all(axis=1)
            points = points[inside]
            if len(points) == 0:
                continue
            lower, upper = points - 5000 * normal, points + 5000 * normal
            a = geometry[0].evaluate_value(lower)
            b = geometry[0].evaluate_value(upper)
            valid = np.isfinite(a) & np.isfinite(b) & (a < 0) & (b > 0)
            lower, upper = lower[valid], upper[valid]
            for _ in range(28):
                middle = (lower + upper) / 2
                positive = geometry[0].evaluate_value(middle) > 0
                upper[positive] = middle[positive]
                lower[~positive] = middle[~positive]
            on_fault = (lower + upper) / 2
            positive, negative = on_fault + normal, on_fault - normal
            pos_movement = event.apply_to_points(positive) - positive
            neg_movement = event.apply_to_points(negative) - negative
            intended_slip = event.displacement * event.faultfunction.gz(
                event[2].evaluate_value(positive)
            )
            expected = intended_slip[:, None] * event[1].vector
            error = np.linalg.norm((pos_movement - neg_movement) - expected, axis=1)
            if not np.isfinite(error).all() or np.any(error > 1e-5):
                raise RuntimeError(f"Incorrect displacement sign or magnitude for {event.name}")
            for location, actual, target, residual in zip(
                on_fault, pos_movement - neg_movement, expected, error
            ):
                records.append(
                    {
                        "fault": name,
                        "unit": unit,
                        "X": location[0],
                        "Y": location[1],
                        "Z": location[2],
                        "expected_throw_m": target[2],
                        "actual_throw_m": actual[2],
                        "net_slip_m": float(np.linalg.norm(actual)),
                        "vector_error_m": residual,
                    }
                )
    return pd.DataFrame(
        records,
        columns=[
            "fault",
            "unit",
            *XYZ,
            "expected_throw_m",
            "actual_throw_m",
            "net_slip_m",
            "vector_error_m",
        ],
    )


def sample_fields(model, points, horizons, *, mask_terrain=True):
    """Sample reusable implicit fields and classify units in source coordinates."""
    values = {unit: model[unit].evaluate_value(points, ignore_regions=True) for unit in horizons}
    names = unit_names(model)
    ids = np.full(len(points), names.index("Older_substrate"), dtype=np.int32)
    # Oldest first so young cover wins at an intersection.
    for index in reversed(range(len(horizons))):
        ids[values[horizons[index]] >= 0] = names.index(horizons[index])
    valid = np.isfinite(np.column_stack(list(values.values()))).all(axis=1)
    if mask_terrain:
        height = model.dtm(points[:, :2])
        valid &= np.isfinite(height) & (points[:, 2] <= height)
    ids[~valid] = -1
    return values, ids


def export_model(model, inputs, picks, horizon_faults, directory, *, dimensions=(81, 81, 35)):
    """Write implicit fields, block labels, nonbridging surfaces and diagnostics."""
    import pyvista as pv

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    horizons, fault_names = ZONES[inputs.zone]
    image = pv.ImageData(
        dimensions=dimensions,
        origin=inputs.origin,
        spacing=(inputs.maximum - inputs.origin) / (np.asarray(dimensions) - 1),
    )
    grid = pv.StructuredGrid()
    grid.points = image.points.astype(np.float64)
    grid.dimensions = dimensions
    fields, _ = sample_fields(model, grid.points, horizons)
    for name, field in fields.items():
        grid.point_data["base_" + name] = field
        restored = grid.points.copy()
        for event in horizon_faults[name]:
            restored = event.apply_to_points(restored)
        grid.point_data["restoration_" + name] = restored - grid.points
    grid.point_data["terrain_clearance"] = inputs.terrain(grid.points[:, :2]) - grid.points[:, 2]
    volume = grid.cast_to_unstructured_grid()
    corners = volume.cell_connectivity.reshape(-1, 8)
    centres = grid.cell_centers().points
    _, ids = sample_fields(model, centres, horizons)
    grid.cell_data["unit_id"] = ids
    block_ids = np.zeros(len(centres), dtype=np.int32)
    crossing = {}
    surfaces = {}
    for index, name in enumerate(fault_names):
        geometry = model[name]
        distances = geometry[0].evaluate_value(grid.points)
        grid.point_data["fault_" + name] = distances
        volume.point_data["fault_" + name] = distances
        block_ids |= (geometry[0].evaluate_value(centres) > 0).astype(np.int32) << index
        v = distances[corners]
        crossing[name] = (v.min(axis=1) <= 0) & (v.max(axis=1) >= 0)
        surfaces["fault_" + name] = grid.contour([0.0], scalars="fault_" + name)
    grid.cell_data["fault_block_id"] = block_ids
    grid.field_data["crs"] = ["EPSG:32614"]
    grid.field_data["coordinate_units"] = ["metres"]
    grid.save(directory / "implicit_fields.vts")
    grid.threshold([-0.5, len(horizons) + 0.5], scalars="unit_id").save(
        directory / "geological_block.vtu"
    )
    for index, unit in enumerate(horizons):
        keep = np.ones(len(corners), dtype=bool)
        for event in horizon_faults[unit]:
            name = event.name.split("__")[0]
            # Do not contour through a discontinuity. Even a vanishing throw
            # retains a conservative grid-sized exclusion at the fault.
            keep &= ~crossing[name]
        surface = volume.extract_cells(keep).contour([0.0], scalars="base_" + unit)
        for younger in horizons[:index]:
            surface = surface.clip_scalar(scalars="base_" + younger, value=0.0, invert=True)
        surfaces["base_" + unit] = surface
    records = []
    for name, surface in surfaces.items():
        if surface.n_cells:
            surface = surface.clip_scalar(
                scalars="terrain_clearance", value=0.0, invert=False
            ).triangulate()
        if surface.n_cells:
            if name.startswith("base_"):
                unit = name.removeprefix("base_")
                triangles = surface.faces.reshape(-1, 4)[:, 1:]
                for event in horizon_faults[unit]:
                    values = surface.point_data["fault_" + event.name.split("__")[0]][triangles]
                    bridges = (values.min(axis=1) < -1e-8) & (values.max(axis=1) > 1e-8)
                    if bridges.any():
                        raise RuntimeError(f"Contact mesh {name} bridges {event.name}")
            surface.clear_data()
            surface.field_data["crs"] = ["EPSG:32614"]
            surface.save(directory / (name + ".vtp"))
        else:
            # A rerun at another resolution can remove a previously visible
            # contact; do not leave a stale surface beside the new inventory.
            (directory / (name + ".vtp")).unlink(missing_ok=True)
        records.append(
            {
                "surface": name,
                "points": surface.n_points,
                "triangles": surface.n_cells,
                "file": name + ".vtp" if surface.n_cells else "",
            }
        )
    pd.DataFrame(records).to_csv(directory / "surface_inventory.csv", index=False)
    picks.to_csv(directory / "fault_displacement_picks.csv", index=False)
    checks = displacement_checks(model, inputs, picks, horizon_faults)
    checks.to_csv(directory / "fault_displacement_checks.csv", index=False)
    fit = []
    for unit in horizons:
        rows = inputs.contacts.loc[inputs.contacts.formation == unit, XYZ].drop_duplicates()
        residuals = model[unit].evaluate_value(rows.to_numpy(), ignore_regions=True)
        inside = ((rows.to_numpy() >= inputs.origin) & (rows.to_numpy() <= inputs.maximum)).all(
            axis=1
        )
        fit.append(
            {
                "unit": unit,
                "contacts": len(rows),
                "finite": int(np.isfinite(residuals).sum()),
                "contacts_inside_domain": int(inside.sum()),
                "finite_inside_domain": int(np.isfinite(residuals[inside]).sum()),
                "median_abs_scalar_residual": float(np.nanmedian(abs(residuals))),
            }
        )
    pd.DataFrame(fit).to_csv(directory / "contact_fit.csv", index=False)
    metadata = {
        "zone": inputs.zone,
        "source_commit": COMMIT,
        "archive_sha256": ARCHIVE_SHA256,
        "crs": "EPSG:32614",
        "units": unit_names(model),
        "unit_ids": dict(enumerate(unit_names(model))),
        "fault_block_bits": dict(enumerate(fault_names)),
        "origin": inputs.origin.tolist(),
        "maximum": inputs.maximum.tolist(),
        "dimensions": list(dimensions),
        "displacement_check_count": len(checks),
        "maximum_displacement_vector_error_m": float(checks.vector_error_m.max())
        if len(checks)
        else None,
        "fault_events": [
            {
                "fault": event.name.split("__")[0],
                "unit": unit,
                "slip_scale_m": event.displacement,
                "restoration_direction": event[1].vector.tolist(),
                "strike_direction": event[2].vector.tolist(),
                "frame_origin": event[2].origin.tolist(),
                "strike_positions_m": event.faultfunction.gz.positions.tolist(),
                "signed_slip_ratios": event.faultfunction.gz.values.tolist(),
                "end_taper_m": event.faultfunction.gz.taper,
            }
            for unit, events in horizon_faults.items()
            for event in events
        ],
        "assumptions": [
            "Horizon-specific dip slip inferred from original section cutoffs, not measured slip history",
            "No transverse bedding dip or strike slip inferred",
            "Unresolved offsets use zero slip",
            "No fault-fault offsets; event ordering is the listed order",
            "Linear along-strike interpolation and 5 km end taper",
            "Source notebook horizon order with erosional priority",
            "Contact surfaces omit fault-crossing grid cells; not a conforming volume mesh",
        ],
        "licence_note": "Upstream LICENSE/Zenodo: CC BY 4.0; README also says noncommercial; paper says MIT for code. Resolve before redistributing source data.",
    }
    (directory / "model.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    plot_sections(model, inputs, picks, directory)
    plot_block(grid, inputs, unit_names(model), directory)
    return grid, pd.DataFrame(records)


def plot_block(grid, inputs, names, directory):
    """Save a three-dimensional preview without changing exported UTM coordinates."""
    import pyvista as pv

    block = grid.threshold([-0.5, len(names) - 0.5], scalars="unit_id")
    display = block.copy()
    display.points = (display.points - [inputs.origin[0], inputs.origin[1], 0]) / 1000
    viewer = pv.Plotter(off_screen=True, window_size=(1400, 900))
    try:
        viewer.set_background("white")
        viewer.add_mesh(
            display,
            scalars="unit_id",
            cmap=[COLOURS[n] for n in names],
            clim=(-0.5, len(names) - 0.5),
            show_scalar_bar=False,
        )
        for name in ZONES[inputs.zone][1]:
            path = Path(directory) / f"fault_{name}.vtp"
            if path.exists():
                surface = pv.read(path)
                surface.points = (surface.points - [inputs.origin[0], inputs.origin[1], 0]) / 1000
                viewer.add_mesh(surface, color="#202020", opacity=0.25)
        viewer.add_legend(
            [(n.replace("_", " "), COLOURS[n]) for n in names],
            bcolor="white",
            face="rectangle",
            size=(0.25, 0.25),
        )
        viewer.add_text(f"Mexico Basin | {inputs.zone}", color="black", font_size=14)
        viewer.show_grid(
            xtitle="Easting from origin (km)",
            ytitle="Northing from origin (km)",
            ztitle="Elevation (km)",
            color="black",
            font_size=10,
            n_xlabels=3,
            n_ylabels=3,
            n_zlabels=3,
            fmt="%.1f",
        )
        viewer.view_isometric()
        viewer.show(screenshot=str(Path(directory) / "model_preview.png"))
    finally:
        viewer.close()


def plot_sections(model, inputs, picks, directory):
    """Plot geological cross-sections and the inferred horizon-dependent throws."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap

    horizons = ZONES[inputs.zone][0]
    units = unit_names(model)
    cmap = ListedColormap([COLOURS[u] for u in units])
    norm = BoundaryNorm(np.arange(len(units) + 1) - 0.5, len(units))
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), constrained_layout=True)
    for ax, fraction in zip(axes[:2], (0.35, 0.7)):
        x = np.linspace(inputs.origin[0], inputs.maximum[0], 240)
        z = np.linspace(inputs.origin[2], inputs.maximum[2], 100)
        xx, zz = np.meshgrid(x, z)
        y = inputs.origin[1] + fraction * (inputs.maximum[1] - inputs.origin[1])
        points = np.c_[xx.ravel(), np.full(xx.size, y), zz.ravel()]
        _, ids = sample_fields(model, points, horizons)
        ax.pcolormesh(
            (xx - inputs.origin[0]) / 1000,
            zz / 1000,
            np.ma.masked_less(ids.reshape(xx.shape), 0),
            cmap=cmap,
            norm=norm,
            shading="auto",
        )
        for name in ZONES[inputs.zone][1]:
            field = model[name][0].evaluate_value(points).reshape(xx.shape)
            if np.nanmin(field) < 0 < np.nanmax(field):
                ax.contour(
                    (xx - inputs.origin[0]) / 1000,
                    zz / 1000,
                    field,
                    [0],
                    colors="black",
                    linewidths=0.8,
                )
        ax.set(
            xlabel="Easting from origin (km)",
            ylabel="Elevation (km)",
            title=f"{inputs.zone}: northing {y:.0f} m",
        )
    measured = picks.loc[picks.status == "paired_cutoffs"]
    for unit, rows in measured.groupby("unit"):
        axes[2].scatter(rows.Y / 1000, rows.throw_m, label=unit, color=COLOURS[unit], s=18)
    axes[2].axhline(0, color="black", linewidth=0.5)
    axes[2].set(
        xlabel="Section northing (km)",
        ylabel="Signed inferred throw (m)",
        title="Original section cutoffs; positive = restore positive wall upward",
    )
    axes[2].legend(fontsize=8, ncol=3)
    fig.savefig(Path(directory) / "sections_and_throws.png", dpi=150)
    plt.close(fig)


def run_example(
    zone="North_2",
    output_directory=None,
    *,
    data_directory=None,
    offline=False,
    nelements=30000,
    dimensions=(81, 81, 35),
):
    """Build one reproducible case and return the model and its meshing diagnostics."""
    inputs = load_inputs(zone, data_directory, offline=offline)
    model, picks, horizon_faults = build_model(inputs, nelements=nelements)
    output_directory = Path(output_directory or Path("validation") / "mexico_basin" / zone)
    grid, inventory = export_model(
        model, inputs, picks, horizon_faults, output_directory, dimensions=dimensions
    )
    print(picks.groupby(["fault", "status"]).size().to_string(), flush=True)
    print(f"Saved {zone} to {output_directory.resolve()}", flush=True)
    return model, inputs, picks, horizon_faults, grid, inventory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--zone", choices=tuple(ZONES), default="North_2")
    parser.add_argument(
        "--all", action="store_true", help="Build all ten published submodel cases separately"
    )
    parser.add_argument("--output", type=Path, default=Path("validation/mexico_basin"))
    parser.add_argument("--data", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--nelements", type=int, default=30000)
    parser.add_argument("--dimensions", type=int, nargs=3, default=(81, 81, 35))
    args = parser.parse_args()
    if args.nelements < 100 or any(d < 3 for d in args.dimensions):
        parser.error("Use at least 100 interpolation elements and 3 grid nodes per dimension")
    for zone_name in ZONES if args.all else (args.zone,):
        run_example(
            zone_name,
            args.output / zone_name,
            data_directory=args.data,
            offline=args.offline,
            nelements=args.nelements,
            dimensions=tuple(args.dimensions),
        )
