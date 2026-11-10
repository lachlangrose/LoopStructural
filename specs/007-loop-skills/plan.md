# Implementation plan: loop-skills, agent skills for Loop models

**Feature**: `007-loop-skills` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

## Open points

- **OP1**: Wording of SC-004 and FR-013. A static check cannot resolve every
  attribute (for example an instance attribute that `__init__` sets). The
  plan checks three kinds of name: imports, dotted paths from an import, and
  methods that code calls on a variable made by `v = Class(...)`. It counts
  all other attribute reads as "unchecked" and does not fail on them.
  Owner: the maintainer. Decision needed: accept "100% of the checked names"
  in SC-004, and say in the spec what "checked" means. Blocks: the wording
  of SC-004 only. Task T-names can start with the plan rule.
- **OP2**: The exact JSON fields of the Claude Code plugin manifest
  (`plugin.json`) and of the marketplace file (`marketplace.json`). The plan
  uses the fields that the author knows. Owner: the implementer of stage S4.
  Check them against the current Claude Code documentation before writing the
  files. Blocks: the manifest and marketplace tasks of stage S4.
- **OP3**: The project skill folder of Codex. The plan uses `.agents/skills`
  because the toolkit of this repository installs the same `SKILL.md` there.
  Owner: the implementer of stage S2. Check the Codex documentation. Blocks:
  the Codex row of the agent table (`_agents.py`).
- **OP4**: The size limit of the Copilot instructions file, if any. The
  block holds the text of four skills (at most 2000 lines, from SC-001).
  Owner: the implementer of stage S3. Measure the real size and compare it
  with the Copilot documentation. Blocks: nothing. The result may add a
  size warning to the installer.
- **OP5**: Re-install policy. A second `install` needs consent for a skill
  folder (spec scenario 5) but replaces the Copilot block with no prompt
  (spec scenario 17). The plan follows the spec. Owner: the maintainer.
  Decision needed: keep this difference, or ask consent for the block too.
  Blocks: nothing.

## Answers

<!-- Leave this section empty until an open point has an answer. -->

- **OP3** (answered 2026-11-10 by the maintainer, at the start of the orchestrator run): use `.agents/skills` as the Codex project skills folder. The maintainer can check the Codex documentation later. T020 is free.

- **OP2** (answered 2026-11-10 from the official Claude Code documentation: plugins/manifest-reference, marketplace-reference, create-marketplace, cli-reference; read by the claude-code-guide agent). The plan fields are correct, with one addition. `plugin.json`: `name` is the only required key; `version`, `description` and `author` (an object with `name`) are optional, but `claude plugin validate` warns when one of them is missing, so the file also has `"author": {"name": "Loop3D"}`. The manifest is `.claude-plugin/plugin.json` under the plugin root; the skills are found automatically in `skills/` of the plugin root. `marketplace.json` at the repository root: required `name`, `owner` (with `name`) and `plugins`; a plugin entry has `name` (equal to the `name` in `plugin.json`) and `source`; a relative `source` must start with `./`, resolves from the marketplace root, and must not contain `..`, so `./packages/loop_skills/src/loop_skills` is valid. A pinned `version` in `plugin.json` means that updates are only picked up when the string changes; release-please changes it (the `extra-files` entry). User commands: `claude plugin marketplace add Loop3D/LoopStructural` and `claude plugin install loop-skills@loop3d` (in a session: `/plugin marketplace add Loop3D/LoopStructural`); update with `claude plugin marketplace update loop3d` and `claude plugin update loop-skills@loop3d`; remove with `claude plugin uninstall loop-skills@loop3d` and `claude plugin marketplace remove loop3d`. Validation: `claude plugin validate <path>` for the marketplace root and for the plugin folder. T034 is free.

**Clarifications from the wave 5 review (2026-11-10).** These close gaps between the tests and the plan. They add no feature.
- The CLI imports the installer as a module and calls `_install.install` and `_install.uninstall` (so that tests can patch them).
- `uninstall` for folder agents deletes the target folder if it is empty after the removals, then each empty parent up to (not including) the base folder.
- `render_block` splits the description and the body with `splitlines()` and joins every line of the block with the detected newline, so a CRLF file has no lone LF.
- The name check keeps its bindings across all Python blocks of one skill, in file order. The blocks of a skill are the steps of one script (for example `model = GeologicalModel(...)` in step 2 and `model.update()` in step 5). A checker that starts again for each block would check no name in the later steps. (Found at wave 8, when the check of `build-model` counted 0 checked names.)
- Copilot install ends the block with one final newline after `END`. Copilot uninstall removes the line end of `END` and one blank line before `BEGIN`, so that install then uninstall restores the old text exactly.

## Summary

