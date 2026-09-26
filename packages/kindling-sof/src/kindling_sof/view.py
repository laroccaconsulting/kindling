"""SQL on FHIR v2 ViewDefinition evaluation.

A :class:`View` is validated and compiled once, then turns FHIR resources into rows::

    view = View.from_dict(view_definition_json)
    for row in view.rows(resources):
        ...

Semantics follow the SQL on FHIR specification and match the reference
implementation (FHIR/sql-on-fhir.js) on the shared conformance test suite.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from .fhirpath import (
    BUILTIN_EXTERNALS,
    DateStr,
    DateTimeStr,
    Env,
    Expression,
    FHIRPathError,
    TimeStr,
    to_bool,
)

Row = dict[str, Any]

_COLUMN_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class ViewDefinitionError(ValueError):
    """The ViewDefinition is invalid, or evaluating it hit an error the spec calls fatal."""


@dataclass
class Column:
    name: str
    path: Expression
    type: str | None = None
    collection: bool = False
    description: str | None = None


@dataclass
class Selection:
    columns: list[Column] = field(default_factory=list)
    select: list[Selection] = field(default_factory=list)
    union_all: list[Selection] = field(default_factory=list)
    for_each: Expression | None = None
    for_each_or_null: Expression | None = None
    repeat: list[Expression] = field(default_factory=list)

    def column_names(self) -> list[str]:
        names = [c.name for c in self.columns]
        for s in self.select:
            names.extend(s.column_names())
        if self.union_all:
            names.extend(self.union_all[0].column_names())
        return names

    def column_defs(self) -> list[Column]:
        cols = list(self.columns)
        for s in self.select:
            cols.extend(s.column_defs())
        if self.union_all:
            cols.extend(self.union_all[0].column_defs())
        return cols


_CONSTANT_VALUE_KEYS = {
    "valueBase64Binary",
    "valueBoolean",
    "valueCanonical",
    "valueCode",
    "valueDate",
    "valueDateTime",
    "valueDecimal",
    "valueId",
    "valueInstant",
    "valueInteger",
    "valueInteger64",
    "valueOid",
    "valuePositiveInt",
    "valueString",
    "valueTime",
    "valueUnsignedInt",
    "valueUri",
    "valueUrl",
    "valueUuid",
}


def _constant_value(c: dict[str, Any]) -> Any:
    keys = [k for k in c if k.startswith("value")]
    if len(keys) != 1 or keys[0] not in _CONSTANT_VALUE_KEYS:
        raise ViewDefinitionError(f"Constant {c.get('name')!r} must have exactly one value[x]")
    key = keys[0]
    v = c[key]
    if key == "valueDecimal":
        return Decimal(str(v))
    if key == "valueDate":
        return DateStr(v)
    if key in ("valueDateTime", "valueInstant"):
        return DateTimeStr(v)
    if key == "valueTime":
        return TimeStr(v)
    return v


class View:
    """A validated, compiled ViewDefinition."""

    def __init__(self, definition: dict[str, Any]):
        if not isinstance(definition, dict):
            raise ViewDefinitionError("ViewDefinition must be a JSON object")
        self.definition = definition
        self.name: str | None = definition.get("name")
        resource = definition.get("resource")
        if not isinstance(resource, str) or not resource:
            raise ViewDefinitionError("ViewDefinition.resource is required")
        self.resource: str = resource

        self.constants: dict[str, Any] = {}
        for c in definition.get("constant") or []:
            name = c.get("name")
            if not isinstance(name, str) or not name:
                raise ViewDefinitionError("Constant name is required")
            self.constants[name] = _constant_value(c)
        self._known = set(self.constants) | BUILTIN_EXTERNALS

        select = definition.get("select")
        if not isinstance(select, list) or not select:
            raise ViewDefinitionError("ViewDefinition.select must be a non-empty array")
        self.root = Selection(select=[self._selection(s) for s in select])

        self.where: list[Expression] = []
        for w in definition.get("where") or []:
            self.where.append(self._expr(w.get("path") if isinstance(w, dict) else None, "where.path"))

        names = self.root.column_names()
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ViewDefinitionError(f"Duplicate column names: {dupes}")
        self.columns: list[Column] = self.root.column_defs()

    @classmethod
    def from_dict(cls, definition: dict[str, Any]) -> View:
        return cls(definition)

    @classmethod
    def from_file(cls, path: str | Path) -> View:
        return cls(json.loads(Path(path).read_text()))

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    # -- compilation ------------------------------------------------------------------

    def _expr(self, src: Any, where: str) -> Expression:
        if not isinstance(src, str):
            raise ViewDefinitionError(f"{where} must be a FHIRPath string, got {src!r}")
        try:
            return Expression(src, self._known)
        except FHIRPathError as e:
            raise ViewDefinitionError(f"Invalid FHIRPath in {where}: {e}") from e

    def _selection(self, s: Any) -> Selection:
        if not isinstance(s, dict):
            raise ViewDefinitionError("select entries must be objects")
        sel = Selection()
        for c in s.get("column") or []:
            name = c.get("name")
            if not isinstance(name, str) or not _COLUMN_NAME_RE.match(name):
                raise ViewDefinitionError(f"Invalid column name {name!r}")
            sel.columns.append(
                Column(
                    name=name,
                    path=self._expr(c.get("path"), f"column {name}"),
                    type=c.get("type"),
                    collection=bool(c.get("collection", False)),
                    description=c.get("description"),
                )
            )
        if "forEach" in s:
            sel.for_each = self._expr(s["forEach"], "forEach")
        if "forEachOrNull" in s:
            sel.for_each_or_null = self._expr(s["forEachOrNull"], "forEachOrNull")
        if "repeat" in s:
            if not isinstance(s["repeat"], list) or not s["repeat"]:
                raise ViewDefinitionError("repeat must be a non-empty array of FHIRPath strings")
            sel.repeat = [self._expr(p, "repeat") for p in s["repeat"]]
        if sum(x is not None and x != [] for x in (sel.for_each, sel.for_each_or_null, sel.repeat)) > 1:
            raise ViewDefinitionError("Only one of forEach, forEachOrNull and repeat is allowed")
        sel.select = [self._selection(x) for x in s.get("select") or []]
        sel.union_all = [self._selection(x) for x in s.get("unionAll") or []]
        if sel.union_all:
            first = sel.union_all[0].column_names()
            for branch in sel.union_all[1:]:
                if branch.column_names() != first:
                    raise ViewDefinitionError(
                        f"unionAll branches must have identical columns: {first} vs {branch.column_names()}"
                    )
        return sel

    # -- evaluation -------------------------------------------------------------------

    def rows(self, resources: Iterable[dict[str, Any]]) -> Iterator[Row]:
        """Yield rows for every matching resource, in column order."""
        names = self.column_names
        for resource in resources:
            if not isinstance(resource, dict) or resource.get("resourceType") != self.resource:
                continue
            env = Env(resource=resource, constants=self.constants)
            if not self._included(resource, env):
                continue
            for row in self._process(self.root, resource, env):
                yield {n: row.get(n) for n in names}

    def _included(self, resource: dict[str, Any], env: Env) -> bool:
        for w in self.where:
            try:
                res = w([resource], env)
            except FHIRPathError as e:
                raise ViewDefinitionError(f"Error evaluating where {w.src!r}: {e}") from e
            if res and not isinstance(res[0], bool):
                raise ViewDefinitionError(f"where path {w.src!r} must evaluate to a boolean")
            if to_bool(res[:1], "where") is not True:
                return False
        return True

    def _process(self, sel: Selection, node: Any, env: Env) -> list[Row]:
        if sel.for_each is not None or sel.for_each_or_null is not None:
            expr = sel.for_each if sel.for_each is not None else sel.for_each_or_null
            assert expr is not None
            items = self._eval(expr, node, env)
            if not items and sel.for_each_or_null is not None:
                items = [{}]
            return self._iterate(sel, items, env)
        if sel.repeat:
            return self._iterate(sel, self._traverse(sel.repeat, node, env), env)
        return self._combine(sel, node, env)

    def _iterate(self, sel: Selection, items: list[Any], env: Env) -> list[Row]:
        rows: list[Row] = []
        for i, item in enumerate(items):
            child = Env(env.resource, env.constants, None, None, i)
            rows.extend(self._combine(sel, item, child))
        return rows

    def _traverse(self, paths: list[Expression], node: Any, env: Env) -> list[Any]:
        out: list[Any] = []

        def walk(n: Any) -> None:
            for p in paths:
                for child in self._eval(p, n, env):
                    if isinstance(child, dict):
                        out.append(child)
                        walk(child)

        walk(node)
        return out

    def _eval(self, expr: Expression, node: Any, env: Env) -> list[Any]:
        try:
            return expr([node] if node is not None else [], env)
        except FHIRPathError as e:
            raise ViewDefinitionError(f"Error evaluating {expr.src!r}: {e}") from e

    def _combine(self, sel: Selection, node: Any, env: Env) -> list[Row]:
        parts: list[list[Row]] = []
        if sel.columns:
            record: Row = {}
            for col in sel.columns:
                vals = self._eval(col.path, node, env)
                if col.collection:
                    record[col.name] = [_output(v) for v in vals]
                elif len(vals) <= 1:
                    record[col.name] = _output(vals[0]) if vals else None
                else:
                    raise ViewDefinitionError(
                        f"Column {col.name!r} ({col.path.src}) returned {len(vals)} values; "
                        "set collection: true or narrow the path"
                    )
            parts.append([record])
        for s in sel.select:
            parts.append(self._process(s, node, env))
        if sel.union_all:
            union: list[Row] = []
            for s in sel.union_all:
                union.extend(self._process(s, node, env))
            parts.append(union)
        rows: list[Row] = [{}]
        for part in parts:
            rows = [{**r, **p} for r in rows for p in part]
            if not rows:
                break
        return rows


def _output(v: Any) -> Any:
    """Convert internal values to plain JSON-compatible output values."""
    if isinstance(v, (DateStr, DateTimeStr, TimeStr)):
        return str(v)
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() and v.as_tuple().exponent == 0 else float(v)
    return v
