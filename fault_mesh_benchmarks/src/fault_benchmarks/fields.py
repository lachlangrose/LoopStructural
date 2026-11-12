"""Block-local (one-sided) evaluation of faulted LoopStructural fields.

A faulted field is discontinuous across each fault. Contouring it on a grid
smears the offset across the cells that the fault cuts. To avoid this, the
benchmark evaluates, for every fault block, a *smooth extension* of that
block's field over the whole domain:

    v_sigma(p) = v(restore_sigma(p))

where ``restore_sigma`` treats every point as if it were on side ``sigma_i``
of each fault i. This is done by temporarily replacing the fault frame
coordinate gx_i(p) by ``sigma_i * |gx_i(p)|`` (a mirror extension), so the
displacement profile is continuous across the fault surface. Inside its own
block, v_sigma equals the LoopStructural field exactly.

Each block is the set ``{p : sigma_i * s_i(p) >= 0 for all i}`` where s_i is
the side function of fault i. For an abutting fault (it exists only where
``side * gx_j > 0``) the side function is the continuous CSG expression
``max(-side*gx_j, gx_i)``, so the block surfaces can be clipped with linear
interpolation without a jump.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from contextlib import contextmanager

import numpy as np

from .builder import BuiltCase, restore

EPS_GX = 1e-9


def _orig_eval(feature, pts, **kw):
    """Call the class implementation, bypassing any instance override."""
    return type(feature).evaluate_value(feature, pts, **kw)


@contextmanager
def forced_sides(sides: dict) -> Iterator[None]:
    """Force fault frame coordinate gx of each fault to one side.

    ``sides`` maps FaultSegment -> +1 / -1. NaN values (outside an abutting
    region) are kept, so a fault with no support still gives no movement.
    """
    patched = []
    try:
        for fault, s in sides.items():
            feat = fault[0]
            patched.append((feat, feat.__dict__.get("evaluate_value")))

            def wrapped(pos, *args, _feat=feat, _s=float(s), **kwargs):
                v = np.asarray(_orig_eval(_feat, pos, *args, **kwargs), dtype=float)
                out = v.copy()
                m = ~np.isnan(v)
                out[m] = _s * np.maximum(np.abs(v[m]), EPS_GX)
                return out

            feat.evaluate_value = wrapped
        yield
    finally:
        # Restore in reverse so nested contexts on the same fault unwind correctly.
        for feat, previous in reversed(patched):
            if previous is None:
                feat.__dict__.pop("evaluate_value", None)
            else:
                feat.evaluate_value = previous


def raw_frame(fault, pts: np.ndarray, coord: int = 0) -> np.ndarray:
    """Fault frame coordinate without the side override and without regions."""
    return np.asarray(_orig_eval(fault[coord], pts, ignore_regions=True), dtype=float)


def tip_function(built: BuiltCase, name: str, pts: np.ndarray) -> np.ndarray | None:
    """t(p) = min(1 - |g|) over the frame coordinates that carry a tip, or None.

    t > 0 where the fault displaces points (inside the tip loop, projected
    along the fault normal); t <= 0 where its displacement is exactly zero.
    """
    from .spec import profile_tip_axes

    fault = built.faults[name]
    tip_y, tip_z = profile_tip_axes(built.spec.fault(name).profile)
    parts = [1.0 - np.abs(raw_frame(fault, pts, c)) for c, on in ((1, tip_y), (2, tip_z)) if on]
    if not parts:
        return None
    return np.minimum.reduce(parts) if len(parts) > 1 else parts[0]


class SideFunctions:
    """Continuous side functions s_i(p) for the faults of one case.

    s_i >= 0 is the hanging-wall block of fault i (the canonical block where
    the fault does not exist). Two cases restrict the footwall block:

    * abutment on fault j (side s): the fault exists only where s*gx_j > 0;
    * a finite fault (tip): the fault displaces points only where t > 0. The
      footwall block stops at t = -margin, a little outside the tip, where both
      block fields are exactly equal; the two blocks of a horizon then share
      identical triangles there and are merged into one surface.
    """

    def __init__(self, built: BuiltCase, cell: float | None = None):
        self.built = built
        self.cell = cell

    def tip_margin(self, name: str) -> float:
        """Margin in t units: two cell diagonals."""
        if self.cell is None:
            return 0.0
        fs = self.built.spec.fault(name)
        radius = min(fs.major_axis, fs.intermediate_axis)
        return 2.0 * np.sqrt(3.0) * self.cell / radius

    def __call__(self, name: str, pts: np.ndarray) -> np.ndarray:
        fs = self.built.spec.fault(name)
        fault = self.built.faults[name]
        out = raw_frame(fault, pts)
        if fs.abuts is not None:
            other, side = fs.abuts
            a = side * raw_frame(self.built.faults[other], pts)
            out = np.maximum(-a, out)
        t = tip_function(self.built, name, pts)
        if t is not None:
            out = np.maximum(out, -(t + self.tip_margin(name)))
        return np.nan_to_num(out, nan=1.0)


def sign_patterns(built: BuiltCase, fault_names: list[str]) -> list[dict[str, int]]:
    """All side patterns over ``fault_names`` that can exist.

    An abutting fault whose host side is excluded by the pattern can only
    take the canonical +1 side (it is absent there).
    """
    spec = built.spec
    out = []
    for signs in itertools.product((1, -1), repeat=len(fault_names)):
        pat = dict(zip(fault_names, signs))
        ok = True
        for n, s in pat.items():
            fs = spec.fault(n)
            if fs.abuts and fs.abuts[0] in pat and pat[fs.abuts[0]] != fs.abuts[1] and s == -1:
                ok = False
        if ok:
            out.append(pat)
    return out


def block_label(pattern: dict[str, int]) -> str:
    if not pattern:
        return "all"
    return "_".join(f"{n}{'+' if s > 0 else '-'}" for n, s in pattern.items())


def actual_pattern(built: BuiltCase, sides: SideFunctions, names: list[str], pts) -> np.ndarray:
    """Per point sign (+1/-1) for each fault in ``names``; shape (N, len(names))."""
    if not names:
        return np.ones((len(pts), 0), dtype=int)
    return np.stack([np.where(sides(n, pts) >= 0, 1, -1) for n in names], axis=1)


def clip_order(built: BuiltCase, names: list[str]) -> list[str]:
    """Younger / host faults first so later side functions are evaluated in their block."""
    order = [f.name for f in built.spec.fault_build_order()]
    return [n for n in order if n in names]


def force_map(built: BuiltCase, pattern: dict[str, int]) -> dict:
    return {built.faults[n]: s for n, s in pattern.items()}


def _parent_frame(built: BuiltCase, name: str, pts: np.ndarray) -> np.ndarray:
    """Points restored through the faults that displace fault ``name``."""
    parents = [built.faults[n] for n in built.spec.fault(name).faulted_by]
    return restore(pts, parents) if parents else np.asarray(pts, dtype=float)


def own_displacement(built: BuiltCase, name: str, pts: np.ndarray) -> np.ndarray:
    """Forward displacement from fault ``name`` alone, ``q - restore_f(q)``.

    For a displaced fault, ``q`` is the point restored through its parents:
    the frame in which the series sees this fault. For translating parents
    (``constant`` profile) it equals the present-day displacement.
    """
    q = _parent_frame(built, name, pts)
    return q - built.faults[name].apply_to_points(q)


def fault_displacement_sides(built: BuiltCase, name: str, pts: np.ndarray):
    """Forward displacement of each wall of one fault, from that fault alone.

    Returns (d_hanging_wall, d_footwall), each as :func:`own_displacement`
    with the point forced to one side.
    """
    fault = built.faults[name]
    q = _parent_frame(built, name, pts)
    out = []
    for s in (1, -1):
        with forced_sides({fault: s}):
            r = fault.apply_to_points(q)
        out.append(q - r)
    return out[0], out[1]
