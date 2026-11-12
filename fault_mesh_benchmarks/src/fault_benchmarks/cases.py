"""Registry of benchmark cases.

Every case lives in the unit cube with z up. Restored stratigraphic fields
are analytic; LoopStructural interpolates them from present-day samples that
are restored through the case's faults (see ``builder``).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .spec import (
    CaseSpec,
    FaultSpec,
    SeriesSpec,
    bend_surface,
    dip_vectors,
    listric_surface,
    planar_surface,
)

CASES: dict[str, Callable[[], CaseSpec]] = {}


def register(fn: Callable[[], CaseSpec]) -> Callable[[], CaseSpec]:
    CASES[fn.__name__] = fn
    return fn


def get_case(name: str) -> CaseSpec:
    if name not in CASES:
        raise KeyError(f"unknown case {name!r}; choose from {sorted(CASES)}")
    return CASES[name]()


def _planar_fault(
    name,
    center,
    dip,
    dip_azimuth,
    displacement,
    sense="normal",
    profile="constant",
    axes=(4.0, 4.0, 4.0),
    **kw,
) -> FaultSpec:
    """Planar fault. ``sense`` is normal (hanging wall down-dip) or reverse."""
    normal, down_dip, _ = dip_vectors(dip, dip_azimuth)
    slip = down_dip if sense == "normal" else -down_dip
    kw.setdefault("steps", 1 if profile == "constant" else 10)
    return FaultSpec(
        name=name,
        center=tuple(center),
        normal=tuple(normal),
        slip=tuple(slip),
        displacement=displacement,
        surface=planar_surface(center, dip, dip_azimuth),
        profile=profile,
        major_axis=axes[0],
        intermediate_axis=axes[1],
        minor_axis=axes[2],
        **kw,
    )


def _layer_cake(name="strat", isovalues=(0.25, 0.45, 0.65, 0.8), faults=(), **kw) -> SeriesSpec:
    return SeriesSpec(
        name=name,
        field=lambda p: p[:, 2].copy(),
        expression="z",
        isovalues=list(isovalues),
        faults=list(faults),
        **kw,
    )


# --------------------------------------------------------------------------
# 1. Idealised geometric end-members
# --------------------------------------------------------------------------


@register
def planar_fault() -> CaseSpec:
    f = _planar_fault("f1", (0.5, 0.5, 0.5), 60, 90, 0.15)
    return CaseSpec(
        name="planar_fault",
        category="idealised",
        description=(
            "One planar normal fault (dip 60 toward +x, strike along y) with a constant "
            "displacement vector: the hanging wall moves rigidly 0.15 down-dip, the footwall "
            "is fixed. Four horizontal horizons are offset by a pure step."
        ),
        faults=[f],
        series=[_layer_cake(faults=["f1"])],
        tags=["step", "constant-slip", "planar"],
    )


@register
def fault_tip() -> CaseSpec:
    f = _planar_fault(
        "f1", (0.5, 0.5, 0.5), 70, 90, 0.2, profile="base3d", axes=(0.35, 0.3, 0.5)
    )
    return CaseSpec(
        name="fault_tip",
        category="idealised",
        description=(
            "Finite fault fully inside the volume (LoopStructural BaseFault3D). Displacement "
            "is largest at the centre and goes smoothly to zero on the tip loop, and away from "
            "the fault over the minor axis. The tip loop is a rectangle in the fault frame "
            "(0.7 along strike, 0.6 along dip), with rounded displacement contours inside. "
            "Each horizon is one surface: a cut horizon has a slit (two cut-off curves that "
            "meet at the tip); a horizon beyond the tip is not cut."
        ),
        faults=[f],
        series=[_layer_cake(faults=["f1"])],
        tags=["tip-line", "die-out", "high-gradient"],
    )


@register
def fault_tip_step() -> CaseSpec:
    f = _planar_fault("f1", (0.5, 0.5, 0.5), 70, 90, 0.2, profile="tip", axes=(0.35, 0.3, 1.0))
    return CaseSpec(
        name="fault_tip_step",
        category="idealised",
        description=(
            "Same fault plane and tip loop as fault_tip, but only the hanging wall moves: "
            "the footwall is fixed, and the hanging-wall movement decays over 0.5 from the "
            "fault (fault_tip: both walls move, decay 0.25). The full offset is on one side, "
            "so the cut-off is a pure step that tapers to zero on the tip loop."
        ),
        faults=[f],
        series=[_layer_cake(faults=["f1"])],
        tags=["tip-line", "step", "die-out"],
        variant_of="fault_tip",
    )


def _surface_frame(surface) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Centre, normal and down-dip direction of a parametric surface at (0, 0)."""
    p, n = surface(np.array([0.0]), np.array([0.0]))
    p2, _ = surface(np.array([0.0]), np.array([1e-3]))
    d = p2[0] - p[0]
    d -= np.dot(d, n[0]) * n[0]  # exactly in the tangent plane
    return p[0], n[0], d / np.linalg.norm(d)


