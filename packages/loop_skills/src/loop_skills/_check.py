"""Check the frontmatter set and the Python code blocks of skills."""

from __future__ import annotations

import ast
import importlib
import inspect
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Literal

from packaging.requirements import Requirement

from ._pin import check_pin
from ._skill import Skill


@dataclass(frozen=True)
class CodeBlock:
    """One fenced Python block of a skill body.

    Attributes
    ----------
    index : int
        Number of the block in the skill. The first block is 1.
    line : int
        1-based line of the opening fence in the SKILL.md file.
    source : str
        Code text between the fences.
    """

    index: int
    line: int
    source: str


@dataclass(frozen=True)
class Problem:
    """One problem that a check found.

    Attributes
    ----------
    skill : str
        Name of the skill.
    kind : Literal["frontmatter", "unique", "syntax", "name", "pin"]
        Type of the check that failed.
    detail : str
        Text that explains the problem.
    """

    skill: str
    kind: Literal["frontmatter", "unique", "syntax", "name", "pin"]
    detail: str


@dataclass(frozen=True)
class NameReport:
    """Result of the name check.

    Attributes
    ----------
    status : Literal["checked", "skipped"]
        Whether the check ran.
    reason : str
        Reason for a skipped check. Empty when the check ran.
    problems : list[Problem]
        Problems that the check found.
    checked : int
        Number of names that the check verified.
    unchecked : int
        Number of names that the check could not verify.
    """

    status: Literal["checked", "skipped"]
    reason: str
    problems: list[Problem]
    checked: int
    unchecked: int


def _closing_rule_line(skill: Skill) -> int:
    """Find the 1-based file line of the closing frontmatter rule.

    Parameters
    ----------
    skill : Skill
        The skill to inspect.

    Returns
    -------
    int
        Line number of the closing ``---`` line.
    """
    lines = skill.path.read_text(encoding="utf-8").splitlines()
    for number, text in enumerate(lines[1:], start=2):
        if text == "---":
            return number
    return 1


def python_blocks(skill: Skill) -> list[CodeBlock]:
    """Find the fenced Python blocks in the body of a skill.

    A block opens at a line that is ``` ```python ``` and closes at the next
    line that is ``` ``` ```. Trailing spaces are ignored.

    Parameters
    ----------
    skill : Skill
        The skill to scan.

    Returns
    -------
    list[CodeBlock]
        The blocks in file order.
    """
    offset = _closing_rule_line(skill)
    blocks: list[CodeBlock] = []
    open_line: int | None = None
    source: list[str] = []
    for number, text in enumerate(skill.body.splitlines(), start=1):
        stripped = text.strip()
        if open_line is None:
            if stripped == "```python":
                open_line = number
                source = []
        elif stripped == "```":
            blocks.append(
                CodeBlock(
                    index=len(blocks) + 1,
                    line=offset + open_line,
                    source="\n".join(source),
                )
            )
            open_line = None
        else:
            source.append(text)
    return blocks


def check_frontmatter_set(skills: Sequence[Skill]) -> list[Problem]:
    """Check that each skill name is unique in a set of skills.

    Parameters
    ----------
    skills : Sequence[Skill]
        The skills to check.

    Returns
    -------
    list[Problem]
        One ``unique`` problem for each repeated name.
    """
    counts = Counter(skill.name for skill in skills)
    return [
        Problem(name, "unique", f"the name '{name}' is used {count} times")
        for name, count in counts.items()
        if count > 1
    ]


def check_syntax(skill: Skill) -> list[Problem]:
    """Check that each Python block of a skill parses.

    Parameters
    ----------
    skill : Skill
        The skill to check.

    Returns
    -------
    list[Problem]
        One ``syntax`` problem for each block that does not parse.
    """
    problems: list[Problem] = []
    for block in python_blocks(skill):
        try:
            ast.parse(block.source)
        except SyntaxError as err:
            problems.append(
                Problem(
                    skill.name,
                    "syntax",
                    f"block {block.index} (line {block.line}): {err.msg}",
                )
            )
    return problems


@dataclass(frozen=True)
class _Instance:
    """An object made from a known class in a code block.

    Attributes
    ----------
    cls : type
        The class of the object.
    """

    cls: type


