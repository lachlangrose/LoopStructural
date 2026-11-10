# Feature spec: loop-skills, agent skills for Loop models

**Feature**: `007-loop-skills` | **Created**: 2026-11-10 | **Status**: Draft

**Input**: An installable package, `packages/loop_skills`, with agent skills
that help a user build and inspect LoopStructural models.

## User scenarios and tests

### User story 1: Install and remove the skills (priority: P1)

A geologist installs the skills for their agent with one command or one
plugin install. The geologist can also remove them. The installer warns when
the installed core does not match the skills.

**Why this priority**: No other story works until the skills are in the
agent folder. The constitution asks for a way back.

**Independent test**: Run the installer into an empty folder for each agent.
Check the files, the frontmatter, the version warnings, and the uninstall
result. All checks run in CI with no agent and no network.

**Acceptance scenarios**:

1. **Given** the plugin folder of the package, **when** the check runs,
   **then** the plugin manifest is valid. The folder holds all four skills
   with valid frontmatter (name, description).
2. **Given** an empty skills folder of Claude Code or Codex, **when** the
   user runs `loop-skills install` for that agent, **then** the same skill
   set is in the correct folder of that agent. For Copilot, the installer
   writes the skills as one marked block in the Copilot instructions file
   (scenario 17).
3. **Given** an installed core version inside the pin of a skill, **when**
   the installer runs, **then** it reports no version warning.
4. **Given** an installed core version outside the pin of a skill, **when**
   the installer runs, **then** it warns, names the pin and the installed
   version, and still installs the skill.
5. **Given** a target folder that already has a skill with the same name,
   **when** the installer runs, **then** it does not overwrite the skill
   with no consent from the user. With a terminal, the consent is an answer
   to a prompt. With no terminal, the installer skips that skill and reports
   it. With `--force`, the installer overwrites with no prompt.
6. **Given** a skill file, **when** the check runs, **then** the file has a
   unique name, a description, and a version pin that the installer can read.
7. **Given** an environment where `loop-skills` is not installed, **when** the
   user imports `LoopStructural`, **then** the import succeeds (FR-001).
8. **Given** the core test files that exist today, **when** the feature is
   added, **then** those tests pass with no change to the test files
   (FR-002).
9. **Given** an environment with no network, **when** the installer and the
   automatic checks run, **then** they succeed (FR-003).
10. **Given** the package documentation, **when** the check runs, **then** it
    names the install folder of each of the three agents (FR-009).
11. **Given** an environment where the core is not installed, **when** the
    installer runs, **then** it installs the skills, warns that the core is
    missing, and says how to install it (FR-014).
12. **Given** skills that the installer put in a target folder, and one skill
    that the user made with another source, **when** the user runs
    `loop-skills uninstall`, **then** the installer removes only the skills
    it installed and leaves the other skill. For Copilot, it removes only
    the marked block and leaves all other text of the file (FR-017).
13. **Given** the CI matrix of Python 3.9 and later on Windows, Linux and
    macOS, **when** the installer tests run, **then** they pass on each
    combination (FR-008).
14. **Given** a skill with a Python code block that does not parse, **when**
    the check runs, **then** it fails and names the skill and the block
    (FR-012).
15. **Given** a skill code block with a `LoopStructural` or `map2loop` name
    that does not exist in the installed version inside the pin, **when**
    the check runs, **then** it fails and names the skill and the name
    (FR-013).
16. **Given** the repository, **when** the check runs, **then**
    `ROADMAP.md` names the `loop_skills` package and its release path
    (FR-015).

17. **Given** a Copilot instructions file that has user text, **when** the
    user runs `loop-skills install` for Copilot, **then** the installer adds
    the skills between two marker lines and changes no text outside them.
    A second run replaces only the text between the markers (FR-018).

### User story 2: Build a model from tables (priority: P1)

A geologist who writes model scripts gives an agent a data table: contacts,
orientations and a stratigraphic order. The agent uses the `build-model`
skill to make a working `GeologicalModel` and a first section plot. The
agent does not invent API calls that do not exist.

**Why this priority**: Model building is the first task of every user.
Today a general agent often gets the API wrong. This story shows the value
of the skills.

**Independent test**: Check that the `build-model` skill is in the skill set,
with valid frontmatter, a version pin, and parsed code blocks whose names
exist (story 1, scenarios 1, 6, 14, 15). A manual check with a real agent and
a CSV example repeats the story (CI cannot run it).

**Acceptance scenarios**:

1. **Given** CSV tables of contacts, orientations and stratigraphy with the
   standard Loop column names, **when** the user asks the agent to build a
   model, **then** the build skill names the required input tables, the steps
   to make a `GeologicalModel`, and the steps to make a first section plot
   (manual check).

### User story 3: Inspect a model (priority: P2)

