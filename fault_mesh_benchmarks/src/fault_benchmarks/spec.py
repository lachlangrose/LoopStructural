"""Declarative description of one benchmark case.

All geometry is in the unit cube [0, 1]^3 with z up. A case is a list of
faults (youngest first is NOT required; each fault names the faults that
displace it) and a list of stratigraphic series ordered youngest first.

Sign conventions
----------------
* ``FaultSpec.normal`` points into the hanging wall. LoopStructural gives
  the fault frame coordinate ``gx > 0`` on that side.
* ``FaultSpec.slip`` is the *forward* (geological) movement direction of
  the hanging wall relative to the footwall. LoopStructural expects the
  restoration direction, so the builder passes ``-slip`` to it.
* ``FaultSpec.displacement`` is the total relative offset between the two
  walls at the fault centre.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

Vec3 = tuple[float, float, float]
FieldFn = Callable[[np.ndarray], np.ndarray]
SurfaceFn = Callable[[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]


def unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def dip_vectors(dip_deg: float, dip_azimuth_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (normal_up, down_dip, strike) unit vectors for a plane.

    ``dip_azimuth_deg`` is measured clockwise from +y (north) to the
    down-dip direction, so 90 means the plane dips toward +x.
    """
    d = np.radians(dip_deg)
    a = np.radians(dip_azimuth_deg)
    horiz = np.array([np.sin(a), np.cos(a), 0.0])
    down_dip = np.cos(d) * horiz + np.array([0.0, 0.0, -np.sin(d)])
    normal = np.sin(d) * horiz + np.array([0.0, 0.0, np.cos(d)])
    strike = np.cross(normal, down_dip)
    return unit(normal), unit(down_dip), unit(strike)


@dataclass
class FaultSpec:
    name: str
    center: Vec3
    normal: Vec3
    slip: Vec3
    displacement: float
    surface: SurfaceFn
    """Parametric fault surface ``(u, v) -> (points, normals)``, u,v in [-1, 1].

    Present-day geometry when the fault is not displaced by another fault;
    restored geometry otherwise (the builder moves it forward)."""
    profile: str = "constant"
    """``constant`` (hanging wall moves rigidly, step at the fault),
    ``tip`` (hanging wall moves, footwall fixed, taper to a tip loop that is a rectangle in the fault frame),
    ``base`` (LoopStructural BaseFault), ``base3d`` (BaseFault3D)."""
    major_axis: float = 4.0
    """Strike radius: LoopStructural normalises gz = distance / major_axis."""
    intermediate_axis: float = 4.0
    """Slip-direction radius: gy = distance / intermediate_axis."""
    minor_axis: float = 4.0
    """Full width normal to the fault: gx = distance / (minor_axis / 2).
    (Measured on LoopStructural 1.8.4; note the factor 2 differs from gy, gz.)"""
    faulted_by: list[str] = field(default_factory=list)
    """Younger faults that displace this fault, oldest first."""
    abuts: tuple[str, int] | None = None
    """(other fault, side): this fault exists only where side*gx_other > 0."""
    truncated_by: tuple[str, float] | None = None
    """(series, value): fault surface exists only where series < value
    (a pre-unconformity fault). Geometry only; kinematics are set by which
    series list the fault."""
    nelements: int = 30_000
    fault_buffer: float = 0.5
    steps: int = 10
    """Integration steps of LoopStructural ``apply_to_points``. One step is exact for a
    planar fault with the ``constant`` profile (a pure translation)."""
    samples: tuple[int, int] = (9, 9)


@dataclass
class SeriesSpec:
    name: str
    field: FieldFn
    """Analytic scalar field in restored (pre-faulting) coordinates."""
    expression: str
    isovalues: list[float]
    faults: list[str] = field(default_factory=list)
    """Faults that displace this series, oldest first."""
    unconformity: float | None = None
    """If set, older series are visible only where this series < value."""
    nelements: int = 40_000
    n_samples: int = 1200
    buffer: float = 0.3


@dataclass
class CaseSpec:
    name: str
    category: str
    description: str
    faults: list[FaultSpec]
    series: list[SeriesSpec]
    """Youngest first (LoopStructural build order)."""
    tags: list[str] = field(default_factory=list)
    seed: int = 20261111
    variant_of: str | None = None

    def fault(self, name: str) -> FaultSpec:
        for f in self.faults:
            if f.name == name:
                return f
        raise KeyError(name)

    def series_by_name(self, name: str) -> SeriesSpec:
        for s in self.series:
            if s.name == name:
                return s
        raise KeyError(name)

    def fault_build_order(self) -> list[FaultSpec]:
        """Faults ordered so every fault is built after the faults that displace it."""
        done: list[str] = []
        pending = list(self.faults)
        while pending:
            progressed = False
            for f in list(pending):
                deps = list(f.faulted_by) + ([f.abuts[0]] if f.abuts else [])
                if all(d in done for d in deps):
                    done.append(f.name)
                    pending.remove(f)
                    progressed = True
            if not progressed:
                raise ValueError(f"cyclic fault dependencies in {self.name}")
        return [self.fault(n) for n in done]