The feature adds the package `packages/loop_skills` (pip name `loop-skills`).
The package holds four agent skills as `SKILL.md` files, a small installer
and a set of automatic checks. One copy of the skill files serves two
routes: the Claude Code plugin (the folder `src/loop_skills` is the plugin
root) and the command `loop-skills install` (the files are package data).
Claude Code and Codex get skill folders. Copilot gets one marked block in
`.github/copilot-instructions.md`. Each skill carries a version pin in its
frontmatter. The installer compares the pin with the installed version and
warns. The checks parse the Python code blocks and test that the
`LoopStructural` and `map2loop` names exist. The core library does not
change and does not import the new package.

## Technical context

- **Packages changed**: new `packages/loop_skills`. Shared files:
  `.release-please-config.json`, `.release-please-manifest.json`,
  `.github/workflows/packages.yml`, `.claude-plugin/marketplace.json`
  (new), `ROADMAP.md`, `uv.lock`, `specs/README.md`. No file under
  `LoopStructural/`, `tests/`, `packages/loop_common`,
  `packages/loop_interpolation` or `packages/map2loop` changes.
- **Languages and versions**: Python 3.9 and later (`requires-python =
  ">=3.9"`). Every module starts with `from __future__ import annotations`.
  No Rust.
- **New dependencies**: `packaging` (required: PEP 440 ranges), `pyyaml`
  (required: frontmatter). Extra `tests = ["pytest"]`. Extra `checks =
  ["LoopStructural", "map2loop"]` (used by the name check in CI; resolved
  from the workspace through the existing `[tool.uv.sources]` entries).
- **Public API and import changes**: the console script `loop-skills`
  (`loop_skills.cli:main`) and `python -m loop_skills`. `loop_skills`
  exports only `__version__`. All other modules start with an underscore
  and are not public. The core has no import change.
- **Saved-data format changes**: two new small formats, both owned by this
  package. (1) The owner file `.loop-skills.json` in each installed skill
  folder. (2) The two marker lines of the Copilot block. See "Messages and
  saved data".
- **Coordinate contract**: Not applicable.
- **Performance target**: None specified. The spec has no time target.
- **Platforms and backends**: Windows, Linux and macOS, Python 3.9 and
  later (FR-008). The name check needs `LoopStructural` and `map2loop`.
  `map2loop` needs GDAL, which installs on Ubuntu only in this CI. So the
  name check runs in an Ubuntu job. The installer tests run on all
  platforms with the marker `-m "not names"`.

## Constitution check

| Project rule | Result | How the plan agrees |
|---|---|---|
| Work stays within the existing library and package responsibilities | Pass | A new package under `packages/`. The core does not import it (FR-001). |
| Development commands come from .dev-tools/project.json and the constitution | Pass | Root `pytest` and `ruff check LoopStructural packages` stay. The package test command is added to the package gate below. |
| Both pytest and ruff check LoopStructural packages must pass before merge | Pass | Both run in each stage. The package tests run with `uv run --package loop-skills pytest packages/loop_skills/tests`. |
| Python changes use numpy-style docstrings and type hints; Ruff targets py39 | Pass | The new files are not in the grandfather list in `pyproject.toml`, so `D` and `ANN` apply at once. No new per-file ignore. |
| Black uses line length 100 and preserves string quoting | Pass | `black .` is run before each commit. |
| ROADMAP.md owns architecture stages and decisions; update it when either changes | Pass | Task T-roadmap adds Stage 7 and a status-log entry (FR-015, story 1 scenario 16). |
| Stages can be tested and reversed independently | Pass | Four stages. Each stage is a revert of its commits. See "Stages and rollback". |
| The public GeologicalModel API stays compatible; a break needs a ROADMAP.md decision and a major-version note | Pass | No core change. The skills only describe the API (FR-002). |
| The QGIS plugin stays in its separate repository | Pass | Out of scope in the spec. |
| Feature documents stay under specs/NNN-name/ | Pass | `specs/007-loop-skills/`. |
| Releases use release-please with per-package paths | Pass | Stage S1 adds the path, the manifest entry and the root `exclude-paths` entry. |
| A constitution amendment requires a pull request and maintainer acceptance | Not applicable | No amendment. |

## Design

### Types and data

All types are in `packages/loop_skills/src/loop_skills/`.

`_skill.py`:

```python
@dataclass(frozen=True)
class Skill:
    name: str          # equal to the folder name; ^[a-z0-9]+(-[a-z0-9]+)*$
    description: str   # non-empty
    requires: str      # PEP 440 requirement, e.g. "LoopStructural>=1.11,<2"
    path: Path         # the SKILL.md file
    body: str          # text after the frontmatter

class SkillError(ValueError):
    """A SKILL.md file is not valid. The message names the file."""
```

`_pin.py`:

```python
@dataclass(frozen=True)
class PinResult:
    requirement: str            # the text of the pin
    distribution: str           # e.g. "LoopStructural"
    installed: Optional[str]    # None if not installed
    status: Literal["ok", "outside", "missing"]
    message: str                # text for the user, in plain words
```

`_agents.py`:

