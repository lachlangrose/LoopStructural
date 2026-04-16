from __future__ import annotations

__all__ = ["DataRole", "GeologicalSchema", "LoopProject"]


def __getattr__(name: str):
	if name == "DataRole":
		from .role import DataRole

		return DataRole
	if name == "GeologicalSchema":
		from .geologicalschema import GeologicalSchema

		return GeologicalSchema
	if name == "LoopProject":
		from .project import LoopProject

		return LoopProject
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
