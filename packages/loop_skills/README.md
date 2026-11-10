# loop-skills

Agent skills for LoopStructural and map2loop.

`loop-skills` is a Python package. It holds skills for coding agents.
A skill is a Markdown file that tells an agent how to do one task.
The package installs the skills for Claude Code, Codex and GitHub Copilot.

The LoopStructural core never imports this package.
The package makes no network call.
It runs on Python 3.9 and later, on Windows, Linux and macOS.

## The skills

Each skill has a version pin. The pin names the package that the skill needs.

| Skill | Use | Pin |
| --- | --- | --- |
| `build-model` | Build a LoopStructural model from CSV tables and plot a first section. | `LoopStructural>=1.11,<2` |
| `inspect-model` | Look at a built model: its units, faults and data. | `LoopStructural>=1.11,<2` |
| `map2loop-prepare` | Prepare map data with map2loop for a model. | `map2loop>=3.5,<4` |
| `install-help` | Check and fix the skill install and the versions. | `loop-skills>=0.1,<1` |

## Install

There are two routes.

### Route 1: the Claude Code plugin

The repository holds a plugin marketplace named `loop3d`.
The file is `.claude-plugin/marketplace.json` at the repository root.
It lists the plugin `loop-skills`.
The plugin folder is `packages/loop_skills/src/loop_skills`.

Add the marketplace, then install the plugin:

```bash
claude plugin marketplace add Loop3D/LoopStructural
claude plugin install loop-skills@loop3d
```

In a Claude Code session, use these commands:

```
/plugin marketplace add Loop3D/LoopStructural
/plugin install loop-skills@loop3d
```

Add `--scope project` to the install command to share the plugin with a project.

After an install or an update, run `/reload-plugins` in a running session.
You can also start a new session.

To update the plugin:

```bash
claude plugin marketplace update loop3d
claude plugin update loop-skills@loop3d
```

To remove the plugin:

```bash
claude plugin uninstall loop-skills@loop3d
claude plugin marketplace remove loop3d
```

### Route 2: the pip package

Install the package. Then run the installer for each agent that you use:

```bash
pip install loop-skills
loop-skills install --agent claude
loop-skills install --agent codex
loop-skills install --agent copilot
loop-skills install --agent all
```

You can also run the installer with `python -m loop_skills`.
The value `all` selects the three agents.

## Where the skills go

| Agent | Value of `--agent` | Target |
| --- | --- | --- |
| Claude Code | `claude` | `.claude/skills/<name>/SKILL.md` |
| Codex | `codex` | `.agents/skills/<name>/SKILL.md` |
| Copilot | `copilot` | One block in `.github/copilot-instructions.md` |

The Claude Code and Codex folders are in the project folder.
Each installed skill folder holds the owner file `.loop-skills.json`.
The installer uses this file to know that the folder is its own.

The Copilot block starts with the line `<!-- loop-skills:begin -->`.
It ends with the line `<!-- loop-skills:end -->`.
The installer does not change the text outside these two lines.

## Options

| Option | Meaning |
| --- | --- |
| `--agent` | The target agent: `claude`, `codex`, `copilot` or `all`. This option is required. |
| `--dir` | The base folder. The default is the current folder. |
| `--force` | Replace existing skills with no question. Only `install` has this option. |

For a user-wide install, use the home folder as the base folder:

```bash
loop-skills install --agent all --dir ~
```

## Existing skills

- The installer replaces the Copilot block with no question when the block exists.
- A Claude Code or Codex skill folder needs consent to be replaced.
- With a terminal, the installer asks `Replace skill '<name>'? [y/N]`.
- With no terminal, the installer skips the skill and the exit code is `3`.
- With `--force`, the installer replaces the folder with no question.

## Uninstall

```bash
loop-skills uninstall --agent claude
loop-skills uninstall --agent all --dir ~
```

The command removes only what the installer made.
It removes the skill folders that hold the file `.loop-skills.json`.
It removes the marked block from the Copilot file.
It keeps the Copilot file, even when the file is empty.

## Version pins and warnings

The installer checks the installed version of the package that each skill needs.
It prints a warning when the check fails.
The installer installs the skill anyway.

```
warning: LoopStructural 1.9.0 is outside the pin 'LoopStructural>=1.11,<2' of this skill
warning: map2loop is not installed. Install it with: pip install 'map2loop>=3.5,<4'
```

The general forms are:

- `<dist> <version> is outside the pin '<range>' of this skill`
- `<dist> is not installed. Install it with: pip install '<range>'`

To fix a warning, run the `pip install` command from the warning.
Put the range in single quotes.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Done. |
| `1` | Error. The line `error: <message>` is on stderr. |
| `2` | Usage error. An argument is wrong or missing. |
| `3` | Done, but the installer skipped some skill. |

## Write a new skill

Make the folder `skills/<name>/` in `packages/loop_skills/src/loop_skills/`.
Put one file in it: `SKILL.md`. Do not add other files.
This rule keeps the Copilot block complete.

The file starts with a frontmatter block. These keys are required:

| Key | Value |
| --- | --- |
| `name` | The folder name, in lowercase with hyphens. |
| `description` | One sentence that tells the agent when to use the skill. |
| `requires` | A PEP 440 range, for example `LoopStructural>=1.11,<2`. |

Follow these rules:

- Keep the file to fewer than 500 lines.
- Write code in the fence ```` ```python ````.
- Each Python block must parse.
- Each `LoopStructural` and `map2loop` name must exist in the installed version inside the pin.

The automatic tests check these rules.

## Run the tests

This command runs everywhere:

```bash
uv run --package loop-skills pytest packages/loop_skills/tests -m "not names"
```

The tests marked `names` need the extra `checks`.
This extra installs `LoopStructural` and `map2loop`.
`map2loop` needs GDAL, so these tests run in the Ubuntu CI job:

```bash
uv run --package loop-skills --extra checks pytest packages/loop_skills/tests -m names
```