@register
def listric_fault() -> CaseSpec:
    surf = listric_surface(
        x_top=0.25, z_top=1.05, dip_top=72, dip_bottom=22, depth=1.1, strike_bow=0.08
    )
    c, n, down = _surface_frame(surf)
    f = FaultSpec(
        name="f1",
        center=tuple(c),
        normal=tuple(n),
        slip=tuple(down),
        displacement=0.15,
        surface=surf,
        profile="base3d",
        major_axis=0.9,
        intermediate_axis=1.0,
        minor_axis=0.8,
        samples=(11, 15),
        nelements=40_000,
    )
    return CaseSpec(
        name="listric_fault",
        category="idealised",
        description=(
            "Listric normal fault: dip decreases from 72 at the top to 22 at the base, and the "
            "trace is bowed in map view. BaseFault3D throw varies along strike and dip but "
            "stays non-zero in the volume. Slip follows the curved fault frame, so the "
            "hanging-wall horizons roll over."
        ),
        faults=[f],
        series=[_layer_cake(isovalues=(0.3, 0.5, 0.7, 0.85), faults=["f1"])],
        tags=["curved", "listric", "variable-throw", "rollover"],
    )


@register
def y_junction() -> CaseSpec:
    main = _planar_fault("f_main", (0.4, 0.5, 0.5), 60, 90, 0.12)
    branch = _planar_fault("f_branch", (0.75, 0.5, 0.6), 70, 270, 0.06, abuts=("f_main", 1))
    return CaseSpec(
        name="y_junction",
        category="idealised",
        description=(
            "Y junction: an antithetic fault in the hanging wall of the main fault abuts it at "
            "depth (junction line near z=0.17). Three blocks; the antithetic fault surface ends "
            "on the main fault along a shared junction curve."
        ),
        faults=[main, branch],
        series=[_layer_cake(faults=["f_main", "f_branch"])],
        tags=["junction", "abutting", "y-junction"],
    )


@register
def crossing_faults() -> CaseSpec:
    old = _planar_fault("f_old", (0.4, 0.5, 0.5), 60, 90, 0.10, faulted_by=["f_young"])
    young = _planar_fault("f_young", (0.6, 0.5, 0.5), 55, 270, 0.08)
    return CaseSpec(
        name="crossing_faults",
        category="idealised",
        description=(
            "Conjugate cross-cutting faults. The younger fault (dip 55 toward -x) cuts and "
            "offsets the older fault (dip 60 toward +x). Four blocks; the older fault surface "
            "is itself split into two offset patches."
        ),
        faults=[old, young],
        series=[_layer_cake(faults=["f_old", "f_young"])],
        tags=["junction", "cross-cutting", "offset-fault"],
    )


@register
def graben() -> CaseSpec:
    west = _planar_fault("f_west", (0.15, 0.5, 0.5), 60, 90, 0.10, faulted_by=["f_east"])
    east = _planar_fault("f_east", (0.85, 0.5, 0.5), 60, 270, 0.10)
    return CaseSpec(
        name="graben",
        category="idealised",
        description=(
            "Symmetric graben: two facing normal faults (dip 60). The faults converge toward a "
            "line just below the domain base (z ~ -0.1), so the graben floor narrows to about "
            "0.12 at z=0. Constant-slip profiles move each hanging-wall half-space rigidly, so "
            "the west fault lies in the moving hanging wall of the east fault: the east fault is "
            "declared younger and displaces the west fault surface."
        ),
        faults=[west, east],
        series=[_layer_cake(faults=["f_west", "f_east"])],
        tags=["graben", "multi-fault", "converging"],
    )


# --------------------------------------------------------------------------
# 2. Complex structural frameworks
# --------------------------------------------------------------------------


def _folded_field(p: np.ndarray) -> np.ndarray:
    axis = np.radians(30.0)
    s = p[:, 0] * np.cos(axis) + p[:, 1] * np.sin(axis)
    return p[:, 2] - 0.5 - 0.07 * np.sin(2 * np.pi * s / 0.5)


