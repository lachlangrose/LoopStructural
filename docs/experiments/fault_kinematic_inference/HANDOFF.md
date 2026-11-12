# Stage A handoff

Date: 12 November 2026.

T001-T007 are complete. **Gate A: conditional pass** for the declared planar model and working error model. This decision permits Stage B work with the same conditional uncertainty labels. Full dataset uncertainty calibration remains unperformed.

The [Gate A report](../../../validation/fault_kinematic_inference/stage_a_final_gate/report.md) and its machine-readable `gate_a.json`, `calibration.json`, `runtime.json` and `verification.json` contain the acceptance evidence. The selected runs are `stage_a_final_e0`, `stage_a_final_e1` and `stage_a_final_e2` under the repository's `validation/fault_kinematic_inference/` directory.

## Measured results

Each case used all five buffered folds. Every grid converged. All fits retained likelihood rank one; E1 removes pitch from the inferred parameter vector. There were no missing withheld contact predictions.

| Case | Free dimensions | Mean fold contact error (m) | Mean width of 90% D interval (m) |
|---|---:|---:|---:|
| E0 | 2 | 7.68 | 452.81 |
| E1 | 1 | 7.70 | 31.00 |
| E2 | 2 | 7.70 | 74.53 |

E0 preserves the unresolved slip family. The expert direction in E1 narrows the conditional displacement interval. E2's assumed +/-5 degree bound retains a wider family. Predictive error stays about 7.7 m: extra direction information improves parameter constraints, not these already-compatible contact predictions. No algorithm acceleration is claimed.

The 200-trial analytical prior-predictive screens passed: component coverage was 93.5%/92.5% for two markers, 92.0%/87.5% for parallel markers and 90.0% for the signed known-direction scalar. Exact binomial confidence intervals and rank histograms are saved in `calibration.json`. These are independent-Gaussian verification targets; they are separate from the dataset's uniform-D/pitch prior.

Plane uncertainty is material. For E0 fold 0, local plane perturbations shift separation by 4.77 m SD, compared with 3.53 m conditional posterior SD. This is a sensitivity result, not a marginal posterior. The dataset's reported intervals remain conditional on the training-estimated plane.

## Actual checks

- Focused suite: **30 passed in 4.27 s**, including explicit wall exchange, scalar terrain/root-solver regression, source/hash isolation, normalisation of expert vectors and independent bounded-pitch quadrature.
- Ruff: pass on the experiment package and tests.
- Black: all 17 files would be left unchanged.
- Post-run verification: selected training hashes and frozen prediction hashes still match. Model source hashes match; only runner metadata/formatting and the fixed-pitch report changed after the fits.
- The constraint-impact figure and repaired E1 pitch figure were visually checked.
- The initial scalar-conversion failure is preserved in `stage_a_20261112_e1/manifest.json`. The later E1 constant-pitch histogram failure is preserved in `stage_a_final_e1/manifest_reporting_failure.json`; its report was regenerated without refitting or changing scored predictions.
- Other diagnostic/partial attempts are retained and indexed in `run_index.json`. They are not method comparisons. Function timings exclude interpreter startup and the diagnostic attempts; no efficiency verdict is made.

## Changed files

Production LoopStructural code, datasets and generators were not changed by this work. Pre-existing working-tree changes remain outside this experiment.

- `experiment/__init__.py`
- `experiment/constraints.py`
- `experiment/data.py`
- `experiment/evaluate.py`
- `experiment/geometric_ensemble.py`
- `experiment/geometry.py`
- `experiment/grid.py`
- `experiment/likelihood.py`
- `experiment/report.py`
- `experiment/run.py`
- `experiment/schema.py`
- `tests/test_calibration.py`
- `tests/test_geometry.py`
- `tests/test_grid.py`
- `tests/test_inputs.py`
- `tests/test_likelihood.py`
- `tests/test_predictions.py`
- `configs/simple_e0.json`
- `configs/simple_e1.json`
- `configs/simple_e2.json`
- `configs/simple_sensitivity.json`
- `TASKS.md`, `README.md`, `INSTRUCTIONS.md`, `HANDOFF.md`.

## Frozen configuration hashes (SHA-256)

- `simple_e0.json`: `0a4cd5fa3160bdd6e4fe1a86b5b19e7d4950075c1111b4e5f3c5161fec651ba0`
- `simple_e1.json`: `abf5ed667fcae95615296dab4d82108b2887eb5ada977984174c9d9c41d5d070`
- `simple_e2.json`: `c53a7067a88e2124d63659708c70f4231fd0f82307915ea5e3aa4e7d1d473296`
- `simple_sensitivity.json`: `c8da0714728df57b837cb109a9d1e7cd792df0dfaea5433ba5c52b79e98d49b1`

Each run manifest records training-file hashes, configuration/input signatures, code hashes, seeds, software/hardware, evaluation counts, timings and status. Each fold hashes its frozen predictions before evaluation. Withheld input hashes are saved separately. No generating coefficients or packaged synthetic parameter truth are read by fitting or scoring. Recovery against packaged slip truth is unperformed; recovery is tested independently on analytical problems.

