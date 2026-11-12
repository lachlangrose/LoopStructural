# LoopStructural Constitution

## Purpose and scope
LoopStructural is a Python library for 3D structural geological modelling.
It is being rebuilt in stages as "LoopStructural 2.0". The packages
`loop_common`, `loop_interpolation`, `loopresources`,
`loopstructural_visualisation` and `map2loop` live under `packages/`.
Evidence: `ROADMAP.md`, `packages/`, `pyproject.toml`.

## Development commands
- Test: `pytest` (`pyproject.toml`: `testpaths = ["tests"]`).
- Format: `black .` (line length 100, string normalization off).
- Lint: `ruff check LoopStructural packages`.
- Check: `ruff check LoopStructural packages && pytest`.
- Evidence: `.github/workflows/tester.yml`, `.github/workflows/linter.yml`,
  `.pre-commit-config.yaml`.

## Merge gate
- Existing CI runs `pytest`. The lint workflow applies Black and Ruff fixes,
  but runs Ruff with `--exit-zero`, so lint errors do not fail that step.
  Evidence: `.github/workflows/tester.yml`, `.github/workflows/linter.yml`.
- A change must pass `pytest` and
  `ruff check LoopStructural packages` before merge.
- No minimum review count is set.

## Code conventions
- Ruff enforces numpy-style docstrings (`D`) and type hints (`ANN`) going
  forward. Evidence: `pyproject.toml` `[tool.ruff.lint]`.
- Lint target Python version is py39.

## Module structure
- Do not write monolith files. Each module has one clear responsibility.
- Keep concerns separate: for example, data input and output, numerical
  algorithms, model assembly and visualisation go in different modules.
- When a file gets more than one responsibility, split it before you add
  more code to it.
- A module depends only on the modules it needs. Do not add a dependency
  from lower-level code (for example, interpolation) to higher-level code
  (for example, model assembly or visualisation).
- Specs and plans must name the module that owns each new responsibility.

## Architecture and compatibility
- `ROADMAP.md` is the architecture reference and the source of truth for
  stages and decisions. Update it when a stage completes or a decision changes.
- Work ships as independently testable, reversible stages.
- The public `GeologicalModel` API is a hard compatibility boundary. A
  breaking change needs an explicit decision recorded in `ROADMAP.md` and a
  major-version note.
- The QGIS plugin stays in a separate repository.
- Features are specified under `specs/NNN-name/` (spec, plan, tasks).
- Releases use release-please with per-package paths
  (`.release-please-config.json`).

## Amendments
The maintainer accepted this constitution on 2026-11-01.
Amended on 2026-11-04: added the "Module structure" section.

Propose a change in a pull request that edits this file. The repository
maintainer accepts or rejects it.