A geologist gives an agent a saved model or a model script. The agent uses
the `inspect-model` skill to list the features, show their data, and find
common problems.

**Why this priority**: The user needs to check a model after it is built.

**Independent test**: Check that the `inspect-model` skill is in the skill
set, with valid frontmatter and a version pin (story 1, scenarios 1, 6). A
manual check with a real agent repeats the story.

**Acceptance scenarios**:

1. **Given** the skill set of the package, **when** the check runs, **then**
   `inspect-model` is in the set with valid frontmatter and a version pin for
   the core.

### User story 4: Prepare map data with map2loop (priority: P3)

A geologist gives an agent map data. The agent uses the `map2loop-prepare`
skill to make the input tables for story 2.

**Why this priority**: It extends story 2 to users who start from maps.

**Independent test**: Check that the `map2loop-prepare` skill is in the skill
set, with valid frontmatter and a version pin for `map2loop` (story 1,
scenarios 1, 6). A manual check with a real agent repeats the story.

**Acceptance scenarios**:

1. **Given** the skill set of the package, **when** the check runs, **then**
   `map2loop-prepare` is in the set with valid frontmatter and a version pin
   for `map2loop`.

### Edge cases

- The installed core is newer or older than the pin (story 1, scenario 4).
- A skill with the same name is in the target folder (story 1, scenario 5).
- The core is not installed when the skills install: the skills install and
  the installer warns (FR-014).
- The target folder cannot be written: the installer stops with a clear
  message and changes nothing.
- The install fails in the middle: the installer leaves no half-written
  skill.
- The agent folder does not exist: the installer creates it and reports
  that it did.
- The Copilot instructions file does not exist: the installer creates it
  with the marked block only.
- A skill file is damaged (no frontmatter, or no pin): the check fails and
  names the file.
- The installer runs on Windows: paths and folder names work the same as on
  other systems (story 1, scenario 13).

## Requirements

### Input tables for story 2

- **Contacts**: `X`, `Y`, `Z`, `feature_name`, `val`.
- **Orientations**: `X`, `Y`, `Z`, `feature_name`, and either `gx`, `gy`,
  `gz` or `strike` and `dip`.
- The `build-model` skill holds this table and links to the core docs.

### Functional requirements

- **FR-001**: The core library must not need the skills package. Importing
  `LoopStructural` must work when `loop-skills` is not installed.
- **FR-002**: The skills must describe the public `GeologicalModel` API and
  must not require a change to it.
- **FR-003**: The skills and the installer must work with no network call and
  no Loop service.
- **FR-004**: The first release must cover two packages: the LoopStructural
  core and `map2loop`. Other packages are out of scope for this release.
- **FR-005**: The package must give a Claude Code plugin made from the skill
  files.
- **FR-006**: The package must give a `loop-skills install` command that
  copies the same skill files for pip users.
- **FR-007**: The skills must support Claude Code, Codex and Copilot.
  Claude Code and Codex read `SKILL.md` folders. Copilot gets the skills as
  a block in its instructions file.
- **FR-008**: The installer must run on Python 3.9 and later, on Windows,
  Linux and macOS.
- **FR-009**: The package must document the install folder of Claude Code
  and Codex, and the instructions file of Copilot.
- **FR-010**: Each skill must name the core and package versions that it
  supports (version pin). The pin is a field in the frontmatter of its
  `SKILL.md`. It holds a PEP 440 version range, for example
  `requires: LoopStructural>=1.11,<2`. The `install-help` skill describes
  the installer, so its pin is a range of the `loop-skills` version.
- **FR-011**: The installer must compare the pin of each skill with the
  installed version of the package.
- **FR-012**: The automatic check must parse each Python code block in a
  skill. It does not run the code.
- **FR-013**: The automatic check must find each `LoopStructural` and
  `map2loop` name in a skill code block. It must confirm that the name exists
  in the installed version that is inside the pin. The CI matrix names the
  versions that it tests.
- **FR-014**: If the core is not installed, the installer must install the
  skills, warn that the core is missing, and say how to install it.
- **FR-015**: The feature must record the `loop_skills` package and its
  release path in `ROADMAP.md`.
- **FR-016**: The first release must contain four skills: `build-model`
  (story 2), `inspect-model` (story 3), `map2loop-prepare` (story 4) and
  `install-help` (tells the agent how to check and fix the skill install and
  the versions).
- **FR-017**: The package must give a `loop-skills uninstall` command. It
  removes only the skills that the installer put in the target folder, and
  only the marked block in the Copilot file.
- **FR-018**: For Copilot, the installer must write the skills between two
  marker lines. It must change no text outside the markers.

### Package ownership

- **Owner**: `packages/loop_skills` (new) owns the skill text, the plugin
  manifest and the installer. The core and the other packages own their APIs;
  the skills only describe them.