@register
def folded_faulted() -> CaseSpec:
    normal = _planar_fault(
        "f_normal", (0.35, 0.5, 0.5), 60, 90, 0.12, profile="base", axes=(0.9, 4.0, 0.6),
        faulted_by=["f_reverse"],
    )
    reverse = _planar_fault(
        "f_reverse", (0.8, 0.5, 0.5), 45, 90, 0.10, sense="reverse", profile="base",
        axes=(0.9, 4.0, 0.6),
    )
    strat = SeriesSpec(
        name="strat",
        field=_folded_field,
        expression="z - 0.5 - 0.07*sin(2*pi*(x*cos(30deg) + y*sin(30deg))/0.5)",
        isovalues=[-0.3, -0.15, 0.0, 0.15, 0.3],
        faults=["f_normal", "f_reverse"],
        n_samples=2500,
        nelements=60_000,
    )
    return CaseSpec(
        name="folded_faulted",
        category="pseudo-real",
        description=(
            "Upright folds (wavelength 0.5, amplitude 0.07, axis trending 30 deg oblique to the "
            "faults) cut after folding by a normal fault (dip 60) and a reverse fault (dip 45). "
            "BaseFault profiles: throw varies along strike and drag-like decay over 0.3 from "
            "each fault, so horizon cut-off lines are curved and the dihedral angle varies."
        ),
        faults=[normal, reverse],
        series=[strat],
        tags=["folded", "normal", "reverse", "variable-dihedral"],
    )


@register
def unconformity_faulted() -> CaseSpec:
    post = _planar_fault("f_post", (0.65, 0.5, 0.5), 65, 270, 0.12)
    pre = _planar_fault(
        "f_pre", (0.3, 0.5, 0.4), 55, 90, 0.10, faulted_by=["f_post"], truncated_by=("cover", 0.0)
    )
    tilt = np.radians(20.0)
    cover = SeriesSpec(
        name="cover",
        field=lambda p: p[:, 2] - 0.6,
        expression="z - 0.6",
        isovalues=[0.0, 0.15, 0.3],
        faults=["f_post"],
        unconformity=0.0,
    )
    basement = SeriesSpec(
        name="basement",
        field=lambda p: -np.sin(tilt) * p[:, 0] + np.cos(tilt) * p[:, 2] - 0.1,
        expression="-sin(20deg)*x + cos(20deg)*z - 0.1",
        isovalues=[0.05, 0.2, 0.35, 0.5, 0.65],
        faults=["f_pre", "f_post"],
    )
    return CaseSpec(
        name="unconformity_faulted",
        category="pseudo-real",
        description=(
            "Tilted basement (20 deg) cut by an early fault, eroded, and covered by flat strata "
            "above an angular unconformity (cover = 0). A late fault cuts everything and offsets "
            "the early fault. Upper basement horizons are truncated (missing intervals on the "
            "upthrown side), and the early fault surface ends on the unconformity."
        ),
        faults=[post, pre],
        series=[cover, basement],
        tags=["unconformity", "truncation", "pre-unconformity-fault", "cross-cutting"],
    )


# --------------------------------------------------------------------------
# 3. Fault uncertainty and edge cases
# --------------------------------------------------------------------------


def _gradient_case(label: str, minor_axis: float) -> CaseSpec:
    f = _planar_fault(
        "f1", (0.5, 0.5, 0.5), 60, 90, 0.15, profile="base", axes=(1.6, 4.0, minor_axis)
    )
    return CaseSpec(
        name=f"displacement_gradient_{label}",
        category="uncertainty",
        description=(
            f"Planar normal fault with a BaseFault profile; minor axis {minor_axis}. The "
            f"displacement decays to zero at {minor_axis / 2:.2f} from the fault, so the "
            "near-fault displacement gradient (and horizon drag) changes across the family "
            "while the offset at the fault stays 0.15."
        ),
        faults=[f],
        series=[_layer_cake(faults=["f1"])],
        tags=["displacement-gradient", "drag", f"minor-axis-{minor_axis}"],
        variant_of="displacement_gradient",
    )


@register
def displacement_gradient_sharp() -> CaseSpec:
    return _gradient_case("sharp", 0.12)


@register
def displacement_gradient_medium() -> CaseSpec:
    return _gradient_case("medium", 0.4)


@register
def displacement_gradient_broad() -> CaseSpec:
    return _gradient_case("broad", 1.2)


def _uncertainty_case(k: int) -> CaseSpec:
    seed = 1000 + k
    rng = np.random.default_rng(seed)
    dip = float(np.clip(rng.normal(60, 6), 45, 75))
    disp = float(np.clip(rng.normal(0.12, 0.03), 0.05, 0.2))
    minor = float(np.clip(rng.lognormal(np.log(0.4), 0.5), 0.1, 1.5))
    cx = float(rng.uniform(0.4, 0.6))
    f = _planar_fault("f1", (cx, 0.5, 0.5), dip, 90, disp, profile="base", axes=(1.6, 4.0, minor))
    return CaseSpec(
        name=f"fault_uncertainty_{k}",
        category="uncertainty",
        description=(
            f"Seeded realisation {k} (seed {seed}) of an uncertain planar fault: dip {dip:.1f}, "
            f"displacement {disp:.3f}, minor axis {minor:.2f}, centre x {cx:.3f}. The parameters "
            "are drawn from fixed distributions so the family is reproducible."
        ),
        faults=[f],
        series=[_layer_cake(faults=["f1"])],
        tags=["uncertainty", "realisation"],
        seed=seed,
        variant_of="fault_uncertainty",
    )