```python
@dataclass(frozen=True)
class AgentTarget:
    kind: Literal["folders", "block"]
    relpath: str    # relative to the base directory

AGENTS: Dict[str, AgentTarget] = {
    "claude": AgentTarget("folders", ".claude/skills"),
    "codex": AgentTarget("folders", ".agents/skills"),       # see OP3
    "copilot": AgentTarget("block", ".github/copilot-instructions.md"),
}
```

`_install.py`:

```python
@dataclass
class SkillOutcome:
    name: str
    action: Literal["installed", "replaced", "skipped", "removed"]
    detail: str = ""

@dataclass
class InstallReport:
    agent: str
    location: Path
    outcomes: List[SkillOutcome]
    warnings: List[str]
    created: List[Path]       # directories or files that the run made

    @property
    def any_skipped(self) -> bool: ...

class InstallError(RuntimeError):
    """The installer cannot continue. The message says why and what is unchanged."""
```

`_check.py`:

```python
@dataclass(frozen=True)
class CodeBlock:
    index: int      # 1-based number of the block in the skill
    line: int       # line of the opening fence in SKILL.md
    source: str

@dataclass(frozen=True)
class Problem:
    skill: str
    kind: Literal["frontmatter", "unique", "syntax", "name", "pin"]
    detail: str

@dataclass(frozen=True)
class NameReport:
    status: Literal["checked", "skipped"]
    reason: str                # why skipped; empty if checked
    problems: List[Problem]
    checked: int               # names that the check resolved
    unchecked: int             # attribute reads that the check cannot resolve
```

### Functions and public API

Repository name check: `git grep -n -w "loop_skills\|loop-skills"` found only
the index row of this spec (2026-11-10). PyPI answers 404 for `loop-skills`,
so the pip name is free. All names below are new and live in the new package.

`_skill.py`:

- `skills_root() -> Path`: the folder `skills/` next to the module.
- `split_frontmatter(text: str) -> Tuple[Dict[str, Any], str]`: the text
  must start with a line `---`; the frontmatter ends at the next line `---`.
  `yaml.safe_load` reads it. Raises `ValueError` if a marker is missing or
  the YAML is not a mapping.
- `load_skill(path: Path) -> Skill`: reads UTF-8. Requires the keys
  `name`, `description` and `requires`, each a non-empty `str`. Requires
  `name` to equal the name of the parent folder. Requires `requires` to
  parse with `packaging.requirements.Requirement`. Raises `SkillError`.
- `iter_skills(root: Optional[Path] = None) -> List[Skill]`: every
  `<root>/<dir>/SKILL.md`, sorted by name. `root` defaults to
  `skills_root()`.

`_pin.py`:

- `check_pin(requires: str, lookup: Optional[Callable[[str], Optional[str]]] = None) -> PinResult`.
  `lookup` returns the installed version of a distribution or `None`. The
  default uses `importlib.metadata.version` and returns `None` on
  `PackageNotFoundError`. A version is "inside" when
  `Requirement.specifier.contains(version, prereleases=True)`.
  Messages: `missing`: `"<dist> is not installed. Install it with: pip install '<requires>'"`;
  `outside`: `"<dist> <installed> is outside the pin '<requires>' of this skill"`.

`_install.py`:

- `install(agent: str, base: Path, skills: Sequence[Skill], *, force: bool = False, confirm: Optional[Callable[[str], bool]] = None, lookup=None) -> InstallReport`.
  For `folders` agents see "Behaviour". For `copilot` it calls
  `_copilot.install_block`. `confirm` is `None` when there is no terminal.
- `uninstall(agent: str, base: Path) -> InstallReport`.

`_copilot.py`:

- `BEGIN = "<!-- loop-skills:begin -->"`, `END = "<!-- loop-skills:end -->"`.
- `render_block(skills: Sequence[Skill], version: str, newline: str = "\n") -> str`.
- `install_block(base: Path, skills: Sequence[Skill], version: str) -> InstallReport`.
- `uninstall_block(base: Path) -> InstallReport`.

`_check.py`:

- `python_blocks(skill: Skill) -> List[CodeBlock]`: fenced blocks that open
  with the line ```` ```python ````.
- `check_frontmatter_set(skills: Sequence[Skill]) -> List[Problem]`: kind
  `unique` for a repeated name.
- `check_syntax(skill: Skill) -> List[Problem]`: `ast.parse` for each block;
  one `Problem(kind="syntax")` per block that fails, with the skill name,
  block index, line and the `SyntaxError` text.
- `check_names(skill: Skill, roots: Sequence[str] = ("LoopStructural", "map2loop"), lookup=None) -> NameReport`: see "Behaviour".

`cli.py`:

- `main(argv: Optional[Sequence[str]] = None) -> int`.
- `loop-skills install --agent {claude,codex,copilot,all} [--dir DIR] [--force]`
- `loop-skills uninstall --agent {claude,codex,copilot,all} [--dir DIR]`
- `loop-skills --version`
- `--agent` is required. `--dir` is the base directory and defaults to the
  current directory. For a user-wide install the user gives `--dir ~`.
  There is no user scope option (principle: no feature that the spec does
  not need).
- Exit codes: `0` done (warnings allowed); `1` an `InstallError`; `2` usage
  error (argparse); `3` done, but at least one skill was skipped.

### Messages and saved data

Owner file `<skills folder>/<skill name>/.loop-skills.json`:

```json
{"package": "loop-skills", "version": "0.1.0"}
```

Uninstall removes a folder only if this file exists and `"package"` equals
`"loop-skills"`. A skill folder with no such file is never removed.

Copilot block in `.github/copilot-instructions.md`:

```
<!-- loop-skills:begin -->
<!-- Managed by loop-skills 0.1.0. Change text outside these markers only. -->