- **Boundary**: the skill file format (`SKILL.md` folders), the plugin
  manifest and the install command are the public surface of the package.
- **Name**: the folder is `packages/loop_skills`, like the other packages.
  The pip name and the command are `loop-skills`.
- **Release**: the package has its own release path, like the other
  packages.

## Success criteria

- **SC-001**: Each `SKILL.md` has fewer than 500 lines.
- **SC-002**: 3 of 3 agents (Claude Code, Codex, Copilot) get the same four
  skills from one command each. Copilot gets them as a block.
- **SC-003**: The automatic checks (skill validity, installer result, version
  pin parse, example syntax) pass in CI with 0 network calls and 0 agent
  runs.
- **SC-004**: 100% of the `LoopStructural` and `map2loop` names in the skill
  code blocks exist in the installed version inside the pin (FR-013). This is
  the measure for wrong API calls. There is no manual prompt set in this
  release.

## Out of scope

- An MCP server for live model sessions. A later spec can add it.
- Skills for `loopresources`, `loop_interpolation`, `loop_common`,
  `loopstructural_visualisation` and the viewer link (spec 006) in this
  release.
- A CI run of the skill examples. The syntax check and the name check find
  some wrong examples. They do not find a wrong order of calls or a wrong
  argument value. A later spec can add runs.
- Auto-update of installed skills. The user can run the installer again.
- A skill for the QGIS plugin. The plugin stays in its own repository.

## Clarifications

- 2026-11-10. Q: Spec name? A: `007-loop-skills`.
- 2026-11-10. Q: Main user? A: A geologist who writes model scripts (not the
  developer of Loop packages).
- 2026-11-10. Q: Smallest useful result? A: Build a model from tables.
- 2026-11-10. Q: First release scope? A: All Loop packages (replaced by the
  answer on the package list below; see FR-004).
- 2026-11-10. Q: Distribution? A: Claude Code plugin and a pip installer.
- 2026-11-10. Q: Agents? A: Claude Code, Codex and Copilot.
- 2026-11-10. Q: Drift control? A: Version pin only, no CI run of examples.
- 2026-11-10. Q: Input for story 1? A: CSV tables with the standard Loop
  column names.
- 2026-11-10. Q: Automatic checks? A: Skill file validity, installer result,
  version pin parse. No run of examples.
- 2026-11-10. Q: Edge cases? A: Core version outside the pin; skill folder
  already exists.
- 2026-11-10. Q: Numbers? A: Install time and skill size.
- 2026-11-10. Q: Package list for FR-004? A: LoopStructural core and
  map2loop. This replaces the earlier answer "all Loop packages".
- 2026-11-10. Q: Drift risk? A: Accept it; add the example syntax check.
- 2026-11-10. Q: Core not installed? A: Install and warn.
- 2026-11-10. Q: Out of scope? A: No MCP server. Other items open.
- 2026-11-10. Q: Uninstall, auto-update, QGIS skill? A: Uninstall in scope
  (FR-017). Auto-update and QGIS skill out of scope.
- 2026-11-10. Q: Folder and package name? A: `packages/loop_skills`; pip
  name and command `loop-skills`.
- 2026-11-10. Q: Skills in the first release? A: `build-model`,
  `inspect-model`, `map2loop-prepare`, `install-help` (FR-016).
- 2026-11-10. Q: Consent for overwrite? A: Prompt with a terminal; skip and
  report with no terminal; `--force` overwrites.
- 2026-11-10. Q: Columns? A: Core column names (see "Input tables").
- 2026-11-10. Q: Pin format? A: Frontmatter field with a PEP 440 range.
- 2026-11-10. Q: Platforms? A: Python 3.9+ on Windows, Linux, macOS.
- 2026-11-10. Q: Measure for wrong API calls? A: Name check in CI (FR-013 and
  the last success criterion). No manual prompt set.
- 2026-11-10. Q: Reference machine for the install time? A: No time
  target. The install-time criterion is removed and the later criteria are
  renumbered.
- 2026-11-10. Q: What must not change? A: Core has no agent dependency; the
  public `GeologicalModel` API; offline use.
- 2026-11-10. Q: How does Copilot get the skills? A: Claude Code and Codex
  read `SKILL.md` folders (the toolkit installs the same file in both).
  Copilot gets a marked block in its instructions file (FR-007, FR-018).
- 2026-11-10. Q: Pin of `install-help`? A: A range of the `loop-skills`
  version.
- 2026-11-10. Q: Agent folder missing? A: The installer creates it.
- 2026-11-10. Review 2 changes: the install scenarios moved to a new story 1;
  the build story is now story 2. The requirements are renumbered (17 in total).
  The name check compares names with the installed version inside the pin.