class _NameChecker:
    """Walk one parsed block and check the names that it uses.

    Parameters
    ----------
    skill_name : str
        Name of the skill. It is used in each problem.
    index : int
        Number of the block in the skill.
    roots : Sequence[str]
        First parts of the module names that the checker may import.
    """

    def __init__(self, skill_name: str, index: int, roots: Sequence[str]) -> None:
        self.skill_name = skill_name
        self.index = index
        self.roots = roots
        self.bindings: dict[str, object] = {}
        self.problems: list[Problem] = []
        self.checked = 0
        self.unchecked = 0

    def _problem(self, text: str) -> None:
        """Record one name problem for this block."""
        self.problems.append(Problem(self.skill_name, "name", f"block {self.index}: {text}"))

    def _in_roots(self, module_name: str) -> bool:
        """Tell if a module name starts with a root."""
        return module_name.split(".")[0] in self.roots

    def _import(self, module_name: str) -> ModuleType | None:
        """Import a module. Record a problem if the import fails."""
        try:
            return importlib.import_module(module_name)
        except Exception as err:  # noqa: BLE001 - any failure is a problem
            self._problem(f"cannot import {module_name} ({type(err).__name__})")
            return None

    def visit(self, node: ast.AST) -> None:
        """Visit a node and its children in source order."""
        if isinstance(node, ast.Import):
            self._visit_import(node)
        elif isinstance(node, ast.ImportFrom):
            self._visit_import_from(node)
        elif isinstance(node, ast.Assign):
            self.visit(node.value)
            self._bind_targets(node)
        elif isinstance(node, ast.Call) and self._is_instance_call(node):
            self._visit_instance_call(node)
        elif isinstance(node, ast.Attribute):
            self._visit_attribute(node)
        else:
            for child in ast.iter_child_nodes(node):
                self.visit(child)

    def _visit_import(self, node: ast.Import) -> None:
        """Handle ``import a.b`` and ``import a.b as c``."""
        for alias in node.names:
            if not self._in_roots(alias.name):
                continue
            module = self._import(alias.name)
            if module is None:
                continue
            if alias.asname:
                self.bindings[alias.asname] = module
            else:
                top = alias.name.split(".")[0]
                self.bindings[top] = importlib.import_module(top)

    def _visit_import_from(self, node: ast.ImportFrom) -> None:
        """Handle ``from a.b import X as Y``."""
        if node.level or not node.module or not self._in_roots(node.module):
            return
        module = self._import(node.module)
        if module is None:
            return
        for alias in node.names:
            if hasattr(module, alias.name):
                value = getattr(module, alias.name)
            else:
                try:
                    value = importlib.import_module(f"{node.module}.{alias.name}")
                except Exception:  # noqa: BLE001 - a missing name is a problem
                    self._problem(f"cannot import name {alias.name} from {node.module}")
                    continue
            bound_name = alias.asname or alias.name
            if inspect.ismodule(value) or inspect.isclass(value):
                self.bindings[bound_name] = value
            else:
                self.bindings.pop(bound_name, None)

    def _bind_targets(self, node: ast.Assign) -> None:
        """Update the bindings after an assignment.

        Only a plain name target drops a binding. A target such as
        ``v.a`` or ``v[0]`` changes the object, not the name, so ``v`` stays.
        """
        for target in node.targets:
            self._unbind(target)
        value = node.value
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(value, ast.Call)
        ):
            bound = self._resolve(value.func)
            if inspect.isclass(bound):
                self.bindings[node.targets[0].id] = _Instance(bound)

    def _unbind(self, target: ast.expr) -> None:
        """Drop the binding of each plain name in an assignment target."""
        if isinstance(target, ast.Name):
            self.bindings.pop(target.id, None)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._unbind(element)
        elif isinstance(target, ast.Starred):
            self._unbind(target.value)

    def _resolve(self, node: ast.expr) -> object | None:
        """Find the module or class that a name or attribute chain gives."""
        names: list[str] = []
        while isinstance(node, ast.Attribute):
            names.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        obj = self.bindings.get(node.id)
        for attr in reversed(names):
            if not (inspect.ismodule(obj) or inspect.isclass(obj)) or not hasattr(obj, attr):
                return None
            obj = getattr(obj, attr)
        return obj

    def _is_instance_call(self, node: ast.Call) -> bool:
        """Tell if a call has the form ``v.m(...)`` with ``v`` an instance."""
        func = node.func
        return (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and isinstance(self.bindings.get(func.value.id), _Instance)
        )

    def _visit_instance_call(self, node: ast.Call) -> None:
        """Check the method of a call on an instance. Keep the arguments."""
        func = node.func
        assert isinstance(func, ast.Attribute)
        assert isinstance(func.value, ast.Name)
        instance = self.bindings[func.value.id]
        assert isinstance(instance, _Instance)
        self.checked += 1
        if not hasattr(instance.cls, func.attr):
            self._problem(f"{instance.cls.__name__} has no method {func.attr}")
        for child in [*node.args, *node.keywords]:
            self.visit(child)

    def _visit_attribute(self, node: ast.Attribute) -> None:
        """Check one attribute chain, such as ``N.a.b``."""
        names: list[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            names.append(current.attr)
            current = current.value
        names.reverse()
        if not isinstance(current, ast.Name):
            self.visit(current)
            return
        bound = self.bindings.get(current.id)
        if isinstance(bound, _Instance):
            self.unchecked += 1
            return
        if not (inspect.ismodule(bound) or inspect.isclass(bound)):
            return
        obj: object = bound
        path = current.id
        for attr in names:
            path = f"{path}.{attr}"
            if not hasattr(obj, attr):
                self._problem(f"{path} does not exist (missing {attr})")
                return
            obj = getattr(obj, attr)
            self.checked += 1


def check_names(
    skill: Skill,
    roots: Sequence[str] = ("LoopStructural", "map2loop"),
    lookup: Callable[[str], str | None] | None = None,
) -> NameReport:
    """Check that the names in the Python blocks of a skill exist.

    The check imports only modules whose first part is in ``roots``. It runs
    only when the pin of the skill names a root and the installed version
    meets the pin. The bindings persist across the blocks of a skill, in file
    order, because the blocks are steps of one script. A block that does not
    parse is skipped.

    Parameters
    ----------
    skill : Skill
        The skill to check.
    roots : Sequence[str]
        Names of the packages that the check may import.
    lookup : Callable[[str], str | None] | None
        Version lookup that is passed to ``check_pin``.

    Returns
    -------
    NameReport
        The result of the check.
    """
    dist = Requirement(skill.requires).name
    if dist not in roots:
        return NameReport("skipped", "no pin on a checked package", [], 0, 0)
    pin = check_pin(skill.requires, lookup)
    if pin.status != "ok":
        return NameReport("skipped", pin.message, [], 0, 0)

    # One checker for the whole skill: the blocks are steps of one script.
    checker = _NameChecker(skill.name, 1, roots)
    for block in python_blocks(skill):
        try:
            tree = ast.parse(block.source)
        except SyntaxError:
            continue
        checker.index = block.index
        checker.visit(tree)
    return NameReport("checked", "", checker.problems, checker.checked, checker.unchecked)