## Skill: build-model

<description of the skill>

<body of SKILL.md>

## Skill: inspect-model
...
<!-- loop-skills:end -->
```

Plugin manifest `src/loop_skills/.claude-plugin/plugin.json` (fields: see
OP2):

```json
{
  "name": "loop-skills",
  "version": "0.1.0",
  "description": "Agent skills for LoopStructural and map2loop models"
}
```

Marketplace `.claude-plugin/marketplace.json` at the repository root (fields:
see OP2):

```json
{
  "name": "loop3d",
  "owner": {"name": "Loop3D"},
  "plugins": [
    {"name": "loop-skills", "source": "./packages/loop_skills/src/loop_skills",
     "description": "Agent skills for LoopStructural and map2loop models"}
  ]
}
```

Skill frontmatter (all skills):

```yaml
---
name: build-model
description: Build a LoopStructural GeologicalModel from CSV tables ...
requires: LoopStructural>=1.11,<2
---
```

Pins of the four skills: `build-model` and `inspect-model`:
`LoopStructural>=1.11,<2`. `map2loop-prepare`: `map2loop>=3.5,<4`.
`install-help`: `loop-skills>=0.1,<1`. (Versions at 2026-11-10: core 1.11.0,
`map2loop` 3.5.1, `loop-skills` 0.1.0.)

Rules for all skill files in this release: one file `SKILL.md` per skill
with no other file in the folder (so the Copilot block is complete); fewer
than 500 lines (SC-001); Python code blocks are valid Python and use the
fence ```` ```python ````.

### Behaviour

**Folder install (Claude Code and Codex).** For `install(agent, base, skills, ...)`:

1. `target = base / AGENTS[agent].relpath`. If `target` does not exist, make
   it with `mkdir(parents=True)` and add each new directory to
   `report.created`.
2. Write test: make and remove a temp folder inside `target`. On `OSError`
   remove `report.created` (deepest first, only empty folders) and raise
   `InstallError("cannot write to <target>: <reason>. Nothing changed.")`.
3. For each skill, in name order:
   1. Warn from `check_pin(skill.requires, lookup)`: add `result.message` to
      `report.warnings` when `status != "ok"`. Install in all cases.
   2. If `target/<name>` exists: if `force` is true, replace. Else if
      `confirm` is not `None` and `confirm(name)` returns true, replace.
      Else add `SkillOutcome(name, "skipped", "exists; use --force")` and
      go to the next skill.
   3. Copy the folder with `shutil.copytree` to
      `target/.loop-skills-new-<name>`. Write `.loop-skills.json` into it.
   4. If replacing: rename `target/<name>` to `target/.loop-skills-old-<name>`.
      Rename the new folder to `target/<name>`. Delete the old folder. If a
      step fails, rename the old folder back, delete the new folder and
      raise `InstallError`.
   5. If making a new skill: rename the new folder to `target/<name>`. On
      failure delete the new folder and raise `InstallError`.
   6. Record `SkillOutcome(name, "installed" or "replaced")`.

A failed run therefore never leaves a half-written skill folder. Skills that
finished before the failure stay installed and the report lists them.

**Folder uninstall.** For each direct subfolder of `target` that holds a
valid `.loop-skills.json` (package `loop-skills`): `shutil.rmtree`, record
`"removed"`. Do not touch any other entry. A missing `target` gives an empty
report.

**Copilot install.** `path = base / ".github" / "copilot-instructions.md"`.

1. Read the file with `newline=""` (empty text if the file is missing).
   Detect the newline as `"\r\n"` if the text contains it, else `"\n"`.
2. Make the block with `render_block`.
3. If the text has `BEGIN` and a later `END`: replace the text from the
   start of `BEGIN` to the end of `END` with the block. If it has one marker
   only, or `END` before `BEGIN`: raise `InstallError("the markers in
   <path> are damaged. Nothing changed.")`.
4. Else append: the old text, then a blank line if the old text is not empty
   and does not end with a blank line, then the block.
5. Write to `<path>.loop-skills-tmp` and `os.replace` it onto `path`. Make
   `.github` if needed. Record the made paths in `report.created`.
6. Add the pin warnings as in the folder install. Record one
   `SkillOutcome(name, "installed")` for each skill (a second run records
   `"replaced"`).

