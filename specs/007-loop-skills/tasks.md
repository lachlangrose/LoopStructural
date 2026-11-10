# Tasks: loop-skills, agent skills for Loop models

**Feature**: `007-loop-skills` | **Plan**: [plan.md](plan.md)

## Orchestrator notes

- Run this file with the spec-orchestrator skill. It has the rules for the
  worktree, the sub agents, the checks and the commits.
- Waves: 13. Tiers: [S] = simple model, [M] = standard model.
- Do not start a task with "Blocked by".
- Run all commands from the root of the worktree. Run package tests with
  `uv run --package loop-skills pytest ...` so that the worktree uses its own
  environment. Do not use the `.venv` of the main checkout: it is an editable
  install that points to the main checkout.
- Annotations: every module starts with `from __future__ import annotations`. Write `X | None`, `list[str]` and `dict[str, int]` (the Ruff `UP` rules of this repository require them; they are safe on Python 3.9 because the annotations are not evaluated). Do not use `Optional`, `List` or `Dict`. Do not use these forms at run time (for example in `isinstance`).
- A test task must fail first. Run it before the task that makes it pass and
  keep the failure message in the report.
- Stages: S1 = T001 to T016, S2 = T017 to T022, S3 = T023 to T026,
  S4 = T027 to T038. Commit at the end of each stage. Use Conventional
  Commits with the scope `loop-skills`.

## Phase 1: Setup

- [x] T001 [Setup] [M] Create the package skeleton of `loop_skills`.
  - Files: `packages/loop_skills/pyproject.toml`, `packages/loop_skills/LICENSE`, `packages/loop_skills/README.md`, `packages/loop_skills/src/loop_skills/__init__.py`
  - Needs: none
  - Wave: 1
  - Done when: `uv run --package loop-skills python -c "import loop_skills; print(loop_skills.__version__)"` prints `0.1.0`.
  - Context: `pyproject.toml`: build-system `setuptools`; `[project]` `name = "loop-skills"`, `version = "0.1.0"`, `requires-python = ">=3.9"`, `dependencies = ["packaging", "pyyaml"]`, `readme = "README.md"`, `license = { text = "MIT" }`, same `authors` and classifiers style as `packages/loop_common/pyproject.toml`. `[project.optional-dependencies]` `tests = ["pytest"]`, `checks = ["LoopStructural", "map2loop"]`. `[project.scripts]` `loop-skills = "loop_skills.cli:main"`. `[tool.setuptools.packages.find]` `where = ["src"]`, `include = ["loop_skills", "loop_skills.*"]`. `[tool.setuptools.package-data]` `loop_skills = ["skills/*/SKILL.md"]`. `[tool.pytest.ini_options]` `markers = ["names: needs LoopStructural and map2loop"]`. `LICENSE`: copy `packages/loop_common/LICENSE`. `README.md`: a title and one sentence (the full text comes in T036). `__init__.py`: start with `from __future__ import annotations`; `from importlib.metadata import PackageNotFoundError, version`; `try: __version__ = version("loop-skills")` `except PackageNotFoundError: __version__ = "0+unknown"`. Docstring in numpy style. Rule: the workspace uses `members = ["packages/*"]`, so no root change is needed.
- [x] T002 [P] [Setup] [M] Add two CI jobs for the package to the packages workflow.
  - Files: `.github/workflows/packages.yml`
  - Needs: none
  - Wave: 1
  - Done when: `python -c "import yaml; d = yaml.safe_load(open('.github/workflows/packages.yml')); j = d['jobs']; assert 'loop-skills-installer' in j and 'loop-skills-names' in j; assert {'loop-skills-installer', 'loop-skills-names'} <= set(j['loopstructural-test']['needs'])"` exits 0.
  - Context: Job `loop-skills-installer`: copy the steps of `packages-test`; matrix `os: ${{ fromJSON(vars.BUILD_OS)}}` and `python-version: ${{ fromJSON(vars.PYTHON_VERSIONS)}}`; install with `uv sync --package loop-skills --extra tests --python ${{ matrix.python-version }}`; test with `uv run --package loop-skills pytest packages/loop_skills/tests -m "not names"`. Job `loop-skills-names`: `runs-on: ubuntu-latest`; matrix `python-version` only; copy the GDAL apt step, the `uv` setup and the `GDAL_VERSION` lines of `map2loop-test`; install with `uv sync --package loop-skills --extra tests --extra checks --python ...`; test with `uv run --package loop-skills --extra checks pytest packages/loop_skills/tests -m names`. Change `needs:` of `loopstructural-test` to `[packages-test, map2loop-test, loop-skills-installer, loop-skills-names]`. Add a comment for each job that says why (the installer runs on all platforms; the name check needs GDAL for `map2loop`, so Ubuntu only).
