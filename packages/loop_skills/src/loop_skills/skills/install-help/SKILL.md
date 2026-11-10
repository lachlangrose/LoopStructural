---
name: install-help
description: "Use this skill to check and fix the install of the Loop skills for coding agents, and to check the versions of the Loop packages that the skills need."
requires: loop-skills>=0.1,<1
---

# Check and fix the Loop skill install

Use this skill when a Loop skill is missing, old or not found by the agent.
Use it also when the installer prints a warning or a non-zero exit code.
The `loop-skills` command installs the skills. It does not need a network.

## The skills in the package

| Skill | Use |
| --- | --- |
| `build-model` | Build a LoopStructural model from CSV tables and plot a first section. |
| `inspect-model` | Look at a built model: its units, faults and data. |
| `map2loop-prepare` | Prepare map data with map2loop for a model. |
| `install-help` | Check and fix the skill install and the versions (this skill). |

## Where each agent reads the skills

| Agent | Value of `--agent` | Target |
| --- | --- | --- |
| Claude Code | `claude` | `.claude/skills/<name>/SKILL.md` |
| Codex | `codex` | `.agents/skills/<name>/SKILL.md` |
| Copilot | `copilot` | One marked block in `.github/copilot-instructions.md` |

The value `all` selects the three agents.

The Copilot block starts with the line `<!-- loop-skills:begin -->`.
It ends with the line `<!-- loop-skills:end -->`.
The installer does not change the text outside the two lines, except the blank line next to the block.

## Step 1: Check what is installed

The base folder is the project folder. For a user-wide install, the base folder is the home folder.

List the skill folders of the base folder:

```bash
ls .claude/skills .agents/skills
```

Search for the Copilot markers with a search tool:

```bash
grep -n "loop-skills:" .github/copilot-instructions.md
```

Two lines in the result mean that the block exists. One line or no line means that the block is broken or missing.

Read the `requires:` line of each installed skill:

```bash
grep -H "^requires:" .claude/skills/*/SKILL.md .agents/skills/*/SKILL.md
```

A folder that holds the file `.loop-skills.json` belongs to the installer.
Do not edit such a folder by hand. The installer can replace it at any time.

Check the version of the installer:

```bash
loop-skills --version
```

## Step 2: Install or update the skills

Run the installer from the project folder:

```bash
loop-skills install --agent claude
loop-skills install --agent codex
loop-skills install --agent copilot
loop-skills install --agent all
```

Use `--dir` to choose the base folder. The default is the current folder.
For a user-wide install, give the home folder:

```bash
loop-skills install --agent claude --dir ~
loop-skills install --agent codex --dir ~
```

The installer expands a leading `~` itself, so this works in bash, zsh, PowerShell and cmd.
The Copilot target is a file of one repository.
For Copilot, use `--agent copilot` in the project folder.

The installer prints one line for each skill, in this form:

```
<agent>: <action> <name> <detail>
```

The action is `installed`, `replaced` or `skipped`.
For a Copilot install, each skill line shows the skill that is in the block.

Example of a first install:

```
claude: installed build-model
claude: installed inspect-model
claude: installed map2loop-prepare
claude: installed install-help
```

The last line is a summary:

```
4 skill(s) done, 0 skipped
```

With `--agent all`, the summary is `12 skill(s) done, 0 skipped`.
This is 3 agents with 4 skills each. The Copilot block counts one outcome for each skill.

### An existing skill

- With a terminal, the installer asks `Replace skill '<name>'? [y/N]`. It replaces the skill only after the answer `y` or `yes`. Any other answer keeps the old skill.
- With no terminal (the input or the output is piped, for example when an agent runs the command), the installer does not ask. It skips the skill. The line is `<agent>: skipped <name> exists; use --force`.
- With `--force`, the installer replaces the skill with no question.
- The Copilot block is always replaced with no question. The installer owns the text between the markers.

When a skill is skipped, check that you can lose the old skill files. Then run the command again with `--force`:

```bash
loop-skills install --agent all --force
```

## Step 3: Read the warnings

Each skill file names the packages that it needs, with a version range.
Example: `requires: LoopStructural>=1.11,<2`.
The installer checks the installed version of each package. It prints a warning when the check fails.
The installer installs the skill anyway.

A warning can repeat when two skills need the same package.

The package is not installed:

```
warning: LoopStructural is not installed. Install it with: pip install 'LoopStructural>=1.11,<2'
```

The installed version is outside the range:

```
warning: LoopStructural 1.9.0 is outside the pin 'LoopStructural>=1.11,<2' of this skill
```

To fix a warning, run the `pip install` command from the warning.
Put the range in single quotes. Without quotes, the shell reads `>` as a redirect:

```bash
pip install 'LoopStructural>=1.11,<2'
pip install 'map2loop>=3.5,<4'
```

Use the Python environment that the user runs the model code in.
Run the install command again after the fix. No warning line must stay.

## Step 4: Remove the skills

Remove only what the installer made:

```bash
loop-skills uninstall --agent claude
loop-skills uninstall --agent codex --dir ~
```

The command removes the skill folders that hold the file `.loop-skills.json`.
It also removes the `skills` folder and the parent folders (for example `.claude`) when they are empty, up to the base folder.
It never removes a folder that holds any other entry.
It removes the marked block from the Copilot file.
It does not remove the Copilot file, even when the file is empty.

When the Copilot file has no complete block, `uninstall` prints no `removed` line and exits with `0`.
A damaged block (one marker line only) gives the same result.
Run the search from Step 1 to check that the block is gone.
If a stray marker line stays, find it with a search tool.
Put back the missing line, or delete the stray line.

The output lines use the action `removed`:

```
claude: removed build-model
copilot: removed copilot-block
```

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Done. Warnings can be present. |
| `1` | Error. The line `error: <message>` is on stderr. |
| `2` | Usage error. An argument is wrong or missing, for example an unknown `--agent`. |
| `3` | Done, but the installer skipped some skill. |

For code `1`, read the message. Check that the base folder exists and that the user can write to it.
A damaged Copilot block also gives code `1` for `install`. Only one marker line is in the file, or `END` comes before `BEGIN`.
The message is `error: the markers in <path> are damaged. Nothing changed.`
Find the stray marker line with a search tool. Put back the missing line, or delete the stray line. Then run the command again.
For code `2`, read the usage text that the command prints.
For code `3`, see the section "An existing skill". Run again with `--force` after you check that you can lose the old skill files.

## Checks before you finish

1. The command exits with `0`.
2. The skill folders (or the Copilot block) exist in the base folder.
3. The command prints no warning, or the user accepts the warnings.
4. The agent is restarted, so that it reads the new skills.
