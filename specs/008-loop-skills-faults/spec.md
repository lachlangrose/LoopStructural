# Feature spec: loop-skills-faults, fault skill

**Feature**: `008-loop-skills-faults` | **Created**: 2026-11-11 | **Status**: Draft

**Input**: Add a fault skill (`add-faults`) to the `loop-skills` package. The
agent does not only run code. It asks the user for geological knowledge,
measures the observed data, fits the fault displacement profile to match the
observed offsets, and checks the result. Depends on spec 007-loop-skills.
The fold skill is in spec 009-loop-skills-folds.

## User scenarios and tests

### User story 1: Choose fault parameters from geological knowledge (priority: P1)

A geologist has a model and data near a fault. The geologist asks the agent to
add the fault. The skill makes the agent ask for the geological knowledge
first: the sense of displacement (kinematics), the slip direction or pitch,
the dip and the dip variation, the size of the displacement and where it is
largest or zero, the tectonic setting, and the relations to other faults and
their age order. The agent then proposes the fault parameters and says why.

**Why this priority**: A wrong kinematic or dip choice gives a model that
runs but is wrong. The questions are the value of the skill.

**Independent test**: Check the skill text for each required question and
for the rule that the agent states its parameter choice and the reason. Names
and syntax are checked as in spec 007.

**Acceptance scenarios**:

1. **Given** the skill `add-faults`, **when** the structure check runs,
   **then** the skill has a step that asks for each item above before any
   parameter is chosen.
2. **Given** an answer for each item, **when** the agent follows the skill,
   **then** the skill maps each answer to a fault parameter and says what
   the agent must record.
3. **Given** the user cannot answer an item, **when** the agent follows the
   skill, **then** the skill says what the agent does (state the open item
   and choose a documented default only after it tells the user).
4. **Given** a tectonic setting, **when** the agent follows the skill,
   **then** the skill says how the setting limits the kinematic and dip
   choices and tells the agent to state that limit as a hypothesis, not as a
   fact.

### User story 2: Fit the displacement profile to the observed offsets (priority: P1)

The data shows contacts that are offset across the fault. The skill makes the
agent measure the offset of each contact at each place along the fault, then
choose the displacement profile (along strike, along dip and across the
fault) so that the model matches the offsets. The agent compares the fault
surface to the fault points and the orientations before it applies the
displacement.

**Why this priority**: The displacement profile decides the model offset. A
default profile can hide a large misfit.

**Independent test**: A worked example with synthetic data. The model has a
known fault and a known displacement. The skill code runs and the recovered
offset is inside the tolerance of SC-002.

**Acceptance scenarios**:

1. **Given** contacts on both sides of a fault, **when** the agent follows the
   skill, **then** the skill gives the steps to measure the offset of a unit
   across the fault, with its units and its sign.
2. **Given** the measured offsets, **when** the agent follows the skill,
   **then** the skill gives the steps to choose and fit the displacement
   profile, and to check the fit with a plot.
3. **Given** the fault points and orientations, **when** the agent follows the
   skill, **then** the skill gives the check of dip and trace against the data
   before the displacement is applied.
4. **Given** the synthetic example, **when** the example runs in CI, **then**
   the recovered displacement is inside the tolerance of SC-002.

### User story 3: Report the residual and resolve conflicts (priority: P1)

After the model is built, the agent reports where the model offset and the
observed offset disagree. If the user knowledge and the data disagree, the
agent shows both, states the difference, and asks the user to decide. The
agent records each decision.

**Why this priority**: The user must be able to trust and review the model.
The agent must not hide a bad fit or override the user.

**Independent test**: Check the skill text for the residual report, the
conflict rule and the decision record. Check the synthetic example for a
residual table.

**Acceptance scenarios**:

1. **Given** a built model, **when** the agent follows the skill, **then** the
   skill gives a residual table: one row for each measured offset, with the
   observed offset, the model offset and the difference.
2. **Given** a user statement and data that disagree, **when** the agent
   follows the skill, **then** the skill tells the agent to show both, state
   the difference, and ask the user to decide. The skill never tells the
   agent to choose alone.
3. **Given** a decision of the user, **when** the agent follows the skill,
   **then** the skill tells the agent to record the decision and its reason
   in a form that the user can read later.

### User story 4: Install, list and map the skill (priority: P2)

The installer, the plugin and `install-help` treat `add-faults` like the
four skills of spec 007. The skill `inspect-model` lists the fault order and
the fault parameters. The skill `map2loop-prepare` gives fault tables in the
columns that `add-faults` reads.