**Copilot uninstall.** Remove the text from `BEGIN` to the end of `END`, and
one blank line before it if present. Write with the same temp-file step.
Leave the file in place, even if it is empty. No markers: empty report.

**CLI.** `--agent all` runs the three agents in the order claude, codex,
copilot. `confirm` is `None` unless `sys.stdin.isatty() and
sys.stdout.isatty()`; with a terminal it asks `Replace skill '<name>'? [y/N] `
and accepts `y` or `yes`. The CLI prints one line for each outcome, then the
warnings, then a summary. The version for the Copilot block and the owner
file is `loop_skills.__version__`.

**Name check (`check_names`).**

1. Find the pin distribution: `Requirement(skill.requires).name`. If it is
   not one of the `roots` (the name `loop-skills` for `install-help`), return
   `NameReport("skipped", "no LoopStructural or map2loop pin", [], 0, 0)`.
2. `check_pin` the pin. If `status != "ok"`, return
   `NameReport("skipped", <pin message>, [], 0, 0)`.
3. For each block: `ast.parse`. A block that does not parse is skipped here
   (the syntax check reports it).
4. Build the bindings in source order:
   - `import a.b` binds `a` to the module `a`. Each dotted path is
     imported with `importlib.import_module`; a failure is a `Problem`.
   - `import a.b as c` binds `c` to module `a.b`.
   - `from a.b import X as Y` binds `Y` to `getattr(import_module("a.b"), "X")`;
     if `X` is missing, try `import_module("a.b.X")`; if that fails too, it
     is a `Problem`.
   - Only imports whose first part is in `roots` count.
   - `v = Y(...)` where `Y` is bound to a class (`inspect.isclass`) binds
     `v` to an instance of that class. Any other assignment to `v` removes
     the binding.
5. For each attribute chain `N.a.b` where `N` is bound to a module or a
   class: walk with `getattr`. A missing attribute is a `Problem` and
   `checked` goes up by one for each attribute read.
6. For each call `v.m(...)` where `v` is bound to an instance of class `C`:
   `hasattr(C, "m")`; a missing method is a `Problem`; `checked` goes up by
   one. Every other attribute read on `v` goes into `unchecked`.
