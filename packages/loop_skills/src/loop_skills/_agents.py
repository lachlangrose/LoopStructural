"""Table of the agents that can receive skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = ["AGENTS", "AgentTarget"]


@dataclass(frozen=True)
class AgentTarget:
    """Where and how skills go for one agent.

    Attributes
    ----------
    kind : Literal["folders", "block"]
        ``folders`` copies one folder for each skill. ``block`` writes a
        managed block in one instruction file.
    relpath : str
        Path of the target, relative to the base folder.
    """

    kind: Literal["folders", "block"]
    relpath: str


AGENTS: dict[str, AgentTarget] = {
    "claude": AgentTarget("folders", ".claude/skills"),
    "copilot": AgentTarget("block", ".github/copilot-instructions.md"),
}
