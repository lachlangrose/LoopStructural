"""Command-line runner for the fault meshing benchmark suite.

Examples
--------
    python generate_benchmarks.py --list
    python generate_benchmarks.py --case planar_fault
    python generate_benchmarks.py --case all --resolution 129 --out outputs/suite
    python generate_benchmarks.py --category edge-case --method marching_tetrahedra
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fault_benchmarks.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