7. Keyword names and argument values are not checked (see the spec, "Out of
   scope").

`check_names` never imports a package outside `roots`.

### Stages and rollback

| Stage | Files and behaviour | Acceptance check | Rollback target and compatibility check |
|---|---|---|---|
| S1 | Package skeleton, `_skill.py`, `_pin.py`, `_check.py`, release files, CI jobs, ROADMAP entry, test fixtures. No shipped skill yet. | `pytest packages/loop_skills/tests -m "not names"`; `ruff check LoopStructural packages`; root `pytest`; `git diff --stat master -- LoopStructural tests` is empty. | Revert the S1 commits. The repository returns to the commit before S1. Nothing else depends on the package. |
| S2 | `_agents.py`, `_install.py`, `cli.py`, `__main__.py`; Claude Code and Codex install and uninstall. | Same commands, plus the S2 tests. | Revert the S2 commits. S1 stays valid. |
| S3 | `_copilot.py`; Copilot install and uninstall in the CLI. | Same commands, plus the S3 tests. | Revert the S3 commits. S1 and S2 stay valid and the CLI refuses `--agent copilot` again. |
| S4 | The four skills, the plugin manifest, the marketplace file, `README.md`. | Same commands, plus the name check in the Ubuntu job (`-m names`). | Revert the S4 commits. The package installs no skill, but S1 to S3 stay valid. |

## Test strategy

All new tests are in `packages/loop_skills/tests/`. Tests use `tmp_path`,
and use fixture skills in `tests/fixtures/skills/` (made in S1).

- **Unit and regression tests**:
  - `test_skill.py` (S1): `load_skill` accepts a valid file; rejects a
    missing key, a name that differs from the folder, a bad range, and a
    missing frontmatter marker (spec edge case "damaged skill file", story 1
    scenario 6); `iter_skills` order; repeated name gives a `unique`
    problem.
  - `test_pin.py` (S1): `check_pin` with a fake `lookup`: inside (scenario
    3), outside (scenario 4), missing (scenario 11), pre-release version.
  - `test_check_syntax.py` (S1): a fixture skill with an invalid block
    fails and names the skill and the block (scenario 14).
  - `test_check_names.py` (S1): fixture skill code that uses a real name,
    a missing function, a missing method on a bound variable, an
    unresolvable instance attribute (counted as unchecked); `status` is
    `skipped` when the pin is outside or the package is not installed
    (scenario 15). The fixture uses the standard library name `json` as a
    root through the `roots` argument, so the test needs no heavy package.
  - `test_install_folders.py` (S2): install into an empty folder for
    `claude` and `codex` (scenario 2, SC-002); the folder is created and
    reported; existing skill with no terminal is skipped and reported;
    existing skill with `confirm` true is replaced; `force` replaces;
    `confirm` false skips (scenario 5); a failure injected with
    `monkeypatch` in the rename step leaves no `.loop-skills-new-*` folder
    and no half-written skill (edge case); a read-only target gives
    `InstallError` and `created` is removed (edge case); uninstall removes
    only the folders that have the owner file (scenario 12); a version
    outside the pin gives a warning and still installs (scenario 4); no
    core installed gives the missing warning and still installs (scenario
    11).
  - `test_install_copilot.py` (S3): a file with user text gets the block and
    the text outside the markers is byte-equal before and after (scenario
    17); a second run replaces only the block; a missing file is created; a
    damaged marker gives `InstallError` and the file is unchanged; CRLF
    files keep CRLF; uninstall removes the block and keeps the user text
    (scenario 12).
  - `test_cli.py` (S2, S3): exit codes `0`, `1`, `2`, `3`; `--agent all`
    installs the three targets (SC-002); `--version`; the output names the
    skipped skills.
- **Integration and compatibility tests**:
  - `test_isolation.py` (S1): a subprocess sets `sys.modules["loop_skills"]
    = None` and runs `import LoopStructural` with exit code 0 (scenario 7).
    A second test reads the root `pyproject.toml` and the
    `LoopStructural/` tree and asserts that neither names `loop_skills` or
    `loop-skills` (FR-001).
  - `test_offline.py` (S2): a fixture replaces `socket.socket` with a
    function that raises; the install, the uninstall and the checks pass
    (scenario 9, SC-003).
  - `test_shipped_skills.py` (S4): the shipped skills are exactly the four
    names of FR-016 (scenarios 1, story 3 and 4 scenario 1); each loads
    (scenario 6); each has fewer than 500 lines (SC-001); `build-model` has
    the pin `LoopStructural`, `map2loop-prepare` has the pin `map2loop`,
    `install-help` has the pin `loop-skills`; each folder holds `SKILL.md`
    only; each file passes `check_syntax` (FR-012, SC-003).
  - `test_plugin.py` (S4): `plugin.json` is valid JSON with the key `name`
    equal to `loop-skills`; the folder next to it holds `skills/`; the
    version in `plugin.json`, `pyproject.toml` and
    `.release-please-manifest.json` are equal (scenario 1, release
    consistency).
  - `test_docs.py` (S4): `README.md` contains `.claude/skills`,
    `.agents/skills` and `.github/copilot-instructions.md` (scenario 10,
    FR-009).
  - `test_roadmap.py` (S1): `ROADMAP.md` contains `packages/loop_skills` and
    `loop-skills`; skipped if the file is not found (the sdist case)
    (scenario 16, FR-015).
  - `test_release_files.py` (S1): `.release-please-config.json` has the key
    `packages/loop_skills` and the root `exclude-paths` lists it; the
    manifest has the key.
- **Round-trip tests**: install then uninstall leaves the base directory as
  before for the three agents (a directory listing compare), except that a
  Copilot file made by the installer stays as an empty file (S2, S3).
- **Backend coverage**: Not applicable (no numeric backend).
- **Cross-language fixtures**: Not applicable.
- **Grid and display checks**: Not applicable.
- **Performance check**: None.
- **Name check on the shipped skills** (S4, marker `names`):
  `test_shipped_names.py` runs `check_names` for each shipped skill whose
  pin is `LoopStructural` or `map2loop`. It asserts `status == "checked"`
  and `problems == []` (SC-004). A `skipped` status fails the test, so a
  wrong CI environment cannot pass by skipping.
- **Merge gates**: `pytest` and `ruff check LoopStructural packages` must
  pass. Package gate: `uv run --package loop-skills pytest
  packages/loop_skills/tests -m "not names"` on Windows, Linux and macOS for
  Python 3.9 and later (CI job `loop-skills-installer`, scenario 13). Name
  gate: `uv run --package loop-skills --extra checks pytest
  packages/loop_skills/tests -m names` on Ubuntu (CI job
  `loop-skills-names`, after the GDAL steps of the `map2loop-test` job). The
  marker `names` is declared in the `pyproject.toml` of the package.

## Project structure

### packages/loop_skills (new)

**Responsibility**: the skill text, the plugin manifest, the installer and
the checks.

**Files**:

- `packages/loop_skills/pyproject.toml` - Create (S1). `name = "loop-skills"`,
  `version = "0.1.0"`, `requires-python = ">=3.9"`, dependencies `packaging`
  and `pyyaml`, extras `tests` and `checks`, `[project.scripts]`
  `loop-skills = "loop_skills.cli:main"`, setuptools `where = ["src"]`,
  `[tool.setuptools.package-data] loop_skills = ["skills/*/SKILL.md"]`,
  `[tool.pytest.ini_options]` with `markers = ["names: needs LoopStructural and map2loop"]`.
- `packages/loop_skills/LICENSE` - Create (S1). Copy of the MIT file of
  `packages/loop_common/LICENSE`.
- `packages/loop_skills/README.md` - Create (S1 stub, S4 full). Install
  routes, the three agent targets (FR-009), the commands, exit codes, how
  to write a new skill (frontmatter and pin rules).
- `packages/loop_skills/src/loop_skills/__init__.py` - Create (S1).
  `__version__ = version("loop-skills")` with the fallback `"0+unknown"`.
- `packages/loop_skills/src/loop_skills/__main__.py` - Create (S2).
  `raise SystemExit(main())`.
- `packages/loop_skills/src/loop_skills/_skill.py` - Create (S1).
- `packages/loop_skills/src/loop_skills/_pin.py` - Create (S1).
- `packages/loop_skills/src/loop_skills/_check.py` - Create (S1).
- `packages/loop_skills/src/loop_skills/_agents.py` - Create (S2).
- `packages/loop_skills/src/loop_skills/_install.py` - Create (S2).
- `packages/loop_skills/src/loop_skills/_copilot.py` - Create (S3).
- `packages/loop_skills/src/loop_skills/cli.py` - Create (S2); change (S3) to
  allow `copilot` and `all`.
- `packages/loop_skills/src/loop_skills/.claude-plugin/plugin.json` - Create
  (S4).
- `packages/loop_skills/src/loop_skills/skills/build-model/SKILL.md` - Create
  (S4). Sections: when to use; input tables (the table of the spec,
  "Input tables for story 2"); steps to load the CSV files, make the
  `GeologicalModel`, add the data, add foliations in stratigraphic order,
  and plot a first section; common errors. Every API name comes from the
  `LoopStructural` source and the core documentation, and `check_names`
  proves it.
- `packages/loop_skills/src/loop_skills/skills/inspect-model/SKILL.md` -
  Create (S4). Sections: when to use; load a model or run a model script;
  list the features and their data; checks for common problems (missing
  data, bad bounds, empty features); how to report.
- `packages/loop_skills/src/loop_skills/skills/map2loop-prepare/SKILL.md` -
  Create (S4). Sections: when to use; map data inputs; the `map2loop` steps
  to make the contact and orientation tables of story 2; hand-over to
  `build-model`.
- `packages/loop_skills/src/loop_skills/skills/install-help/SKILL.md` -
  Create (S4). Sections: check which skills are installed for each agent;
  run `loop-skills install` and `uninstall`; read the version warnings; fix
  a version outside the pin.
- `packages/loop_skills/tests/__init__.py` - Create (S1), empty.
- `packages/loop_skills/tests/conftest.py` - Create (S1). Fixtures:
  `fixture_skills` (copy of `tests/fixtures/skills` into `tmp_path`),
  `fake_lookup` (dict-based version lookup), `no_network`.
- `packages/loop_skills/tests/fixtures/skills/good-skill/SKILL.md`,
  `packages/loop_skills/tests/fixtures/skills/bad-syntax/SKILL.md`,
  `packages/loop_skills/tests/fixtures/skills/bad-name/SKILL.md`,
  `packages/loop_skills/tests/fixtures/skills/no-pin/SKILL.md` - Create
  (S1). Small files for the S1 tests.
- `packages/loop_skills/tests/test_skill.py`,
  `test_pin.py`, `test_check_syntax.py`, `test_check_names.py`,
  `test_isolation.py`, `test_roadmap.py`, `test_release_files.py` - Create
  (S1), with the coverage listed in "Test strategy". All under
  `packages/loop_skills/tests/`.
- `packages/loop_skills/tests/test_install_folders.py`, `test_cli.py`,
  `test_offline.py` - Create (S2). `test_cli.py` gets its Copilot cases in
  S3.
- `packages/loop_skills/tests/test_install_copilot.py` - Create (S3).
- `packages/loop_skills/tests/test_shipped_skills.py`, `test_plugin.py`,
  `test_docs.py`, `test_shipped_names.py` - Create (S4).

### Repository files (shared)

**Responsibility**: release, CI and architecture records for the new package.

**Files**:

- `.release-please-config.json` - Change (S1). Add `"packages/loop_skills"`
  to the root `exclude-paths`. Add the package entry
  `{"release-type": "python", "component": "loop-skills", "extra-files": [{"type": "json", "path": "src/loop_skills/.claude-plugin/plugin.json", "jsonpath": "$.version"}]}`.
- `.release-please-manifest.json` - Change (S1). Add
  `"packages/loop_skills": "0.1.0"`.
- `.github/workflows/packages.yml` - Change (S1). Add job
  `loop-skills-installer` (matrix `os: ${{ fromJSON(vars.BUILD_OS)}}`,
  `python-version: ${{ fromJSON(vars.PYTHON_VERSIONS)}}`; steps as
  `packages-test`; test command with `-m "not names"`). Add job
  `loop-skills-names` (Ubuntu only; the GDAL steps of `map2loop-test`;
  `uv sync --package loop-skills --extra tests --extra checks`; the GDAL
  `uv pip install` lines of `map2loop-test`; test command with `-m names`).
  Add both jobs to the `needs:` list of `loopstructural-test`.
- `.claude-plugin/marketplace.json` - Create (S4). Content in "Messages and
  saved data" (see OP2).
- `ROADMAP.md` - Change (S1). Add the bullet "Stage 7 — Agent skills
  (`loop-skills`)" after the Stage 6 bullet, with a link to
  `specs/007-loop-skills/`, the decision that the skills live in a separate
  package that the core does not import, and the four-stage list. Add a
  status-log entry dated with the day of the change. Mark Stage 7 done in
  S4.
- `uv.lock` - Change (S1). Run `uv lock` so that the workspace member and
  its extras are recorded. Check that the diff only adds the new package.
- `specs/README.md` - Change (this plan). The row of 007 gets the plan
  status. Change again when the tasks exist.

## Requirement coverage

| Requirement | Design and files | Verification | Gap |
|---|---|---|---|
| FR-001 | No core import; "Technical context" | `test_isolation.py` (scenario 7) | None |
| FR-002 | No core change; stages table | `git diff --stat master -- LoopStructural tests` is empty at each stage (scenario 8) | None |
| FR-003 | No network call in any module | `test_offline.py` (scenario 9) | None |
| FR-004 | Skills `build-model`, `inspect-model` (core), `map2loop-prepare` | `test_shipped_skills.py` | None |
| FR-005 | `src/loop_skills/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | `test_plugin.py` (scenario 1) | OP2 |
| FR-006 | `cli.py`, `_install.py`, package data | `test_cli.py`, `test_install_folders.py` (scenario 2) | None |
| FR-007 | `_agents.py` (`claude`, `codex`, `copilot`) | `test_install_folders.py`, `test_install_copilot.py` | OP3 |
| FR-008 | Pure Python, `pathlib`, no platform call; CI matrix | CI job `loop-skills-installer` (scenario 13) | None |
| FR-009 | `README.md` | `test_docs.py` (scenario 10) | None |
| FR-010 | `Skill`, `load_skill`, frontmatter rules | `test_skill.py`, `test_shipped_skills.py` (scenario 6) | None |
| FR-011 | `_pin.py`, warning step of `install` | `test_pin.py`, `test_install_folders.py` (scenarios 3, 4) | None |
| FR-012 | `check_syntax` | `test_check_syntax.py` (scenario 14) | None |
| FR-013 | `check_names` | `test_check_names.py` (scenario 15), `test_shipped_names.py` | OP1 |
| FR-014 | Missing-pin message in `check_pin`; `install` warning step | `test_install_folders.py` (scenario 11) | None |
| FR-015 | `ROADMAP.md` Stage 7 | `test_roadmap.py` (scenario 16) | None |
| FR-016 | Four skill folders | `test_shipped_skills.py` | None |
| FR-017 | `uninstall`, `uninstall_block`, owner file | `test_install_folders.py`, `test_install_copilot.py` (scenario 12) | None |
| FR-018 | `_copilot.py`, markers | `test_install_copilot.py` (scenario 17) | OP4, OP5 |
| SC-001 | The 500-line rule | `test_shipped_skills.py` | None |
| SC-002 | `--agent all`, the three targets | `test_cli.py`, `test_install_folders.py` | None |
| SC-003 | All checks with `no_network` | CI jobs; no agent runs anywhere | None |
| SC-004 | `check_names` on the shipped skills | `test_shipped_names.py` | OP1 |
| Story 2 scenario 1 (manual) | `build-model` text | Manual run with a real agent and a CSV example. Not in CI. | None |
| Edge cases (unwritable, partial, missing folder, Windows, damaged file) | "Behaviour" | `test_install_folders.py`, `test_install_copilot.py`, `test_skill.py` | None |

## Handover

Other specs and packages use these contracts:

- The command line: `loop-skills install|uninstall --agent ... [--dir] [--force]`
  and the exit codes `0`, `1`, `2`, `3`.
- The skill file contract: a folder `skills/<name>/` that holds one
  `SKILL.md`, with the frontmatter keys `name`, `description` and `requires`.
  A later spec that adds a skill (for example for `loopresources`) adds a
  folder and a pin. It needs no change to the installer.
- The owner file `.loop-skills.json` and the two Copilot marker lines. A
  later change to either format must keep uninstall working for files that
  an older version made.
- The plugin path `packages/loop_skills/src/loop_skills` and the marketplace
  name `loop3d`.
- The version rule: when `LoopStructural` or `map2loop` makes a release that
  changes an API name that a skill uses, the `names` CI job fails. The fix is
  a change of the skill, or of its pin range.

The shared files are `.release-please-config.json`,
`.release-please-manifest.json`, `.github/workflows/packages.yml`,
`ROADMAP.md` and `uv.lock`. Other specs also change these files (spec 001
changed the release files). Merge them with care and run `uv lock` again
after a merge.

## Complexity tracking

None. Every applicable constitution row passes.