@register
def fault_uncertainty_0() -> CaseSpec:
    return _uncertainty_case(0)


@register
def fault_uncertainty_1() -> CaseSpec:
    return _uncertainty_case(1)


@register
def fault_uncertainty_2() -> CaseSpec:
    return _uncertainty_case(2)


@register
def squeezed_wedge() -> CaseSpec:
    shallow = _planar_fault("f_a", (0.45, 0.5, 0.5), 55, 90, 0.10)
    steep = _planar_fault("f_b", (0.5, 0.5, 0.5), 75, 90, 0.05, abuts=("f_a", 1))
    return CaseSpec(
        name="squeezed_wedge",
        category="edge-case",
        description=(
            "Two synthetic normal faults (dip 55 and 75) that meet at a 20 deg angle near "
            "z=0.38; the steep fault abuts the shallow one. The block between them is a wedge "
            "that thins from 0.27 at the top to zero at the junction line: thin elements, "
            "slivers and a very acute dihedral angle at the junction."
        ),
        faults=[shallow, steep],
        series=[_layer_cake(isovalues=(0.2, 0.45, 0.6, 0.75, 0.9), faults=["f_a", "f_b"])],
        tags=["thin-wedge", "acute-junction", "sliver"],
    )


@register
def restraining_bend() -> CaseSpec:
    step, width = 0.2, 0.12
    surf = bend_surface(x_center=0.5, step=step, y_bend=0.5, width=width)
    p0, n0 = surf(np.array([0.0]), np.array([0.0]))
    tangent = np.array([-n0[0, 1], n0[0, 0], 0.0])  # along strike, pointing +y
    main = FaultSpec(
        name="f_main",
        center=tuple(p0[0]),
        normal=tuple(n0[0]),
        slip=tuple(-tangent),  # dextral: the +x (hanging-wall) block moves -y
        displacement=0.12,
        surface=surf,
        profile="constant",
        samples=(15, 9),
        nelements=40_000,
    )
    # Positive flower: reverse splays dipping toward the bend, one on each side.
    # Each abuts the main fault at depth and dies out along strike (tips at
    # |y - 0.5| = 0.3), so the pop-up is confined to the bend.
    east = _planar_fault("f_splay_e", (0.62, 0.5, 0.75), 60, 270, 0.06, sense="reverse",
                         profile="base", axes=(0.3, 4.0, 0.3), abuts=("f_main", 1))
    west = _planar_fault("f_splay_w", (0.38, 0.5, 0.75), 60, 90, 0.06, sense="reverse",
                         profile="base", axes=(0.3, 4.0, 0.3), abuts=("f_main", -1))
    strat = SeriesSpec(
        name="strat",
        field=lambda p: p[:, 2] + 0.3 * (p[:, 1] - 0.5),
        expression="z + 0.3*(y - 0.5)",
        isovalues=[0.2, 0.4, 0.6, 0.8],
        faults=["f_main", "f_splay_e", "f_splay_w"],
        n_samples=2000,
        nelements=50_000,
    )
    return CaseSpec(
        name="restraining_bend",
        category="pseudo-real",
        description=(
            "Vertical dextral strike-slip fault (slip 0.12) whose trace steps left by 0.2 "
            "across a smooth 40 deg bend at y = 0.5: a restraining bend. Two reverse splays "
            "(dip 60, throw 0.06) dip toward the bend from each side, abut the main fault at "
            "depth and die out along strike, making a positive flower (pop-up). Layers dip "
            "along y, so the horizontal slip gives a visible offset that changes along the bend."
        ),
        faults=[main, east, west],
        series=[strat],
        tags=["strike-slip", "restraining-bend", "flower", "curved", "abutment", "tip"],
    )


@register
def narrow_horst() -> CaseSpec:
    west = _planar_fault("f_west", (0.48, 0.5, 0.5), 89, 270, 0.08)
    east = _planar_fault("f_east", (0.52, 0.5, 0.5), 89, 90, 0.08)
    return CaseSpec(
        name="narrow_horst",
        category="edge-case",
        description=(
            "A horst only 0.04 wide at mid-depth (0.022 at the top, 0.058 at the base) between "
            "two near-vertical (dip 89) normal faults dipping away from each other. The horst is a thin slab of "
            "a few reference cells: it tests collapse of narrow blocks and near-parallel cut-offs."
        ),
        faults=[west, east],
        series=[_layer_cake(faults=["f_west", "f_east"])],
        tags=["narrow-block", "thin-slab", "near-parallel"],
    )
