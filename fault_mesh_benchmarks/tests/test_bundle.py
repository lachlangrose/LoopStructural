"""The benchmark folder of one model is self-contained and reproduces the model."""

import json
import math

import pyvista as pv

from fault_benchmarks.builder import build_case
from fault_benchmarks.bundle import make_case_folder
from fault_benchmarks.cases import get_case
from fault_benchmarks.generate import Options, generate_case


def test_case_folder_rebuilds_model(tmp_path):
    outputs = tmp_path / "outputs"
    generate_case(build_case(get_case("y_junction")), outputs,
                  Options(resolution=33, volume_resolution=17, formats=("vtp", "obj")))
    row = make_case_folder("y_junction", outputs, tmp_path / "benchmark")
    folder = tmp_path / "benchmark" / "y_junction"
    assert "PASSED" in row["check"]
    for rel in ("build_model.py", "README.md", "data/fault_observations.csv",
                "data/series_observations.csv", "fields/implicit_fields.vtu",
                "surfaces/fault_f_branch.obj", "constraints/constraint_curves.vtp"):
        assert (folder / rel).exists(), rel
    support = json.loads((folder / "support" / "support.json").read_text())
    assert set(support) == {"strat", "f_main_gx", "f_main_gy", "f_main_gz",
                            "f_branch_gx", "f_branch_gy", "f_branch_gz"}
    assert support["strat"]["coordinates"] == "restored"
    grid = pv.read(folder / "support" / "strat.vti")
    assert grid.n_points == math.prod(support["strat"]["nodes_per_axis"])
    assert "value" in grid.point_data
