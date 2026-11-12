"""Assemble the benchmark folder (one self-contained folder per model).

Run generate_benchmarks.py first; this reads its outputs.

    python make_benchmark_folder.py --outputs outputs --dest benchmark
    python make_benchmark_folder.py --case fault_tip --case planar_fault
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fault_benchmarks.builder import quiet_loopstructural  # noqa: E402
from fault_benchmarks.bundle import make_case_folder, write_index  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outputs", default="outputs")
    ap.add_argument("--dest", default="benchmark")
    ap.add_argument("--case", action="append", help="case name (default: all in outputs)")
    args = ap.parse_args()
    quiet_loopstructural()
    outputs, dest = Path(args.outputs), Path(args.dest)
    index = json.loads((outputs / "index.json").read_text())["cases"]
    cases = args.case or [c for c, v in index.items() if v["status"] == "ok"]
    dest.mkdir(parents=True, exist_ok=True)
    rows, failed = [], []
    for case in cases:
        print(f"[{case}] ...", flush=True)
        try:
            row = make_case_folder(case, outputs, dest)
        except Exception:  # noqa: BLE001 - report and continue
            traceback.print_exc()
            failed.append(case)
            continue
        print(f"[{case}] {row['check']} ({row['seconds']:.0f} s)", flush=True)
        rows.append(row)
    done = {p.name for p in dest.iterdir() if (p / "README.md").exists()}
    all_rows = {r["case"]: r for r in rows}
    for name in sorted(done - set(all_rows)):
        meta = json.loads((dest / name / "metadata.json").read_text())
        all_rows[name] = {"case": name, "category": meta["category"],
                          "description": meta["description"]}
    order = list(index)
    write_index(dest, sorted(all_rows.values(), key=lambda r: order.index(r["case"])
                             if r["case"] in order else 999))
    if failed:
        print("failed:", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