- [x] T003 [Setup] [M] Create the test scaffold: package, fixtures and fixture skills.
  - Files: `packages/loop_skills/tests/__init__.py`, `packages/loop_skills/tests/conftest.py`, `packages/loop_skills/tests/fixtures/skills/good-skill/SKILL.md`, `packages/loop_skills/tests/fixtures/skills/bad-syntax/SKILL.md`, `packages/loop_skills/tests/fixtures/skills/bad-name/SKILL.md`, `packages/loop_skills/tests/fixtures/skills/no-pin/SKILL.md`
  - Needs: T001
  - Wave: 2
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests --collect-only -q` exits 0 or 5 (no tests yet) and `python -c "import pathlib; assert len(list(pathlib.Path('packages/loop_skills/tests/fixtures/skills').glob('*/SKILL.md'))) == 4"` exits 0.
  - Context: `tests/__init__.py` is empty. Fixture skills (frontmatter keys `name`, `description`, `requires`): `good-skill`: `requires: json>=0`, body has one valid block ```` ```python ```` with `import json` and `json.dumps({})`. `bad-syntax`: valid frontmatter, one ```` ```python ```` block with the text `def broken(:`. `bad-name`: valid frontmatter, one block `import json` then `json.not_a_function()` and `from json import NotAName`. `no-pin`: frontmatter without the `requires` key. `conftest.py` fixtures: `fixture_skills(tmp_path) -> Path` (copy `tests/fixtures/skills` to `tmp_path/"skills"` and return it); `fake_lookup` (returns a function `lookup(dist) -> Optional[str]` that reads a dict; the dict is set with `fake_lookup.versions = {...}`; use a small class with `__call__`); `no_network(monkeypatch)` (replace `socket.socket` by a function that raises `RuntimeError("network call")`). Every fixture and test function has a numpy docstring and type hints (Ruff `D` and `ANN` apply).
- [x] T004 [P] [Setup] [S] Test: the release files list the new package (story 1, scenario 6 of release consistency; plan "test_release_files.py").
  - Files: `packages/loop_skills/tests/test_release_files.py`
  - Needs: T001
  - Wave: 2
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_release_files.py` fails (the keys are missing), then passes after T007.
  - Context: Find the repository root as `Path(__file__).resolve().parents[3]`. Skip the test (`pytest.skip`) if `.release-please-config.json` is not there (sdist case). Cases: (1) `.release-please-config.json` `packages` has the key `packages/loop_skills` with `component == "loop-skills"` and `release-type == "python"`; (2) the list `packages["."]["exclude-paths"]` contains `packages/loop_skills`; (3) `.release-please-manifest.json` has the key `packages/loop_skills` with the value `0.1.0`; (4) the `version` in `packages/loop_skills/pyproject.toml` equals the manifest value (read the file with a regex `^version\s*=\s*"([^"]+)"` because Python 3.9 has no `tomllib`). Numpy docstrings and type hints.
- [x] T005 [P] [Setup] [S] Test: `ROADMAP.md` names the package (spec scenario 16, FR-015).
  - Files: `packages/loop_skills/tests/test_roadmap.py`
  - Needs: T001
  - Wave: 2
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_roadmap.py` fails, then passes after T008.
  - Context: Root = `Path(__file__).resolve().parents[3]`; skip with `pytest.skip` if `ROADMAP.md` is not there. Read the text. Assert it contains `packages/loop_skills` and `loop-skills` and `specs/007-loop-skills`. One test function `test_roadmap_names_package`. Numpy docstring and type hints.
- [x] T006 [P] [Setup] [S] Test: the core does not need the skills package (spec scenario 7, FR-001).
  - Files: `packages/loop_skills/tests/test_isolation.py`
  - Needs: T001
  - Wave: 2
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_isolation.py` passes. This is a guard test: it passes at once and it must keep passing.
  - Context: Root = `Path(__file__).resolve().parents[3]`. Test 1 `test_core_imports_without_skills`: run `subprocess.run([sys.executable, "-c", "import sys; sys.modules['loop_skills'] = None; import LoopStructural"], capture_output=True)` and assert `returncode == 0`; skip if `LoopStructural` is not importable in the environment (`importlib.util.find_spec`). Test 2 `test_core_does_not_name_skills`: skip if `LoopStructural/` is not in the root; assert that no `.py` file under `LoopStructural/` contains `loop_skills` or `loop-skills`, and that the root `pyproject.toml` does not contain `loop-skills`. Numpy docstrings and type hints.
- [x] T007 [Setup] [M] Add the package to the release files and the lock file.
  - Files: `.release-please-config.json`, `.release-please-manifest.json`, `uv.lock`
  - Needs: T004
  - Wave: 3
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_release_files.py` passes and `uv lock --check` exits 0.
  - Context: In `.release-please-config.json` add `"packages/loop_skills"` to `packages["."]["exclude-paths"]` (keep the sorted order). Add the entry `"packages/loop_skills": {"release-type": "python", "component": "loop-skills", "extra-files": [{"type": "json", "path": "src/loop_skills/.claude-plugin/plugin.json", "jsonpath": "$.version"}]}`. In `.release-please-manifest.json` add `"packages/loop_skills": "0.1.0"`. Then run `uv lock` and check with `git diff --stat uv.lock` that the diff only adds `loop-skills` and its dependencies (`packaging`, `pyyaml` if new). Rule: release-please uses per-package paths (constitution).
- [x] T008 [Setup] [M] Add Stage 7 and a status-log entry to `ROADMAP.md`.
  - Files: `ROADMAP.md`
  - Needs: T005
  - Wave: 3
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_roadmap.py` passes.
  - Context: After the bullet "Stage 6 — Intrusion workflow" (before `## Status log`) add the bullet `- [ ] **Stage 7 — Agent skills (\`loop-skills\`).**` Text, in plain English: agent skills for LoopStructural and map2loop live in the separate package `packages/loop_skills` (pip name `loop-skills`); the core never imports it; spec `specs/007-loop-skills/`; four stages S1 (library, checks, release files), S2 (Claude Code and Codex installer), S3 (Copilot block), S4 (skills, plugin, docs). Append at the end of `## Status log` one entry: the date of the day of the change, "Stage 7 started: spec and plan written for `loop-skills`; S1 landed." Match the style of the other entries. Do not change other text.

## Phase 2: Foundation (library: parser, pin, checks)

- [x] T009 [P] [Found] [S] Test: `load_skill` and `iter_skills` (spec scenario 6, edge case "damaged skill file").
  - Files: `packages/loop_skills/tests/test_skill.py`
  - Needs: T003
  - Wave: 3
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_skill.py` fails (import error for `loop_skills._skill`), then passes after T013.
  - Context: Import `from loop_skills._skill import Skill, SkillError, load_skill, iter_skills, split_frontmatter`. Use the `fixture_skills` fixture (folder with `good-skill`, `bad-syntax`, `bad-name`, `no-pin`). Cases: (1) `load_skill(root/"good-skill"/"SKILL.md")` returns a `Skill` with `name == "good-skill"`, `requires == "json>=0"`, a non-empty `body`; (2) `no-pin` raises `SkillError` and the message contains `SKILL.md`; (3) a file whose `name` differs from its folder raises `SkillError`; (4) a file with no `---` first line raises `SkillError`; (5) a `requires` of `not a range` raises `SkillError`; (6) `iter_skills(root)` returns the skills that load, in name order, and raises `SkillError` for `no-pin` (so for the order test, remove `no-pin` first); (7) `iter_skills()` with no argument returns a list (empty before the skills exist); (8) a copy of `good-skill/SKILL.md` that is written with CRLF line endings (use `write_bytes` with `\r\n` line ends) loads and gives the same `name` and `requires`, because Git can check out the files with CRLF on Windows. Numpy docstrings and type hints.
- [x] T010 [P] [Found] [S] Test: `check_pin` (spec scenarios 3, 4 and 11).
  - Files: `packages/loop_skills/tests/test_pin.py`
  - Needs: T003
  - Wave: 3
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_pin.py` fails (import error), then passes after T014.
  - Context: Import `from loop_skills._pin import PinResult, check_pin`. Use the `fake_lookup` fixture. Cases: (1) `check_pin("LoopStructural>=1.11,<2", lookup)` with version `1.11.0` gives `status == "ok"`; (2) version `2.0.0` gives `status == "outside"` and the message contains both `LoopStructural>=1.11,<2` and `2.0.0`; (3) version `None` gives `status == "missing"` and the message contains `pip install 'LoopStructural>=1.11,<2'`; (4) version `1.12.0.dev3` gives `ok` (pre-release allowed); (5) `result.distribution == "LoopStructural"` and `result.installed == "1.11.0"`; (6) `check_pin("loop-skills>=0.1,<1", lookup)` works for the name with a hyphen. Numpy docstrings and type hints.
- [x] T011 [P] [Found] [S] Test: `check_syntax` and `check_frontmatter_set` (spec scenario 14, FR-012).
  - Files: `packages/loop_skills/tests/test_check_syntax.py`
  - Needs: T003
  - Wave: 3
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_check_syntax.py` fails (import error for `loop_skills._check`), then passes after T015.
  - Context: Import `from loop_skills._check import CodeBlock, Problem, check_frontmatter_set, check_syntax, python_blocks` and `from loop_skills._skill import load_skill`. Load fixture skills with `fixture_skills`. Cases: (1) `python_blocks(good)` returns 1 `CodeBlock` with `index == 1` and `line` equal to the 1-based line of the opening fence; (2) `check_syntax(good) == []`; (3) `check_syntax(bad_syntax)` returns one `Problem` with `kind == "syntax"`, `skill == "bad-syntax"`, and a `detail` that contains `block 1`; (4) a body with a fence ```` ```text ```` is not a Python block; (5) `check_frontmatter_set([good, good])` returns one `Problem` with `kind == "unique"` and a detail that names `good-skill`; (6) `check_frontmatter_set([good])` is empty. Numpy docstrings and type hints.
- [x] T012 [P] [Found] [S] Test: `check_names` (spec scenario 15, FR-013).
  - Files: `packages/loop_skills/tests/test_check_names.py`
  - Needs: T003
  - Wave: 3
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_check_names.py` fails (import error), then passes after T016.
  - Context: Import `from loop_skills._check import NameReport, check_names`. Use `roots=("json",)` and the `fake_lookup` fixture with `{"json": "1.0"}`, so the test needs no heavy package. Fixture skills: `good-skill` (pin `json>=0`) gives `status == "checked"`, `problems == []`, `checked >= 1`; `bad-name` gives two `Problem`s with `kind == "name"`, one that names `not_a_function` and one that names `NotAName`. Extra cases with skills made in `tmp_path` by the test: (a) a block `import json` then `d = json.JSONDecoder()` then `d.decode("1")` gives no problem; (b) `d.nope()` gives a problem that names `nope`; (c) `d.object_hook` (a non-call read of an attribute) counts in `unchecked` and is not a problem; (d) a skill with pin `json>=5` and the lookup version `1.0` gives `status == "skipped"` and a non-empty `reason`; (e) a skill whose pin distribution is not in `roots` gives `status == "skipped"`; (f) a block that does not parse is ignored (no problem from `check_names`). Numpy docstrings and type hints.
- [x] T013 [Found] [M] Implement `_skill.py`.
  - Files: `packages/loop_skills/src/loop_skills/_skill.py`
  - Needs: T009
  - Wave: 4
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_skill.py` passes and `ruff check packages/loop_skills` exits 0.
  - Context: Start with `from __future__ import annotations`. `@dataclass(frozen=True) class Skill: name: str; description: str; requires: str; path: Path; body: str`. `class SkillError(ValueError)`: the message names the file. `skills_root() -> Path`: `Path(__file__).parent / "skills"`. `split_frontmatter(text: str) -> Tuple[Dict[str, Any], str]`: split the text with `splitlines()` so that both `\n` and `\r\n` line endings work; the first line must be `---`; the frontmatter ends at the next line that is exactly `---`; read it with `yaml.safe_load`; it must be a `dict`; raise `SkillError` (a `ValueError` subclass) with the reason for any other case; the second value is the text after the closing line. `load_skill(path: Path) -> Skill`: read UTF-8; require the keys `name`, `description`, `requires`, each a non-empty `str`; `name` must match `^[a-z0-9]+(-[a-z0-9]+)*$` and equal `path.parent.name`; `requires` must parse with `packaging.requirements.Requirement`; convert any failure to `SkillError(f"{path}: {reason}")` exactly once (`split_frontmatter` raises `SkillError(reason)` with no path; `load_skill` catches it and adds the path, with no second prefix). `iter_skills(root: Optional[Path] = None) -> List[Skill]`: for each `root/<dir>/SKILL.md` (sorted by directory name) call `load_skill`; a missing `root` gives `[]`. Numpy docstrings and type hints (Ruff `D` and `ANN`).
- [x] T014 [P] [Found] [M] Implement `_pin.py`.
  - Files: `packages/loop_skills/src/loop_skills/_pin.py`
  - Needs: T010
  - Wave: 4
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_pin.py` passes and `ruff check packages/loop_skills` exits 0.
  - Context: `@dataclass(frozen=True) class PinResult: requirement: str; distribution: str; installed: Optional[str]; status: Literal["ok", "outside", "missing"]; message: str`. `Literal` comes from `typing_extensions` only if needed; Python 3.9 has `typing.Literal`. `check_pin(requires: str, lookup: Optional[Callable[[str], Optional[str]]] = None) -> PinResult`. Parse with `packaging.requirements.Requirement(requires)`. Default `lookup`: `importlib.metadata.version(dist)`, returns `None` on `PackageNotFoundError`. Inside means `req.specifier.contains(installed, prereleases=True)`. Messages: missing: `f"{dist} is not installed. Install it with: pip install '{requires}'"`; outside: `f"{dist} {installed} is outside the pin '{requires}' of this skill"`; ok: `f"{dist} {installed} satisfies '{requires}'"`. `distribution` is `req.name` as written. Numpy docstrings and type hints.
- [x] T015 [Found] [M] Implement the syntax part of `_check.py`.
  - Files: `packages/loop_skills/src/loop_skills/_check.py`
  - Needs: T011, T013
  - Wave: 5
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_check_syntax.py` passes and `ruff check packages/loop_skills` exits 0.
  - Context: Types: `@dataclass(frozen=True) class CodeBlock: index: int; line: int; source: str`. `@dataclass(frozen=True) class Problem: skill: str; kind: Literal["frontmatter", "unique", "syntax", "name", "pin"]; detail: str`. `@dataclass(frozen=True) class NameReport: status: Literal["checked", "skipped"]; reason: str; problems: List[Problem]; checked: int; unchecked: int` (declare it now; T016 fills in `check_names`). Functions: `python_blocks(skill: Skill) -> List[CodeBlock]`: scan `skill.body` for fences; a block opens at a line that is exactly ```` ```python ```` and closes at the next line that is exactly ```` ``` ````; `index` counts from 1; `line` is the 1-based line of the opening fence in the SKILL.md file (add the frontmatter line count; compute it from `skill.path` text up to the start of the body). `check_frontmatter_set(skills: Sequence[Skill]) -> List[Problem]`: one `Problem(kind="unique")` for each repeated name, detail names it. `check_syntax(skill: Skill) -> List[Problem]`: `ast.parse` each block; on `SyntaxError` add `Problem(skill.name, "syntax", f"block {index} (line {line}): {err.msg}")`. Import `Skill` from `._skill`. Numpy docstrings and type hints.
- [x] T016 [Found] [M] Implement `check_names` in `_check.py`.
  - Files: `packages/loop_skills/src/loop_skills/_check.py`
  - Needs: T012, T014, T015
  - Wave: 6
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_check_names.py packages/loop_skills/tests/test_check_syntax.py` passes and `ruff check packages/loop_skills` exits 0.
  - Context: Signature `check_names(skill: Skill, roots: Sequence[str] = ("LoopStructural", "map2loop"), lookup: Optional[Callable[[str], Optional[str]]] = None) -> NameReport`. Steps: (1) `dist = Requirement(skill.requires).name`; if `dist` not in `roots`, return `NameReport("skipped", "no pin on a checked package", [], 0, 0)`; (2) `pin = check_pin(skill.requires, lookup)`; if `pin.status != "ok"`, return `NameReport("skipped", pin.message, [], 0, 0)`; (3) for each block from `python_blocks`: `ast.parse`; skip a block that does not parse; (4) walk the statements in source order and keep a dict of bindings: `import a.b` binds `a` to the module `a` and imports `a.b`; `import a.b as c` binds `c` to module `a.b`; `from a.b import X as Y` binds `Y` to `getattr(import_module("a.b"), "X")`, else `import_module("a.b.X")`, else a `Problem(kind="name")`; only imports whose first part is in `roots` count; an import that fails is a `Problem`; `v = Y(...)` where `Y` is bound to a class (`inspect.isclass`) binds `v` to an instance of that class; any other assignment to `v` removes the binding; (5) for each `ast.Attribute` chain `N.a.b` where `N` is bound to a module or a class: walk with `getattr`; a missing attribute is a `Problem`; `checked += 1` for each attribute read; (6) for each `ast.Call` of the form `v.m(...)` where `v` is bound to an instance of class `C`: `hasattr(C, "m")`; missing gives a `Problem`; `checked += 1`; every other attribute read on `v` adds 1 to `unchecked`. A `Problem` has `kind="name"` and a detail with the block number and the missing name. Keyword names and argument values are not checked. Never import a package whose first part is not in `roots`. Return `NameReport("checked", "", problems, checked, unchecked)`. Add the imports `ast`, `inspect`, `importlib` and `Requirement`; import `check_pin` from `._pin`.

## Phase 3: User story 1 - Install and remove the skills (P1)

**Goal**: A user installs the skills for Claude Code, Codex or Copilot with one command, and removes them.
**Independent test**: Run the installer into an empty `tmp_path` for each agent with the fixture skills. Check the files, the warnings and the uninstall result.

- [x] T017 [P] [US1] [M] Test: folder install and uninstall for Claude Code and Codex (spec scenarios 2 to 5, 11 and 12; edge cases; SC-002).
  - Files: `packages/loop_skills/tests/test_install_folders.py`
  - Needs: T003, T013, T014
  - Wave: 5
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_install_folders.py` fails (import error for `loop_skills._install`), then `-k claude` passes after T019 and `-k codex` passes after T020.
  - Context: Import `from loop_skills._install import install, uninstall, InstallError` and `from loop_skills._skill import iter_skills`. Use the good fixture skill only (copy it into a skills folder in `tmp_path`, so `iter_skills(root)` loads). Parametrize the agent with `pytest.param("claude", id="claude")` and `pytest.param("codex", id="codex")`; targets: claude `.claude/skills`, codex `.agents/skills`, both under `base=tmp_path/"proj"`. Signature `install(agent, base, skills, *, force=False, confirm=None, lookup=None) -> InstallReport`. Cases: (1) empty base: the folder `<target>/good-skill/SKILL.md` exists, `<target>/good-skill/.loop-skills.json` holds `{"package": "loop-skills", "version": ...}`, the target folder was created and is in `report.created`; (2) pin outside (`lookup` gives a version outside): `report.warnings` has one line with the pin and the version and the skill is still installed; (3) not installed (`lookup` returns `None`): the warning contains `pip install`; (4) existing skill folder, `confirm=None`: outcome `skipped`, file unchanged, `report.any_skipped` true; (5) existing, `confirm=lambda n: True`: outcome `replaced`; (6) existing, `confirm=lambda n: False`: skipped; (7) existing, `force=True`: replaced; (8) uninstall removes only folders that have the owner file and leaves a folder `other-skill/` with no owner file; (9) write failure: `monkeypatch` `os.rename` (the module `loop_skills._install.os.rename`) to raise `OSError` once; expect `InstallError`, no folder with the prefix `.loop-skills-new-` or `.loop-skills-old-` remains, and no half-written `good-skill`; (10) unwritable target: `monkeypatch` `Path.mkdir` to raise `PermissionError` for the target; expect `InstallError` with the text `Nothing changed` and nothing created; (11) install then uninstall leaves the listing of `base` as before the install, except directories that the installer made are removed when empty. Numpy docstrings and type hints.
- [x] T018 [P] [US1] [S] Test: no network call in install, uninstall and checks (spec scenario 9, FR-003, SC-003).
  - Files: `packages/loop_skills/tests/test_offline.py`
  - Needs: T003
  - Wave: 3
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_offline.py` fails (import error), then passes after T019.
  - Context: Use the fixtures `no_network` and `fixture_skills`. One test: with `no_network`, load `good-skill` with `load_skill`, run `install("claude", tmp_path/"p", [skill], lookup=lambda d: "1.0")`, run `uninstall("claude", tmp_path/"p")`, run `check_syntax(skill)` and `check_names(skill, roots=("json",), lookup=lambda d: "1.0")`. No exception means pass. Imports: `from loop_skills._install import install, uninstall`, `from loop_skills._check import check_names, check_syntax`, `from loop_skills._skill import load_skill`. Numpy docstring and type hints.
- [x] T019 [US1] [M] Implement the agent table and the folder install and uninstall.
  - Files: `packages/loop_skills/src/loop_skills/_agents.py`, `packages/loop_skills/src/loop_skills/_install.py`
  - Needs: T017, T018
  - Wave: 6
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_install_folders.py packages/loop_skills/tests/test_offline.py -k "claude or offline"` passes and `ruff check packages/loop_skills` exits 0.
  - Context: `_agents.py`: `@dataclass(frozen=True) class AgentTarget: kind: Literal["folders", "block"]; relpath: str`; `AGENTS: Dict[str, AgentTarget] = {"claude": AgentTarget("folders", ".claude/skills"), "copilot": AgentTarget("block", ".github/copilot-instructions.md")}` (the Codex row comes in T020). `_install.py`: `SkillOutcome(name, action: Literal["installed","replaced","skipped","removed"], detail: str = "")`; `InstallReport(agent, location: Path, outcomes: List[SkillOutcome], warnings: List[str], created: List[Path])` with property `any_skipped`; `class InstallError(RuntimeError)`. `install(agent, base, skills, *, force=False, confirm=None, lookup=None)`. For `kind == "block"` raise `InstallError("Copilot support is added in stage S3")` (T026 replaces this). Folder steps: (1) `target = base / relpath`; make missing parents with `mkdir(parents=True)` and add each new directory to `created` (collect them before you make them); (2) write test: make and remove a temp folder in `target`; on `OSError` remove `created` (deepest first, only if empty) and raise `InstallError(f"cannot write to {target}: {reason}. Nothing changed.")`; (3) for each skill in name order: warn from `check_pin(skill.requires, lookup)` when `status != "ok"` (add `result.message`); if `target/name` exists: replace when `force` or (`confirm` is not None and `confirm(name)`), else outcome `skipped` with detail `exists; use --force` and continue; `shutil.copytree` the folder to `target/.loop-skills-new-<name>`; write `.loop-skills.json` (`{"package": "loop-skills", "version": loop_skills.__version__}`) in it; if replacing: `os.rename` the old folder to `.loop-skills-old-<name>`, `os.rename` the new folder to `<name>`, `shutil.rmtree` the old; on failure restore the old folder, delete the new folder, raise `InstallError`; if new: `os.rename` the new folder to `<name>`; on failure delete the new folder and raise `InstallError`. Use `os.rename` through the module name `os` so that the test can patch it. `uninstall(agent, base)`: for each direct subfolder of the target with a valid `.loop-skills.json` whose `package == "loop-skills"`: `shutil.rmtree`, outcome `removed`; after the removals, delete `target` if it is empty, then delete each parent folder up to (but not including) `base` if it is empty (this makes install then uninstall restore the folder listing; never delete a folder that holds any entry); a missing target gives an empty report; for `kind == "block"` raise `InstallError("Copilot support is added in stage S3")`. Import `check_pin` from `._pin` and `Skill` from `._skill`. Numpy docstrings and type hints.
- [x] T020 [US1] [S] Add the Codex row to the agent table (spec FR-007).
  - Files: `packages/loop_skills/src/loop_skills/_agents.py`
  - Needs: T019
  - Wave: 7
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_install_folders.py -k codex` passes.
  - Context: In `AGENTS` add the key `"codex"` with `AgentTarget("folders", ".agents/skills")` between `claude` and `copilot`. OP3 is answered in `plan.md` ("Answers"): the folder is `.agents/skills`.
- [x] T021 [P] [US1] [M] Test: the command line for Claude Code and Codex (exit codes, output).
  - Files: `packages/loop_skills/tests/test_cli.py`
  - Needs: T003, T013
  - Wave: 5
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_cli.py` fails (import error for `loop_skills.cli`), then passes after T022.
  - Context: Import `from loop_skills.cli import main`. In each test patch the skills source: `monkeypatch.setattr("loop_skills.cli.iter_skills", lambda: skills)` where `skills` loads `good-skill` from `fixture_skills`; patch the version lookup with `monkeypatch.setattr("loop_skills.cli.version_lookup", fake_lookup)` (the CLI keeps a module-level `version_lookup: Optional[Callable] = None` and passes it as `lookup`). Cases: (1) `main(["install", "--agent", "claude", "--dir", str(tmp)])` returns `0` and the skill folder exists; (2) the same for `--agent codex`; give this test an id that contains `codex` (it passes only after T020); (3) a second install with no terminal (patch `sys.stdin.isatty` to false) returns `3` and the output names `good-skill` and `skipped`; (4) with `--force` it returns `0`; (5) a read-only target (patch `loop_skills._install.install` to raise `InstallError("boom")`) returns `1` and the output has `boom`; (6) `main(["install"])` raises `SystemExit` with code `2` (missing `--agent`); (7) `main(["--version"])` prints the version and returns `0` (argparse `version` action raises `SystemExit(0)`); (8) with a terminal (patch `isatty` to true and `builtins.input` to return `y`) an existing skill is replaced and `main` returns `0`; (9) `main(["uninstall", "--agent", "claude", "--dir", str(tmp)])` returns `0` and removes the folder. Use `capsys`. Numpy docstrings and type hints.
- [x] T022 [US1] [M] Implement the command line.
  - Files: `packages/loop_skills/src/loop_skills/cli.py`, `packages/loop_skills/src/loop_skills/__main__.py`
  - Needs: T019, T021
  - Wave: 7
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_cli.py -k "not codex and not copilot"` passes, `uv run --package loop-skills loop-skills --version` prints `0.1.0`, and `ruff check packages/loop_skills` exits 0.
  - Context: `main(argv: Optional[Sequence[str]] = None) -> int`. The CLI imports the installer as a module (`from . import _install`) and calls `_install.install(...)` and `_install.uninstall(...)`, so that a test can patch them. Module-level names (tests patch them): `from ._skill import iter_skills`, `version_lookup: Optional[Callable[[str], Optional[str]]] = None`. `argparse` with `prog="loop-skills"`, `--version` (`version=f"loop-skills {__version__}"`), sub commands `install` and `uninstall`; each has required `--agent` with choices `["claude", "codex", "all"]` (T026 adds `copilot`), and `--dir` (default `.`); `install` has `--force`. `--agent all` runs the agents in the order of `AGENTS` (use a helper `_agents_for(choice)` that returns the names; T026 changes it to include `copilot`). `confirm` is `None` unless `sys.stdin.isatty() and sys.stdout.isatty()`; with a terminal it asks `Replace skill '<name>'? [y/N] ` through `input()` and accepts `y` or `yes` (any case). Output: one line per outcome (`<agent>: <action> <name> <detail>`), then each warning with the prefix `warning: `, then one summary line. Exit codes: `0` done (warnings allowed); `1` after `InstallError` (print `error: <message>` to stderr); `2` usage error (argparse); `3` done but some skill was skipped. `__main__.py`: `from .cli import main` and `raise SystemExit(main())`. Numpy docstrings and type hints.

### Copilot

- [x] T023 [P] [US1] [M] Test: the Copilot block (spec scenarios 12 and 17, FR-018).
  - Files: `packages/loop_skills/tests/test_install_copilot.py`
  - Needs: T003, T013
  - Wave: 5
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_install_copilot.py` fails (import error for `loop_skills._copilot`), then passes after T024.
  - Context: Import `from loop_skills._copilot import BEGIN, END, install_block, render_block, uninstall_block` and `InstallError` from `loop_skills._install`. `BEGIN == "<!-- loop-skills:begin -->"`, `END == "<!-- loop-skills:end -->"`. Path: `base/.github/copilot-instructions.md`. Signature `install_block(base: Path, skills: Sequence[Skill], version: str) -> InstallReport`. Cases: (1) no file: the file is created and holds the block only; `report.created` has the file and the `.github` folder; (2) a file with the text `My rules\n`: after install the text outside the markers is byte-equal (`text.replace(block, "")` rule: the old text is a prefix) and the block follows after one blank line; (3) a second install replaces only the text between the markers (the text before and after is byte-equal; the outcome is `replaced`); (4) a file with `BEGIN` and no `END` raises `InstallError` with the text `markers` and the file is byte-equal after; (5) a CRLF file keeps CRLF in the block and in the old text; (6) the block holds `## Skill: good-skill`, the description and the body, and the line `<!-- Managed by loop-skills 0.1.0. Change text outside these markers only. -->` for `version="0.1.0"`; (7) `uninstall_block` removes the block and the blank line before it, keeps `My rules\n`, and leaves an empty file in place if only the block was there; (8) `uninstall_block` on a file with no markers or no file returns an empty report and changes nothing. Numpy docstrings and type hints.
- [x] T024 [US1] [M] Implement `_copilot.py`.
  - Files: `packages/loop_skills/src/loop_skills/_copilot.py`
  - Needs: T019, T023
  - Wave: 7
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_install_copilot.py` passes and `ruff check packages/loop_skills` exits 0.
  - Context: Constants `BEGIN`, `END` (exact text in T023). `render_block(skills, version, newline="\n") -> str` (split the description and the body with `splitlines()` and join EVERY line of the block with `newline`, so that a CRLF file has no lone LF): `BEGIN`, the line `<!-- Managed by loop-skills {version}. Change text outside these markers only. -->`, an empty line, then for each skill in the given order: `## Skill: {name}`, empty line, `{description}`, empty line, `{body}` (strip leading and trailing blank lines of the body), empty line; then `END`. Join with `newline`. `install_block(base, skills, version)`: path `base/".github"/"copilot-instructions.md"`; read with `open(path, newline="")` (empty text if the file is missing); newline is `"\r\n"` if the text contains it, else `"\n"`; if `BEGIN` and a later `END` are in the text, replace from the start of `BEGIN` to the end of `END` with the block (outcome `replaced`); if only one marker, or `END` before `BEGIN`, raise `InstallError(f"the markers in {path} are damaged. Nothing changed.")`; else append: the old text, then one blank line if the old text is not empty and does not end with a blank line, then the block and a final newline (outcome `installed`); write to `<path>.loop-skills-tmp` with `newline=""` and `os.replace` onto `path`; make `.github` if needed; record made paths in `created`; add pin warnings with `check_pin(skill.requires)` for each skill when not `ok`; one `SkillOutcome` per skill. `uninstall_block(base)`: remove from `BEGIN` to the end of `END` plus its line end, and one blank line before it if present; same temp-file write; keep the file; no markers or no file gives an empty report. Return `InstallReport("copilot", path, outcomes, warnings, created)`. Import `InstallReport`, `InstallError`, `SkillOutcome` from `._install`. Numpy docstrings and type hints.
- [x] T025 [US1] [S] Test: Copilot cases in the command line tests.
  - Files: `packages/loop_skills/tests/test_cli.py`
  - Needs: T022, T024
  - Wave: 8
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_cli.py -k copilot` fails (the choice `copilot` is not allowed), then passes after T026.
  - Context: Add to the existing file, with the same patching of `iter_skills` and `version_lookup` as the other tests. Cases with ids that contain `copilot`: (1) `main(["install", "--agent", "copilot", "--dir", str(tmp)])` returns `0` and `.github/copilot-instructions.md` has the markers; (2) `main(["install", "--agent", "all", "--dir", str(tmp)])` returns `0` and creates `.claude/skills/good-skill`, `.agents/skills/good-skill` and the Copilot file (SC-002); (3) `main(["uninstall", "--agent", "all", "--dir", str(tmp)])` removes the two folders and the block; (4) a Copilot file with a damaged marker gives exit code `1`. Numpy docstrings and type hints.
- [ ] T026 [US1] [M] Connect Copilot to the installer and the command line.
  - Files: `packages/loop_skills/src/loop_skills/_install.py`, `packages/loop_skills/src/loop_skills/cli.py`
  - Needs: T020, T024, T025
  - Wave: 9
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests` (all tests except `names`) passes with `-m "not names"` and `ruff check packages/loop_skills` exits 0.
  - Context: In `_install.py` replace the two `raise InstallError("Copilot support is added in stage S3")` branches: `install` calls `_copilot.install_block(base, skills, __version__)` for `kind == "block"`; `uninstall` calls `_copilot.uninstall_block(base)`. Import `_copilot` inside the functions (a lazy import) to avoid an import cycle, because `_copilot` imports `InstallReport` from `_install`. In `cli.py` add `copilot` to the `--agent` choices of both sub commands and make `_agents_for("all")` return `["claude", "codex", "copilot"]`. Keep `confirm` unused for Copilot (the block is owned by its markers, see OP5).

## Phase 4: User stories 2 to 4 - The skills (P1 to P3), plugin and docs

**Goal**: Four skills ship in the package, with a Claude Code plugin manifest and full documentation.
**Independent test**: `test_shipped_skills.py` finds exactly the four skills with valid frontmatter, pins, parsed code blocks and fewer than 500 lines. The name check passes in the Ubuntu CI job.

- [x] T027 [P] [US2] [M] Test: the shipped skills (spec scenario 1 and 6, stories 2 to 4 scenario 1, SC-001, SC-003, FR-016).
  - Files: `packages/loop_skills/tests/test_shipped_skills.py`
  - Needs: T003, T013, T015
  - Wave: 6
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_shipped_skills.py` fails (no skill is there), then passes after T029 to T032.
  - Context: Expected names `["build-model", "inspect-model", "map2loop-prepare", "install-help"]`. Expected pin distributions: `build-model` and `inspect-model`: `LoopStructural`; `map2loop-prepare`: `map2loop`; `install-help`: `loop-skills`. Use `iter_skills()` (default root) and parametrize by the expected names so that each name is one test id (`-k build-model`). Tests: (1) `test_skill_set_is_exact`: `[s.name for s in iter_skills()] == sorted(expected)`; (2) per name `test_skill_valid`: the skill loads, `requires` parses and the distribution is the expected one; (3) per name `test_skill_size`: `len(path.read_text(encoding="utf-8").splitlines()) < 500`; (4) per name `test_skill_folder_has_only_skill_md`: the folder holds exactly one entry, `SKILL.md`; (5) per name `test_skill_code_parses`: `check_syntax(skill) == []` and the skill has at least one Python block for `build-model`, `inspect-model` and `map2loop-prepare`; (6) `test_names_unique`: `check_frontmatter_set(iter_skills()) == []`. Numpy docstrings and type hints.
- [x] T028 [P] [US2] [S] Test: the name check on the shipped skills (SC-004, FR-013).
  - Files: `packages/loop_skills/tests/test_shipped_names.py`
  - Needs: T003, T016
  - Wave: 7
  - Done when: `uv run --package loop-skills --extra checks pytest packages/loop_skills/tests/test_shipped_names.py -m names -k build-model` fails (the skill is missing), then passes after T029.
  - Context: Mark the module with `pytestmark = pytest.mark.names`. Parametrize by the three names `["build-model", "inspect-model", "map2loop-prepare"]` (so ids are the names). For each: find the skill with `iter_skills()` (fail with a clear message if missing), run `report = check_names(skill)`, assert `report.status == "checked"` (a skipped check fails the test, with `report.reason` in the message) and `report.problems == []`. Print `report.checked` and `report.unchecked` with `print`. Imports: `from loop_skills._check import check_names`, `from loop_skills._skill import iter_skills`. Numpy docstring and type hints.
- [x] T029 [P] [US2] [M] Write the `build-model` skill.
  - Files: `packages/loop_skills/src/loop_skills/skills/build-model/SKILL.md`
  - Needs: T027, T028
  - Wave: 8
  - Done when: `uv run --package loop-skills --extra checks pytest packages/loop_skills/tests/test_shipped_skills.py packages/loop_skills/tests/test_shipped_names.py -k build-model` passes.
  - Context: Frontmatter: `name: build-model`; a `description` that says when an agent uses the skill (build a LoopStructural `GeologicalModel` from CSV tables of contacts, orientations and a stratigraphic order, then plot a first section); `requires: LoopStructural>=1.11,<2`. Body sections: when to use; input tables (contacts: `X`, `Y`, `Z`, `feature_name`, `val`; orientations: `X`, `Y`, `Z`, `feature_name` and either `gx`, `gy`, `gz` or `strike` and `dip`); steps (load the CSV files with pandas, make the `GeologicalModel` with a bounding box from the data, give it the data, add foliations in stratigraphic order, plot a first section); common errors. Take every API name from the `LoopStructural` source (`LoopStructural/modelling/core/geological_model.py` and `LoopStructural/datasets/`) and the core documentation in `docs/source`; do not write a name from memory. Use ```` ```python ```` blocks that parse. Fewer than 500 lines. No other file in the folder. Use ASD-STE100 Simplified Technical English in the prose.
- [x] T030 [P] [US3] [M] Write the `inspect-model` skill.
  - Files: `packages/loop_skills/src/loop_skills/skills/inspect-model/SKILL.md`
  - Needs: T027, T028
  - Wave: 8
  - Done when: `uv run --package loop-skills --extra checks pytest packages/loop_skills/tests/test_shipped_skills.py packages/loop_skills/tests/test_shipped_names.py -k inspect-model` passes.
  - Context: Frontmatter: `name: inspect-model`; a `description` (inspect a saved model or a model script: list the features, show their data, find common problems); `requires: LoopStructural>=1.11,<2`. Body sections: when to use; load a model or run a model script; list the features and their data; checks for common problems (missing data, bad bounds, empty features); how to report the result. Take every API name from the `LoopStructural` source and the core documentation; do not write a name from memory. Use ```` ```python ```` blocks that parse. Fewer than 500 lines. No other file in the folder. ASD-STE100 prose.
- [x] T031 [P] [US4] [M] Write the `map2loop-prepare` skill.
  - Files: `packages/loop_skills/src/loop_skills/skills/map2loop-prepare/SKILL.md`
  - Needs: T027, T028
  - Wave: 8
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_shipped_skills.py -k map2loop-prepare` passes. The name check for this skill runs in the Ubuntu CI job (`-m names -k map2loop-prepare`) because `map2loop` needs GDAL.
  - Context: Frontmatter: `name: map2loop-prepare`; a `description` (use `map2loop` to turn map data into the contact and orientation tables that the `build-model` skill needs); `requires: map2loop>=3.5,<4`. Body sections: when to use; the map data inputs; the `map2loop` steps that make the contact and orientation tables (same columns as `build-model`); hand-over to `build-model`. Take every API name from `packages/map2loop/src/map2loop/` and its documentation; do not write a name from memory. If GDAL is not installed locally, read the source and check names by reading only; CI runs the name check. Use ```` ```python ```` blocks that parse. Fewer than 500 lines. No other file in the folder. ASD-STE100 prose.
- [ ] T032 [US1] [M] Write the `install-help` skill.
  - Files: `packages/loop_skills/src/loop_skills/skills/install-help/SKILL.md`
  - Needs: T027, T028, T026
  - Wave: 10
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_shipped_skills.py -k install-help` passes.
  - Context: Frontmatter: `name: install-help`; a `description` (check and fix the skill install and the versions); `requires: loop-skills>=0.1,<1`. Body sections: check which skills are installed (folders `.claude/skills`, `.agents/skills`; block in `.github/copilot-instructions.md` between `<!-- loop-skills:begin -->` and `<!-- loop-skills:end -->`); run `loop-skills install --agent claude|codex|copilot|all [--dir DIR] [--force]` and `loop-skills uninstall --agent ... [--dir DIR]`; read the version warnings (a core version outside the pin; a core that is not installed) and fix them with `pip install '<pin>'`; exit codes `0`, `1`, `2`, `3` (3 = some skill was skipped; run again with `--force` after you check that the old skill can go). Use ```` ```bash ```` blocks for commands (not Python blocks). Fewer than 500 lines. No other file in the folder. ASD-STE100 prose.
- [x] T033 [P] [US1] [S] Test: the plugin files (spec scenario 1, FR-005).
  - Files: `packages/loop_skills/tests/test_plugin.py`
  - Needs: T003, T007
  - Wave: 4
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_plugin.py` fails (the files are missing), then passes after T034.
  - Context: Package root `Path(__file__).resolve().parents[1]`; plugin root `<package root>/src/loop_skills`. Repository root `parents[3]`. Cases: (1) `<plugin root>/.claude-plugin/plugin.json` is valid JSON, `name == "loop-skills"`, has a `version` and a `description`; (2) `<plugin root>/skills` is a folder that holds the four skill names; (3) the `version` in `plugin.json` equals the `version` in `packages/loop_skills/pyproject.toml` (regex `^version\s*=\s*"([^"]+)"`) and the value of `packages/loop_skills` in `.release-please-manifest.json` (skip this case if the manifest is not found); (4) `<repo root>/.claude-plugin/marketplace.json` is valid JSON with a `plugins` list that has an entry with `name == "loop-skills"` and `source == "./packages/loop_skills/src/loop_skills"` (skip if the repository root has no `.claude-plugin`). Numpy docstrings and type hints.
- [ ] T034 [US1] [M] Write the plugin manifest and the marketplace file.
  - Files: `packages/loop_skills/src/loop_skills/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
  - Needs: T033, T029, T030, T031, T032
  - Wave: 11
  - Blocked by: OP2
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_plugin.py` passes.
  - Context: First check the current Claude Code documentation for the exact fields of `plugin.json` and `marketplace.json` (OP2). Do not start before OP2 has an answer in `plan.md` ("Answers"). The plan fields: `plugin.json` = `{"name": "loop-skills", "version": "0.1.0", "description": "Agent skills for LoopStructural and map2loop models"}`. `marketplace.json` = `{"name": "loop3d", "owner": {"name": "Loop3D"}, "plugins": [{"name": "loop-skills", "source": "./packages/loop_skills/src/loop_skills", "description": "Agent skills for LoopStructural and map2loop models"}]}`. If the documentation needs other fields, add them and update the plan and `test_plugin.py`. The version in `plugin.json` must equal the package version (release-please updates it, see T007).
- [x] T035 [P] [US1] [S] Test: the documentation names the agent targets (spec scenario 10, FR-009).
  - Files: `packages/loop_skills/tests/test_docs.py`
  - Needs: T003
  - Wave: 3
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_docs.py` fails (the README is a stub), then passes after T036.
  - Context: Read `packages/loop_skills/README.md` (path `Path(__file__).resolve().parents[1] / "README.md"`). Assert it contains each of: `.claude/skills`, `.agents/skills`, `.github/copilot-instructions.md`, `loop-skills install`, `loop-skills uninstall`. One test function per string is not needed: use `pytest.mark.parametrize`. Numpy docstring and type hints.
- [ ] T036 [US1] [M] Write the full `README.md` of the package.
  - Files: `packages/loop_skills/README.md`
  - Needs: T035, T026
  - Wave: 10
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_docs.py` passes.
  - Context: Sections: what the package is (agent skills for LoopStructural and map2loop; the core never imports it); the four skills and their pins; install routes (the Claude Code plugin through the marketplace `loop3d`, see `.claude-plugin/marketplace.json`; `pip install loop-skills` then `loop-skills install --agent ...`); the three agent targets (Claude Code: `.claude/skills/<name>/SKILL.md`; Codex: `.agents/skills/<name>/SKILL.md`; Copilot: one marked block in `.github/copilot-instructions.md`); `--dir` (use `--dir ~` for a user-wide install) and `--force`; overwrite rules (prompt with a terminal, skip with no terminal); uninstall (removes only what the installer made); version pins and the warnings; exit codes `0`, `1`, `2`, `3`; how to write a new skill (a folder with one `SKILL.md`, frontmatter keys `name`, `description`, `requires`, a PEP 440 range, fewer than 500 lines, Python blocks that parse, names that exist); how to run the tests (`uv run --package loop-skills pytest packages/loop_skills/tests -m "not names"`; the `names` tests need `--extra checks` and GDAL). ASD-STE100 prose.

## Phase 5: Finish

- [ ] T037 [Finish] [M] Mark Stage 7 as done in `ROADMAP.md`.
  - Files: `ROADMAP.md`
  - Needs: T002, T006, T007, T008, T018, T030, T031, T032, T034, T036
  - Wave: 12
  - Done when: `uv run --package loop-skills pytest packages/loop_skills/tests/test_roadmap.py` passes and `grep -n "Stage 7" ROADMAP.md` shows a line that starts with `- [x]`.
  - Context: Change `- [ ] **Stage 7` to `- [x] **Stage 7`. Add a line to the bullet with the four stages done. Add one entry at the end of `## Status log` with the date of the day of the change: the four stages landed, the open points that the answers closed (OP1 to OP5, see `specs/007-loop-skills/plan.md`), and the number of tests from the last run. Do not change other text.
- [ ] T038 [Finish] [M] Run all merge gates and the compatibility check.
  - Files: none
  - Needs: T037
  - Wave: 13
  - Done when: these commands all exit 0: `ruff check LoopStructural packages`; `black --check packages/loop_skills`; `pytest`; `uv run --package loop-skills pytest packages/loop_skills/tests -m "not names"`; `git diff --exit-code master -- LoopStructural tests` (the core and its tests have no change).
  - Context: Also run `uv run --package loop-skills --extra checks pytest packages/loop_skills/tests -m names` if `map2loop` imports on this machine; if it does not import, say in the report that the CI job `loop-skills-names` runs it. Run `uv lock --check`. Report each command and its result. If a command fails, mark this task `[!]` with the reason. Do not fix files of other tasks here.

## Wave table

| Wave | Tasks | Tier [S] | Tier [M] |
|---|---|---|---|
| 1 | T001, T002 | 0 | 2 |
| 2 | T003, T004, T005, T006 | 3 | 1 |
| 3 | T007, T008, T009, T010, T011, T012, T018, T035 | 6 | 2 |
| 4 | T013, T014, T033 | 1 | 2 |
| 5 | T015, T017, T021, T023 | 0 | 4 |
| 6 | T016, T019, T024, T027 | 0 | 4 |
| 7 | T020, T022, T028 | 2 | 1 |
| 8 | T025, T029, T030, T031 | 1 | 3 |
| 9 | T026 | 0 | 1 |
| 10 | T032, T036 | 0 | 2 |
| 11 | T034 | 0 | 1 |
| 12 | T037 | 0 | 1 |
| 13 | T038 | 0 | 1 |

## Critical path

T001 -> T003 -> T009 -> T013 -> T017 -> T019 -> T022 -> T025 -> T026 -> T032 -> T034 -> T037 -> T038

## Dependencies

- Setup: T001 first (it makes the package). T002 (CI) has no dependency. T003 (test scaffold), T004 to T006 (tests) follow T001. T007 follows T004. T008 follows T005.
- Foundation: each module follows its test (T009 to T013, T010 to T014, T011 to T015, T012 to T016). `_check.py` is built in two tasks (T015, then T016).
- Install: tests T017, T018, T021, T023 come first. Then T019 (folders), T020 (Codex row, blocked by OP3), T022 (command line), T024 (Copilot), T025 and T026 (Copilot in the command line).
- Skills: the tests T027 and T028 come first. The skills T029 to T031 run at the same time. T032 (`install-help`) waits for the finished command line (T026). T034 (plugin files) waits for OP2 and all skills.
- Finish: T037 (ROADMAP) waits for all leaves. T038 (all gates) is last.
