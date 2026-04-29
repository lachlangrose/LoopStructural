from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Diagnostic:
    code: str
    message: str
    severity: str = "warning"
    context: dict[str, Any] = field(default_factory=dict)


class LoopApiValidationError(ValueError):
    def __init__(self, diagnostics: list[Diagnostic]):
        self.diagnostics = diagnostics
        summary = "; ".join(f"{d.code}: {d.message}" for d in diagnostics)
        super().__init__(summary)


class DiagnosticCollector:
    def __init__(self, mode: str = "strict"):
        if mode not in {"strict", "warn"}:
            raise ValueError("validation mode must be 'strict' or 'warn'")
        self.mode = mode
        self.items: list[Diagnostic] = []

    def _record(self, code: str, message: str, severity: str, context: dict[str, Any] | None):
        self.items.append(
            Diagnostic(code=code, message=message, severity=severity, context=context or {})
        )

    def require(self, condition: bool, code: str, message: str, context: dict[str, Any] | None = None):
        if condition:
            return
        if self.mode == "strict":
            raise LoopApiValidationError([Diagnostic(code=code, message=message, severity="error", context=context or {})])
        self._record(code=code, message=message, severity="warning", context=context)

    def warn(self, code: str, message: str, context: dict[str, Any] | None = None):
        self._record(code=code, message=message, severity="warning", context=context)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [
            {
                "code": d.code,
                "message": d.message,
                "severity": d.severity,
                "context": d.context,
            }
            for d in self.items
        ]
