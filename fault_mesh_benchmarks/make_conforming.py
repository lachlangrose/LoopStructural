"""Make conforming surfaces with Loop CGAL corefinement (experimental).

The fault meshes cut the horizons, and the intersection curves are inserted
into the fault meshes, so the surfaces share vertices and edges along every
cut-off and junction. Writes <out>/<case>/surfaces_conforming/.

    python make_conforming.py --case y_junction
    python make_conforming.py --case y_junction --resolution 49 --remesh 0.03

Supported now: cases without displaced faults or unconformities (13 of 17;
not crossing_faults, graben, folded_faulted, unconformity_faulted).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fault_benchmarks.builder import build_case, quiet_loopstructural  # noqa: E402
from fault_benchmarks.cases import get_case  # noqa: E402
from fault_benchmarks.conforming import write_conforming  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", action="append", required=True)
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--resolution", type=int, default=97)
    ap.add_argument("--method", default="marching_cubes")
    ap.add_argument("--remesh", type=float, default=0.0, metavar="EDGE_LENGTH",
                    help="also remesh with this target edge length (experimental)")
    args = ap.parse_args()
    quiet_loopstructural()
    ok = True
    for case in args.case:
        built = build_case(get_case(case))
        report = write_conforming(built, Path(args.out), args.resolution, args.method,
                                  remesh_target=args.remesh)
        for stage, r in report["stages"].items():
            bad = {k: v for k, v in r["conformity"].items()
                   if v.get("cutoff_edges_not_fault_edges") or v.get("cutoff_vertices_not_fault_vertices")}
            print(f"[{case}] {stage}: conforming={r['conforming']} "
                  f"({len(r['conformity'])} surface pairs, {len(bad)} with mismatches)")
            ok &= r["conforming"] or stage != "corefined"
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