# --------------------------------------------------------------------------
# Parametric fault surfaces
# --------------------------------------------------------------------------


def planar_surface(center, dip_deg, dip_azimuth_deg, half_length=0.9, half_height=0.9) -> SurfaceFn:
    c = np.asarray(center, dtype=float)
    normal, down_dip, strike = dip_vectors(dip_deg, dip_azimuth_deg)

    def surf(u, v):
        pts = c + u[:, None] * half_length * strike + v[:, None] * half_height * down_dip
        nrm = np.repeat(normal[None, :], len(u), axis=0)
        return pts, nrm

    return surf


def bend_surface(x_center: float, step: float, y_bend: float, width: float) -> SurfaceFn:
    """Vertical fault whose map trace makes a smooth step at ``y_bend``.

    Trace: x(y) = x_center - 0.5 * step * tanh((y - y_bend) / width). For
    ``step > 0`` the trace moves toward -x going north (+y): with dextral
    slip (the +x block moves -y) this is a restraining (left-stepping) bend.
    The normal points to +x.
    """

    def x_of(y):
        return x_center - 0.5 * step * np.tanh((y - y_bend) / width)

    def dx_dy(y):
        return -0.5 * step / width / np.cosh((y - y_bend) / width) ** 2

    def surf(u, v):
        y = 0.5 + 0.6 * u
        z = 0.5 + 0.6 * v
        p = np.stack([x_of(y), y, z], axis=1)
        n = np.stack([np.ones_like(y), -dx_dy(y), np.zeros_like(y)], axis=1)
        n /= np.linalg.norm(n, axis=1)[:, None]
        return p, n

    return surf


def listric_surface(
    x_top: float,
    z_top: float,
    dip_top: float,
    dip_bottom: float,
    depth: float,
    strike_bow: float = 0.0,
) -> SurfaceFn:
    """Fault dipping toward +x whose dip decreases linearly with depth.

    ``strike_bow`` bends the trace in map view: x shifts by
    ``strike_bow * (1 - (2y-1)^2)``.
    """
    zs = np.linspace(0.0, depth, 401)
    dips = np.radians(dip_top + (dip_bottom - dip_top) * zs / depth)
    xs = np.concatenate([[0.0], np.cumsum(np.diff(zs) / np.tan(dips[1:]))])

    def pos(y, s):
        return np.stack(
            [
                x_top + np.interp(s, zs, xs) + strike_bow * (1.0 - (2.0 * y - 1.0) ** 2),
                y,
                z_top - s,
            ],
            axis=1,
        )

    def surf(u, v):
        y = 0.5 + 0.6 * u
        s = 0.5 * (v + 1.0) * depth
        p = pos(y, s)
        h = 1e-4
        tu = pos(y + h, s) - pos(y - h, s)
        tv = pos(y, s + h) - pos(y, s - h)
        n = np.cross(tu, tv)
        n /= np.linalg.norm(n, axis=1)[:, None]
        n[n[:, 2] < 0] *= -1.0  # hanging wall above
        return p, n

    return surf


# --------------------------------------------------------------------------
# Fault displacement profiles
# --------------------------------------------------------------------------


def make_profile(kind: str):
    """Return a LoopStructural ``faultfunction`` value for a profile name."""
    from LoopStructural.modelling.features.fault._fault_function import (
        Composite,
        FaultDisplacement,
        Ones,
        Zeros,
        smooth_peak,
    )

    if kind == "constant":
        return FaultDisplacement(gx=Composite(Ones(), Zeros()), gy=Ones(), gz=Ones(), scale=1.0)
    if kind == "tip":
        # Step at the fault: the hanging wall moves, the footwall is fixed. The
        # movement decays away from the fault (LoopStructural BaseFault
        # hanging-wall cubic) and tapers to a tip loop along slip and strike.
        from LoopStructural.modelling.features.fault._fault_function import BaseFault

        return FaultDisplacement(
            gx=Composite(BaseFault.hw, Zeros()), gy=smooth_peak, gz=smooth_peak, scale=1.0
        )
    if kind == "base":
        return "BaseFault"
    if kind == "base3d":
        return "BaseFault3D"
    raise ValueError(f"unknown fault profile {kind!r}")


def profile_tip_axes(kind: str) -> tuple[bool, bool]:
    """Which frame coordinates (gy, gz) have a tip at |g| = 1 for this profile."""
    return {
        "constant": (False, False),
        "tip": (True, True),
        "base": (False, True),
        "base3d": (True, True),
    }[kind]
