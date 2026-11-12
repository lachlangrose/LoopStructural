"""Command-line runner for the fault meshing benchmark suite (see generate_benchmarks.py)."""

from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

from .builder import build_case
from .cases import CASES, get_case
from .generate import FORMAT_VERSION, Options, generate_case

USAGE = """Command-line runner for the fault meshing benchmark suite.

Examples
--------
    python generate_benchmarks.py --list
    python generate_benchmarks.py --case planar_fault
    python generate_benchmarks.py --case all --resolution 129 --out outputs/suite
    python generate_benchmarks.py --category edge-case --method marching_tetrahedra
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=USAGE, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--case", action="append", help="case name, or 'all' (repeatable)")
    ap.add_argument("--category", help="run every case in this category")
    ap.add_argument("--list", action="store_true", help="list the cases and exit")
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--resolution", type=int, default=97,
                    help="grid nodes per axis for reference isosurfaces (default 97)")
    ap.add_argument("--volume-resolution", type=int, default=49,
                    help="grid nodes per axis for the exported field volume (default 49)")
    ap.add_argument("--method", default="marching_cubes",
                    choices=["marching_cubes", "marching_tetrahedra"])
    ap.add_argument("--formats", default="vtp,obj,stl", help="surface formats (vtp,obj,stl)")
    args = ap.parse_args(argv)

    if args.list:
        for name in CASES:
            c = get_case(name)
            print(f"{name:32s} {c.category:12s} {', '.join(c.tags)}")
        return 0

    names: list[str] = []
    if args.category:
        names += [n for n in CASES if get_case(n).category == args.category]
    for c in args.case or []:
        names += list(CASES) if c == "all" else [c]
    if not names:
        ap.error("give --case NAME, --case all, --category NAME or --list")
    names = list(dict.fromkeys(names))
    for n in names:
        get_case(n)  # fail early on a bad name

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    opts = Options(
        resolution=args.resolution,
        volume_resolution=args.volume_resolution,
        method=args.method,
        formats=tuple(f.strip() for f in args.formats.split(",") if f.strip()),
    )
    index_path = out / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"cases": {}}
    index["format_version"] = FORMAT_VERSION
    failures = 0
    for n in names:
        t0 = time.perf_counter()
        print(f"[{n}] building LoopStructural model ...", flush=True)
        try:
            built = build_case(get_case(n))
            meta = generate_case(built, out, opts)
        except Exception:  # noqa: BLE001 - report and continue with the next case
            failures += 1
            traceback.print_exc()
            index["cases"][n] = {"status": "error"}
            continue
        dt = time.perf_counter() - t0
        qa = meta["qa"]
        print(f"[{n}] {len(meta['surfaces'])} surfaces, {len(meta['constraints'])} curves, "
              f"QA {'PASS' if qa['passed'] else 'FAIL'} in {dt:.1f} s", flush=True)
        if not qa["passed"]:
            failures += 1
            print(f"[{n}] failed checks: "
                  f"{[k for k, v in qa['checks'].items() if not v]}", flush=True)
        index["cases"][n] = {
            "status": "ok" if qa["passed"] else "qa-failed",
            "category": meta["category"],
            "metadata": f"{n}/metadata.json",
            "seconds": round(dt, 2),
            "options": meta["options"],
        }
        index_path.write_text(json.dumps(index, indent=1))
    index_path.write_text(json.dumps(index, indent=1))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