**Why this priority**: Without it, the skill does not reach the agent, and
the map route does not give the fault data.

**Independent test**: Run the installer into an empty folder for each agent
and count the skills. Compare the column names across the skills.

**Acceptance scenarios**:

1. **Given** an empty skills folder, **when** the user runs `loop-skills
   install`, **then** five skills are in the folder.
2. **Given** the package, **when** the check runs, **then** the plugin lists
   the same five skills and validates.
3. **Given** the skill `install-help`, **when** a reader looks at the skill
   list, **then** it names all five skills.
4. **Given** the skills `map2loop-prepare` and `add-faults`, **when** the
   check runs, **then** the fault table column names agree.
5. **Given** a model with faults, **when** the agent follows `inspect-model`,
   **then** the skill lists the faults in their order with their parameters.

### Edge cases

- A fault table with a missing displacement: the agent asks the user. It does
  not guess a value.
- A fault with no points in the model box: the skill tells the agent how to
  find it (plot the points, check the box) and what to report.
- Two faults with no order: the agent asks for the order and the relation
  (abutting or cutting).
- A fault with no offset contacts: the skill tells the agent to say that the
  profile cannot be fitted, and to ask the user for a displacement and a
  profile from knowledge. The agent states that the profile is not tested by
  data.
- Offsets that disagree along the fault: the skill tells the agent to report
  the spread and ask if the profile has a tip, a bend or a second fault.
- A tectonic setting that does not agree with the observed sense of
  displacement: the agent states the disagreement and asks the user (the
  conflict rule).
- A model built with a `LoopStructural` version outside the pin: the
  installer warns as in spec 007. The skill still installs.
- A fault that is outside the supported cases (see "Out of scope"): the skill
  says so and does not give a partial method.

## Requirements

### Functional requirements

- **FR-001**: The core package `LoopStructural` must import with no
  `loop-skills` installed.
- **FR-002**: The new skill must call only the public `GeologicalModel` API.
- **FR-003**: The installer and the automatic checks must run with no
  network.
- **FR-004**: The package `loop-skills` must ship the skill `add-faults` with
  the plugin and version pin rules of spec 007. The installer rules of 007
  change in one way: the installer copies the whole skill folder, not only
  `SKILL.md` (FR-021).
- **FR-005**: The skill `install-help` and the package README must list the
  new skill. The tests that count the shipped skills must count five.
- **FR-006**: The skill `map2loop-prepare` must give a fault table in the
  column names that `add-faults` reads, in addition to its tables of spec 007.
- **FR-007**: The skill `add-faults` must make the agent ask the user for
  these items before it chooses a parameter: sense of displacement, slip
  direction or pitch, dip and dip variation, displacement size and where it
  is largest or zero, tectonic setting, and fault relations and age order.
- **FR-008**: The skill must make the agent state each parameter choice and
  its reason, and record it.
- **FR-009**: The skill must give the steps to measure the offset of contacts
  across a fault, with the units and the sign.
- **FR-010**: The skill must give the steps to choose and fit the
  displacement profile to the measured offsets, and to check the fit with a
  plot.
- **FR-011**: The skill must give the check of the fault surface against the
  fault points and the orientations.
- **FR-012**: The skill must give a residual table of the observed offset,
  the model offset and the difference after the model is built.
- **FR-013**: When the user knowledge and the data disagree, the skill must
  make the agent show both, state the difference, and ask the user to
  decide. The skill must not tell the agent to choose alone.
- **FR-014**: The skill must treat a tectonic setting as a hypothesis that
  the agent states, and the user confirms.
- **FR-015**: The skill must cover several faults with an order and
  relations.
- **FR-016**: The skill `inspect-model` must list the fault order and the
  fault parameters, in addition to what it lists today.
- **FR-017**: The automatic checks must check the syntax of each Python block
  and each `LoopStructural` name of `add-faults`, as in spec 007. The skill
  must have a `requires` pin that the installer can read.
- **FR-018**: A worked example with synthetic data must run in CI. It must
  use a known fault and a known displacement, and it must give the residual
  table.
- **FR-019**: The file `SKILL.md` of `add-faults` must have at most 350
  lines. Longer material goes in reference files in the skill folder.
- **FR-021**: The installer must copy the whole skill folder (`SKILL.md` and
  its reference files) for Claude Code and Codex. It must keep the owner
  file, the consent rules and the uninstall rules of spec 007 for every
  copied file. For Copilot, the block holds `SKILL.md` only.
  [NEEDS CLARIFICATION: confirm that the Copilot block holds SKILL.md only,
  and that the skill text points to the reference files by name]
