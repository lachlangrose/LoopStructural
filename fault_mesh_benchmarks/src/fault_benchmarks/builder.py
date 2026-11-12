"""Build a LoopStructural model from a :class:`CaseSpec`.

Data generation is self-consistent with LoopStructural kinematics:

* Fault observations are sampled from the analytic fault surface. When a
  fault is displaced by younger faults, the samples are moved forward
  through those (already built) faults.
* Stratigraphic observations are random present-day points. Each point is
  restored through the built faults of its series, exactly as LoopStructural
  does during evaluation, and the analytic restored field gives its value.
  The interpolated series therefore reproduces the analytic field in
  restored space, and the faults are the only source of discontinuity.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .spec import CaseSpec, FaultSpec, SeriesSpec, make_profile

COLUMNS = ["X", "Y", "Z", "val", "nx", "ny", "nz", "coord", "feature_name"]


@dataclass
class BuiltCase:
    spec: CaseSpec
    model: object
    faults: dict = field(default_factory=dict)
    series: dict = field(default_factory=dict)
    fault_data: dict = field(default_factory=dict)
    contact_data: dict = field(default_factory=dict)
    misfit: dict = field(default_factory=dict)
    build_seconds: float = 0.0
    calls: list = field(default_factory=list)
    """The LoopStructural calls in build order, as plain data (for build_model.py)."""

    def series_faults(self, name: str) -> list:
        """Faults of a series, oldest first."""
        return [self.faults[n] for n in self.spec.series_by_name(name).faults]


def quiet_loopstructural(level=logging.WARNING) -> None:
    for name in ("LoopStructural", "loop_interpolation"):
        logging.getLogger(name).setLevel(level)
    try:
        import LoopStructural

        LoopStructural.setLogging(level="warning")
    except Exception:  # noqa: BLE001 - optional helper
        pass


@contextmanager
def _frame_faults_disabled(fault):
    frame = [fault[i] for i in range(3)]
    previous = [f.faults_enabled for f in frame]
    try:
        for f in frame:
            f.faults_enabled = False
        yield
    finally:
        for f, p in zip(frame, previous):
            f.faults_enabled = p


def restore(points: np.ndarray, faults_oldest_first: list) -> np.ndarray:
    """Restore present-day points through faults, youngest fault first.

    This is the order LoopStructural uses: builders apply ``reversed(faults)``.
    Displaced faults restore with :func:`restore_once` (set by the builder).
    """
    pos = np.asarray(points, dtype=float)
    for f in reversed(faults_oldest_first):
        pos = f.apply_to_points(pos)
    return pos


def restore_once(fault) -> None:
    """Apply a displaced fault to points already restored through its parents.

    A fault that younger faults displace has a frame that itself restores
    points through those younger faults. In a series, LoopStructural restores
    a point through the younger faults first and then evaluates the older
    frame, which restores the point through the younger faults a second time.
    On crossing_faults this puts about 6 % of random points on the wrong side
    of the older fault. The benchmark evaluates the older frame with its own
    faults disabled when it restores series points, so every fault is applied
    exactly once. ``fields.own_displacement`` gives the movement of such a fault.
    """

    def apply_to_points(points, reverse=False, precomputed_gx=None, _f=fault):
        with _frame_faults_disabled(_f):
            # A precomputed gx is a present-day value: do not reuse it here.
            return type(_f).apply_to_points(_f, points, reverse=reverse)

    fault.apply_to_points = apply_to_points


def forward(points: np.ndarray, faults_oldest_first: list) -> np.ndarray:
    """Move restored points forward through faults, oldest first (approximate)."""
    pos = np.asarray(points, dtype=float)
    for f in faults_oldest_first:
        pos = f.apply_to_points(pos, reverse=True)
    return pos


def use_restored_slip_direction(fault) -> None:
    """Fast slip direction for a fault that other faults displace.

    LoopStructural evaluates the gradient of a faulted frame coordinate with
    small tetrahedra moved through the younger faults, refined while any
    tetrahedron crosses a fault. ``apply_to_points`` calls it at every
    integration step, which costs about 3 ms per point. Here the gradient is
    the frame gradient at the restored point. This is exact where the younger
    faults translate rigidly (``constant`` profile) and an approximation in
    their decay zone otherwise. The override is set on the built model, so the
    reference fields and the block fields use the same kinematics.
    """
    feat = fault[1]

    def gradient(pos, ignore_regions=False, element_scale_parameter=None, _f=feat):
        if _f.builder is not None:
            _f.builder.up_to_date()
        p = _f._apply_faults(np.asarray(pos, dtype=float))
        return _f.interpolator.evaluate_gradient(p)

    feat.evaluate_gradient = gradient


def _fault_samples(fs: FaultSpec) -> tuple[np.ndarray, np.ndarray]:
    nu, nv = fs.samples
    u, v = np.meshgrid(np.linspace(-1, 1, nu), np.linspace(-1, 1, nv), indexing="ij")
    return fs.surface(u.ravel(), v.ravel())


def _distance_to_fault(fault, pts: np.ndarray) -> np.ndarray:
    gx = fault[0].evaluate_value(pts, ignore_regions=True)
    g = fault[0].evaluate_gradient(pts, ignore_regions=True)
    return np.abs(gx) / np.maximum(np.linalg.norm(g, axis=1), 1e-12)


def _build_fault(model, fs: FaultSpec, built: dict) -> tuple[object, pd.DataFrame]:
    pts, nrm = _fault_samples(fs)
    center = np.asarray(fs.center, dtype=float)[None, :]
    parents = [built[n] for n in fs.faulted_by]
    if parents:
        pts = forward(pts, parents)
        center = forward(center, parents)
        keep = np.ones(len(pts), dtype=bool)
        for p in parents:
            keep &= _distance_to_fault(p, pts) > 0.04
        pts, nrm = pts[keep], nrm[keep]
    inside = np.all((pts > -0.1) & (pts < 1.1), axis=1)
    pts, nrm = pts[inside], nrm[inside]
    if len(pts) < 4:
        raise ValueError(f"fault {fs.name}: fewer than 4 samples inside the domain")
    df = pd.DataFrame(
        {
            "X": pts[:, 0],
            "Y": pts[:, 1],
            "Z": pts[:, 2],
            "val": 0.0,
            "nx": nrm[:, 0],
            "ny": nrm[:, 1],
            "nz": nrm[:, 2],
            "coord": 0,
            "feature_name": fs.name,
        }
    )[COLUMNS]
    fault = model.create_and_add_fault(
        fs.name,
        fs.displacement,
        data=df,
        fault_slip_vector=-np.asarray(fs.slip, dtype=float),
        fault_normal_vector=np.asarray(fs.normal, dtype=float),
        fault_center=center[0],
        major_axis=fs.major_axis,
        intermediate_axis=fs.intermediate_axis,
        minor_axis=fs.minor_axis,
        faultfunction=make_profile(fs.profile),
        faults=parents,
        nelements=fs.nelements,
        fault_buffer=fs.fault_buffer,
    )
    if fault is None:
        raise RuntimeError(f"LoopStructural did not build fault {fs.name}")
    built.setdefault("__calls__", []).append({
        "call": "fault", "name": fs.name, "displacement": fs.displacement,
        "fault_slip_vector": (-np.asarray(fs.slip, dtype=float)).tolist(),
        "fault_normal_vector": np.asarray(fs.normal, dtype=float).tolist(),
        "fault_center": np.asarray(center[0], dtype=float).tolist(),
        "major_axis": fs.major_axis, "intermediate_axis": fs.intermediate_axis,
        "minor_axis": fs.minor_axis, "profile": fs.profile,
        "faults": list(fs.faulted_by), "nelements": fs.nelements,
        "fault_buffer": fs.fault_buffer, "steps": fs.steps,
        "abuts": list(fs.abuts) if fs.abuts else None,
    })
    fault.steps = fs.steps
    if parents:
        use_restored_slip_direction(fault)
        restore_once(fault)
    if fs.abuts is not None:
        other, side = fs.abuts
        fault.add_abutting_fault(built[other], positive=side > 0)
    return fault, df


def _check_series_faults(spec: CaseSpec, ss: SeriesSpec) -> None:
    for i, name in enumerate(ss.faults):
        for parent in spec.fault(name).faulted_by:
            if parent not in ss.faults[i + 1 :]:
                raise ValueError(
                    f"series {ss.name}: fault {name} is displaced by {parent}, so {parent} "
                    "must also displace the series and be listed after it (younger)"
                )


def _build_series(model, ss: SeriesSpec, built: dict, rng) -> tuple[object, pd.DataFrame, dict]:
    faults = [built[n] for n in ss.faults]
    pts = rng.uniform(0.0, 1.0, size=(ss.n_samples, 3))
    restored = restore(pts, faults)
    vals = ss.field(restored)
    df = pd.DataFrame(
        {
            "X": pts[:, 0],
            "Y": pts[:, 1],
            "Z": pts[:, 2],
            "val": vals,
            "nx": np.nan,
            "ny": np.nan,
            "nz": np.nan,
            "coord": np.nan,
            "feature_name": ss.name,
        }
    )[COLUMNS]
    feat = model.create_and_add_foliation(
        ss.name, data=df, faults=faults, nelements=ss.nelements, buffer=ss.buffer
    )
    if feat is None:
        raise RuntimeError(f"LoopStructural did not build series {ss.name}")
    built.setdefault("__calls__", []).append({
        "call": "series", "name": ss.name, "faults": list(ss.faults),
        "nelements": ss.nelements, "buffer": ss.buffer,
        "unconformity": ss.unconformity,
    })
    if ss.unconformity is not None:
        model.add_unconformity(feat, ss.unconformity)
    fitted = feat.evaluate_value(pts, ignore_regions=True)
    err = fitted - vals
    span = float(np.ptp(vals)) or 1.0
    misfit = {
        "rms": float(np.sqrt(np.nanmean(err**2))),
        "max_abs": float(np.nanmax(np.abs(err))),
        "relative_rms": float(np.sqrt(np.nanmean(err**2)) / span),
    }
    return feat, df, misfit


def build_case(spec: CaseSpec) -> BuiltCase:
    from LoopStructural import GeologicalModel

    quiet_loopstructural()
    t0 = time.perf_counter()
    rng = np.random.default_rng(spec.seed)
    model = GeologicalModel(np.zeros(3), np.ones(3))
    out = BuiltCase(spec=spec, model=model)
    for fs in spec.fault_build_order():
        fault, df = _build_fault(model, fs, out.faults)
        out.faults[fs.name] = fault
        out.fault_data[fs.name] = df
    for ss in spec.series:
        _check_series_faults(spec, ss)
        feat, df, misfit = _build_series(model, ss, out.faults, rng)
        out.series[ss.name] = feat
        out.contact_data[ss.name] = df
        out.misfit[ss.name] = misfit
    out.calls = out.faults.pop("__calls__", [])
    out.build_seconds = time.perf_counter() - t0
    return out
