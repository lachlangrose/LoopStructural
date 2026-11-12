# Validation record

6 November 2026, Windows, existing project `.venv`.

| Check | Result |
|---|---|
| Full saved comparison sweep | 182/182 solver successes; actual reduced objective gradient infinity norm < 1e-6 in every run |
| Scientific verification file | 10 passed in 0.56 s |
| Interpolation package suite | 611 passed, 47 skipped, 2 expected failures in 71.48 s; included the first five new checks |
| Root repository suite | 731 passed, 5 skipped, 24 setup errors in 756.68 s; all 24 errors were shared temporary-directory access failures |
| Retry of those setup errors, workspace temporary directory | 24 passed, 1 skipped in 3.31 s; no remaining test-body failures |
| Ruff, new experimental modules and test file | Passed |
| Ruff, `LoopStructural packages` | 475 existing issues outside the new files; no unrelated changes applied |
| Black, new Python files | Passed/formatted |
| Saved source hashes, fields, actual-objective decrease | All matched/present; every nonlinear final objective <= its initial objective |
| Visual inspection | Comparison sweep, field behaviour and geometry-section PNGs inspected |

Commands used:

```powershell
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m pytest --lf --basetemp .cache/gradient_smoothness_pytest_retry_20261106 -q
.venv/Scripts/python -m pytest packages/loop_interpolation/tests -q
.venv/Scripts/python -m pytest packages/loop_interpolation/tests/test_gradient_smoothness_experiment.py -q
.venv/Scripts/ruff.exe check LoopStructural packages --statistics
.venv/Scripts/ruff.exe check packages/loop_interpolation/src/loop_interpolation/experimental packages/loop_interpolation/tests/test_gradient_smoothness_experiment.py
```

The first root-suite attempt could not enumerate
`AppData/Local/Temp/pytest-of-lachl`. A workspace-local `--basetemp` resolved all
24 setup errors without changing production code or test expectations. The
retry was limited to the failing tests; the passing long interpolation cases
were not repeated. Taken together, all root-suite test bodies passed.

The full Ruff command still fails. The 475 findings concern existing files
(type annotations, imports and other style issues); the scoped command reports
no issues. The experiment changes no existing production Python file.

Repository instructions, `.dev-tools/project.json`, the existing accepted
constitution, FDI derivative masks, structured support, observation assembly,
matrix assembly and solver interfaces were inspected. The ordinary `dev-tools`
launcher failed with a uv trampoline error. Invoking the installed toolkit's
`dev_tools.cli.main(['doctor', '--require-constitution'])` worked but reported
four local skill-copy entries as "No longer selected": the setup skill and
its constitution reference under `.agents` and `.claude`. The configuration
uses user-installed skills. The constitution itself exists and is accepted;
the doctor's failure is an existing installation-manifest mismatch. The setup
skill was consulted. The manifest and local skill copies already contained
uncommitted user work and were preserved. This direct experimental coding task
did not invoke a constitution-dependent spec workflow.

The saved source manifest identifies the experiment code and verification file
by SHA-256. The commit in `environment.json` is the base checkout, not a claim
that the new experiment was committed. Other pre-existing work in toolkit
configuration and specs was left untouched.