## Reproduce from the repository root

The normal module interface in `INSTRUCTIONS.md` remains available. This desktop command environment hung inside the Windows version helper used by `platform.machine()` during Pandas import. The local validation bootstrap below supplies native platform information and exits only after the module has finished and closed its output files. It does not change the scientific calculations. Its SHA-256 is `b336ef9b5394e61dc2fe1f7cc1a1bf9fcb5fafa8c160bf92ab24aa1d9d0e29fa` and is recorded in `runtime.json`.

The commands used for the latest checks and the supported reproduction sequence are:

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONPATH = Join-Path $PWD '.venv/Lib/site-packages'
$runtime = 'C:/Users/lachl/miniconda3/python.exe'
$bootstrap = 'validation/fault_kinematic_inference/windows_bootstrap.py'
& $runtime -u -S $bootstrap pytest docs/experiments/fault_kinematic_inference/tests -q --basetemp validation/fault_kinematic_inference/pytest_reproduction
.venv/Scripts/ruff.exe check docs/experiments/fault_kinematic_inference/experiment docs/experiments/fault_kinematic_inference/tests
& $runtime -u -S $bootstrap black --workers 1 --check docs/experiments/fault_kinematic_inference/experiment docs/experiments/fault_kinematic_inference/tests
foreach ($case in @('e0', 'e1', 'e2')) {
    $config = "docs/experiments/fault_kinematic_inference/configs/simple_$case.json"
    $output = "validation/fault_kinematic_inference/reproduction_$case"
    & $runtime -u -S $bootstrap docs.experiments.fault_kinematic_inference.experiment.run --config $config --output $output --phase fit
    if ($LASTEXITCODE -ne 0) { throw 'Fit failed; preserve its manifest.' }
    & $runtime -u -S $bootstrap docs.experiments.fault_kinematic_inference.experiment.run --config $config --output $output --phase evaluate
    if ($LASTEXITCODE -ne 0) { throw 'Evaluation failed; preserve its manifest.' }
}
& $runtime -u -S $bootstrap docs.experiments.fault_kinematic_inference.experiment.report --runs validation/fault_kinematic_inference/reproduction_e0 validation/fault_kinematic_inference/reproduction_e1 validation/fault_kinematic_inference/reproduction_e2 --output validation/fault_kinematic_inference/reproduction_gate
```

Use fresh output and temporary directories for each attempt. NumPy/SciPy/Pandas/Rasterio are the existing `.venv` packages; the direct base interpreter is the same Python 3.13 runtime. Formatting/lint checks required access beyond the normal desktop command restrictions. The runtime workaround is an output artifact, not a production dependency.

## Model and uncertainty limits

- The model uses shared parallel planes, constant two-wall slip and independently known vertical fault geometry. Horizon IDs are categories; numeric `val` labels are unused.
- Plane fitting and horizon/separation nuisance fitting use training observations. Posterior intervals are conditional on the estimated plane.
- Each source trace is one effective Gaussian observation. This conservative working model differs from the generator's independent-vertex error model.
- The DEM supplies elevation. XY and DEM-derived Z enter once through the surface gradient, using first-order propagation.
- Uniform magnitude in [0,600] m and uniform allowed pitch are integrated in polar coordinates. The 600 m boundary is prior support, not a data constraint.
- E1 uses a normalised expert direction; its vector norm is not a magnitude observation. E2's pitch bound is an experimental assumption.
- Plane perturbations do not replace posterior marginalisation. The analytical screening pass does not calibrate the dataset's full uncertainty.
- Geometric ensemble frequencies have no posterior-probability interpretation.
- A01-A07 apply to the declared constant, planar, fixed-correlation problems. Variable displacement, history alternatives, robust errors, real surveys, advanced methods and production integration remain unperformed.

## Local runtime bootstrap

The output root is ignored by Git. To recreate the local bootstrap in a fresh checkout, save the following as `validation/fault_kinematic_inference/windows_bootstrap.py` before using the commands above:

```python
"""Local validation workaround for hanging Windows platform/helper cleanup."""
import collections
import os
import platform
import runpy
import socket
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
if sys.platform == "win32":
    version = sys.getwindowsversion()
    native_version = f"{version.major}.{version.minor}.{version.build}"
    native_release = str(version.major)
    record = collections.namedtuple("uname_result", "system node release version machine processor")(
        "Windows", socket.gethostname(), native_release, native_version,
        os.environ.get("PROCESSOR_ARCHITECTURE", ""), os.environ.get("PROCESSOR_IDENTIFIER", ""))
    platform.uname = lambda: record
    platform.win32_ver = lambda *args, **kwargs: (native_release, native_version, version.service_pack, "")
module = sys.argv[1]
sys.argv = [module] + sys.argv[2:]
status = 0
try:
    runpy.run_module(module, run_name="__main__")
except SystemExit as error:
    status = error.code if isinstance(error.code, int) else (0 if error.code is None else 1)
except BaseException:
    traceback.print_exc()
    status = 1
sys.stdout.flush()
sys.stderr.flush()
# All module work has returned and output files are closed before this exit.
os._exit(status)
```