- **FR-022**: The skill must cover finite faults with the major, minor and
  intermediate axes and the fault centre, in addition to planar and listric
  faults with a slip vector or a pitch. It must say how the user knowledge
  and the data set the size and the tips.
- **FR-020**: The package version must change as a feature release (minor).
  `loop-skills uninstall` must remove the new skill.

## Success criteria

- **SC-001**: The skill passes the syntax check and the name check in CI,
  with at least 1 checked name (not 0).
- **SC-002**: In the synthetic example, the recovered maximum displacement is
  inside 10 % of the known value, and the residual of each measured offset is inside the same
  tolerance.
- **SC-003**: The structure check finds 6 of 6 required questions (FR-007),
  the conflict rule (FR-013) and the residual table (FR-012) in the skill
  text.
- **SC-004**: The installer puts 5 of 5 skills in an empty folder for each of
  the three agents.
- **SC-005**: The fault table columns of `map2loop-prepare` and `add-faults`
  have 0 mismatches in the check.

## Out of scope

- Folds, the fold frame and refolding. See spec 009-loop-skills-folds.
- Unconformities and intrusions.
- Everything that spec 007 puts out of scope (for example an MCP server).
- Fault geometry that the public `GeologicalModel` fault call does not
  support.

## Risks and way back

- Risk: the agent follows the skill text only in part. A text check finds the
  steps in the skill. It does not prove that an agent follows them. Agent
  trial transcripts are kept as examples in the package docs folder, and CI
  does not run them.
- Risk: a skill gives a wrong argument value that the name check cannot find.
  The synthetic example reduces this risk.
- Way back: `loop-skills uninstall` removes the skill. A patch release can
  drop it. Users can pin `loop-skills` to the last version with four skills.

## Clarifications

- 2026-11-11. Q: Spec name? A: `008-loop-skills-structures`, then split. The
  fault part is `008-loop-skills-faults`. The fold part is
  `009-loop-skills-folds`.
- 2026-11-11. Q: Fault input? A: CSV tables and map2loop output.
- 2026-11-11. Q: What must not change? A: The installer rules of 007, the
  core with no agent dependency, the public `GeologicalModel` API, offline
  use. (Changed later: the installer copies whole skill folders.)
- 2026-11-11. Q: Where does the skill live? A: In `packages/loop_skills`.
- 2026-11-11. Q: Does `map2loop-prepare` change? A: Yes (fault table).
- 2026-11-11. Q: Does `inspect-model` change? A: Yes (fault order and
  parameters).
- 2026-11-11. Q: Dependency? A: Spec 007, on its branch until merged.
- 2026-11-11. Q: Constitution conflict? A: None.
- 2026-11-11. Q: Version bump? A: Minor, by release-please from a `feat`
  commit.
- 2026-11-11. Q: Is a fault skill simple? A: No (user). The skill must fit the
  displacement profile to the observed offsets, use the geological knowledge
  of the user, and include kinematics and dip. The agent must be useful and
  not only run code.
- 2026-11-11. Q: What knowledge must the agent ask for? A: Kinematics
  (sense, slip direction or pitch), dip and dip variation, displacement size
  and where it is largest or zero, fault relations and age order, and the
  tectonic setting (user addition).
- 2026-11-11. Q: How does the agent use the data? A: Measure contact offsets,
  fit the displacement profile, compare the fault surface to the fault points
  and orientations, and report the residual.
- 2026-11-11. Q: Conflict between knowledge and data? A: Show both, state the
  difference, and ask the user to decide.
- 2026-11-11. Q: Extra files in a skill folder? A: Yes. The installer copies
  the whole skill folder (this changes the installer rules of 007).
- 2026-11-11. Q: Synthetic tolerance? A: 10 % of the known displacement.
- 2026-11-11. Q: Fault geometry? A: Planar and listric faults, and finite
  faults with axes (user choice).
- 2026-11-11. Q: Where are trial transcripts? A: In the package docs folder.
- 2026-11-11. Q: Automatic tests? A: Structure check of the skill text, a
  worked example in CI with synthetic data, and agent trial transcripts kept
  as examples (not run in CI).

## Architecture notes

The project has no `arch` block (the architecture source is `ROADMAP.md`).
This spec has no architecture check. Packages touched: `packages/loop_skills`
(grows). The `LoopStructural` core is read-only. Depends on: 007-loop-skills.
