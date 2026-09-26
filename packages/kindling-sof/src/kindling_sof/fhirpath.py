"""A compact FHIRPath engine covering the subset SQL on FHIR ViewDefinitions need.

Expressions are parsed once into an AST and compiled into Python closures, so
evaluating the same path over millions of resources costs one tree-walk each.

Values are plain JSON-decoded Python objects: ``dict`` for complex types, ``str``,
``bool``, ``int`` and ``Decimal`` for primitives. A few ``str`` subclasses carry the
FHIR type where it matters (``ofType(dateTime)`` versus a plain ``date``).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

Collection = list[Any]


class FHIRPathError(Exception):
    """Raised for syntax errors or invalid evaluation (e.g. non-singleton operands)."""


class DateStr(str):
    """A string known to be a FHIR ``date``."""


class DateTimeStr(str):
    """A string known to be a FHIR ``dateTime`` or ``instant``."""


class TimeStr(str):
    """A string known to be a FHIR ``time``."""


# --------------------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------------------


@dataclass
class Env:
    resource: Any = None
    constants: dict[str, Any] = field(default_factory=dict)
    this: Any = None
    index: int | None = None
    row_index: int = 0

    def child(self, this: Any, index: int) -> Env:
        return Env(self.resource, self.constants, this, index, self.row_index)


Evaluator = Callable[[Collection, Env], Collection]

# --------------------------------------------------------------------------------------
# Lexer
# --------------------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+|//[^\n]*|/\*.*?\*/)
  | (?P<datetime>@T?\d[\d\-:T.+Z]*)
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<string>'(?:[^'\\]|\\.)*')
  | (?P<delimited>`(?:[^`\\]|\\.)*`)
  | (?P<ext>%(?:[A-Za-z_][A-Za-z0-9_]*|`(?:[^`\\]|\\.)*`|'(?:[^'\\]|\\.)*'))
  | (?P<special>\$(?:this|index|total))
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op><=|>=|!=|!~|[.\[\](),+\-*/|&=~<>{}])
    """,
    re.VERBOSE | re.DOTALL,
)

_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "f": "\f", "'": "'", '"': '"', "`": "`", "/": "/", "\\": "\\"}


def _unescape(s: str) -> str:
    def repl(m: re.Match[str]) -> str:
        c = m.group(1)
        if c.startswith("u"):
            return chr(int(c[1:], 16))
        return _ESCAPES.get(c, c)

    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", repl, s)


@dataclass
class Token:
    kind: str
    value: str
    pos: int


def tokenize(src: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(src):
        m = _TOKEN_RE.match(src, pos)
        if not m:
            raise FHIRPathError(f"Unexpected character {src[pos]!r} at {pos} in {src!r}")
        kind = m.lastgroup or ""
        text = m.group()
        pos = m.end()
        if kind == "ws":
            continue
        tokens.append(Token(kind, text, m.start()))
    tokens.append(Token("eof", "", len(src)))
    return tokens


# --------------------------------------------------------------------------------------
# AST
# --------------------------------------------------------------------------------------


@dataclass
class Node:
    pass


@dataclass
class Literal(Node):
    value: Any  # None means the empty collection {}


@dataclass
class Member(Node):
    name: str


@dataclass
class Invoke(Node):
    """``target.name`` or ``target.fn(args)``; ``target`` is None for a leading term."""

    target: Node | None
    name: str
    args: list[Node] | None  # None: member access; list: function call


@dataclass
class Index(Node):
    target: Node
    index: Node


@dataclass
class Unary(Node):
    op: str
    operand: Node


@dataclass
class Binary(Node):
    op: str
    left: Node
    right: Node


@dataclass
class TypeOp(Node):
    op: str  # is | as
    operand: Node
    type_name: str


@dataclass
class External(Node):
    name: str


@dataclass
class Special(Node):
    name: str  # $this | $index | $total


# Binding powers, low → high (FHIRPath spec §Operator precedence).
_BINARY = {
    "implies": 1,
    "or": 2,
    "xor": 2,
    "and": 3,
    "in": 4,
    "contains": 4,
    "=": 5,
    "~": 5,
    "!=": 5,
    "!~": 5,
    "<": 6,
    ">": 6,
    "<=": 6,
    ">=": 6,
    "|": 7,
    "is": 8,
    "as": 8,
    "+": 9,
    "-": 9,
    "&": 9,
    "*": 10,
    "/": 10,
    "div": 10,
    "mod": 10,
}
_UNARY_BP = 11
_KEYWORD_OPS = {"and", "or", "xor", "implies", "in", "contains", "is", "as", "div", "mod"}


class Parser:
    def __init__(self, src: str):
        self.src = src
        self.tokens = tokenize(src)
        self.i = 0

    def peek(self) -> Token:
        return self.tokens[self.i]

    def next(self) -> Token:
        t = self.tokens[self.i]
        self.i += 1
        return t

    def expect(self, value: str) -> Token:
        t = self.next()
        if t.value != value:
            raise FHIRPathError(f"Expected {value!r} at {t.pos} in {self.src!r}, got {t.value!r}")
        return t

    def parse(self) -> Node:
        node = self.expression(0)
        if self.peek().kind != "eof":
            t = self.peek()
            raise FHIRPathError(f"Unexpected {t.value!r} at {t.pos} in {self.src!r}")
        return node

    def _binary_op(self) -> str | None:
        t = self.peek()
        if t.kind == "op" and t.value in _BINARY:
            return t.value
        if t.kind == "ident" and t.value in _KEYWORD_OPS:
            return t.value
        return None

    def expression(self, min_bp: int) -> Node:
        left = self.prefix()
        while True:
            op = self._binary_op()
            if op is None:
                break
            bp = _BINARY[op]
            if bp <= min_bp:
                break
            self.next()
            if op in ("is", "as"):
                left = TypeOp(op, left, self.type_specifier())
            else:
                left = Binary(op, left, self.expression(bp))
        return left

    def type_specifier(self) -> str:
        name = self.identifier()
        while self.peek().value == ".":
            self.next()
            name = self.identifier()  # namespace (FHIR./System.) is dropped
        return name

    def identifier(self) -> str:
        t = self.next()
        if t.kind == "ident":
            return t.value
        if t.kind == "delimited":
            return _unescape(t.value[1:-1])
        raise FHIRPathError(f"Expected identifier at {t.pos} in {self.src!r}, got {t.value!r}")

    def prefix(self) -> Node:
        t = self.peek()
        if t.kind == "op" and t.value in ("+", "-"):
            self.next()
            return Unary(t.value, self.expression(_UNARY_BP))
        return self.postfix(self.term())

    def postfix(self, node: Node) -> Node:
        while True:
            t = self.peek()
            if t.value == "." and t.kind == "op":
                self.next()
                node = self.invocation(node)
            elif t.value == "[" and t.kind == "op":
                self.next()
                idx = self.expression(0)
                self.expect("]")
                node = Index(node, idx)
            else:
                return node

    def invocation(self, target: Node | None) -> Node:
        name = self.identifier()
        if self.peek().value == "(":
            self.next()
            args: list[Node] = []
            if self.peek().value != ")":
                args.append(self.expression(0))
                while self.peek().value == ",":
                    self.next()
                    args.append(self.expression(0))
            self.expect(")")
            return Invoke(target, name, args)
        return Invoke(target, name, None)

    def term(self) -> Node:
        t = self.peek()
        if t.kind == "number":
            self.next()
            return Literal(Decimal(t.value) if "." in t.value else int(t.value))
        if t.kind == "string":
            self.next()
            return Literal(_unescape(t.value[1:-1]))
        if t.kind == "datetime":
            self.next()
            v = t.value[1:]
            if v.startswith("T"):
                return Literal(TimeStr(v[1:]))
            return Literal(DateTimeStr(v) if "T" in v else DateStr(v))
        if t.kind == "ext":
            self.next()
            name = t.value[1:]
            if name[0] in "`'":
                name = _unescape(name[1:-1])
            return External(name)
        if t.kind == "special":
            self.next()
            return Special(t.value)
        if t.kind == "op" and t.value == "(":
            self.next()
            node = self.expression(0)
            self.expect(")")
            return node
        if t.kind == "op" and t.value == "{":
            self.next()
            self.expect("}")
            return Literal(None)
        if t.kind == "ident" and t.value in ("true", "false"):
            self.next()
            return Literal(t.value == "true")
        if t.kind in ("ident", "delimited"):
            return self.invocation(None)
        raise FHIRPathError(f"Unexpected {t.value or 'end of expression'!r} at {t.pos} in {self.src!r}")


def parse(src: str) -> Node:
    if not isinstance(src, str) or not src.strip():
        raise FHIRPathError(f"FHIRPath expression must be a non-empty string, got {src!r}")
    return Parser(src).parse()


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

_STRING_TYPES = {
    "string",
    "code",
    "id",
    "uri",
    "url",
    "canonical",
    "oid",
    "uuid",
    "markdown",
    "base64Binary",
    "xhtml",
}
_INTEGER_TYPES = {"integer", "positiveInt", "unsignedInt", "integer64"}
_DATE_TYPES = {"date", "dateTime", "instant", "time"}

_DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
_TIME_RE = re.compile(r"^\d{2}(:\d{2}(:\d{2}(\.\d+)?)?)?$")
_DATETIME_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2}(T\d{2}(:\d{2}(:\d{2}(\.\d+)?)?)?(Z|[+-]\d{2}:\d{2})?)?)?)?$")


def _flatten_into(out: Collection, v: Any) -> None:
    if v is None:
        return
    if isinstance(v, list):
        out.extend(x for x in v if x is not None)
    else:
        out.append(v)


def _choice_values(item: dict[str, Any], name: str) -> Collection:
    """Values for a polymorphic element referenced without its type suffix (``value``)."""
    out: Collection = []
    n = len(name)
    for key, v in item.items():
        if len(key) > n and key.startswith(name) and key[n].isupper():
            _flatten_into(out, _tag(key[n:], v))
    return out


def _tag(type_suffix: str, v: Any) -> Any:
    t = type_suffix[0].lower() + type_suffix[1:]
    if isinstance(v, str):
        if t in ("dateTime", "instant"):
            return DateTimeStr(v)
        if t == "date":
            return DateStr(v)
        if t == "time":
            return TimeStr(v)
    return v


def _navigate(focus: Collection, name: str) -> Collection:
    out: Collection = []
    for item in focus:
        if not isinstance(item, dict):
            continue
        v = item.get(name)
        if v is not None:
            _flatten_into(out, v)
        elif item.get("resourceType") == name:
            out.append(item)
        else:
            out.extend(_choice_values(item, name))
    return out


def _matches_type(v: Any, type_name: str) -> bool:
    if type_name in _STRING_TYPES:
        return isinstance(v, str) and not isinstance(v, (DateStr, DateTimeStr, TimeStr))
    if type_name in _INTEGER_TYPES:
        return isinstance(v, int) and not isinstance(v, bool)
    if type_name == "decimal":
        return isinstance(v, (Decimal, float)) or (isinstance(v, int) and not isinstance(v, bool))
    if type_name == "boolean":
        return isinstance(v, bool)
    if type_name in ("dateTime", "instant"):
        return isinstance(v, DateTimeStr)
    if type_name == "date":
        return isinstance(v, DateStr)
    if type_name == "time":
        return isinstance(v, TimeStr)
    if isinstance(v, dict):
        rt = v.get("resourceType")
        return rt == type_name if rt is not None else True
    return False


def _of_type_member(focus: Collection, name: str, type_name: str) -> Collection:
    """``name.ofType(T)``: prefer the typed choice element ``nameT``."""
    suffix = type_name[0].upper() + type_name[1:]
    out: Collection = []
    for item in focus:
        if not isinstance(item, dict):
            continue
        v = item.get(name + suffix)
        if v is not None:
            _flatten_into(out, _tag(suffix, v))
            continue
        plain: Collection = []
        _flatten_into(plain, item.get(name))
        out.extend(x for x in plain if _matches_type(x, type_name))
    return out


def to_bool(coll: Collection, what: str = "expression") -> bool | None:
    """Singleton evaluation of a collection in a boolean context."""
    if not coll:
        return None
    if len(coll) > 1:
        raise FHIRPathError(f"{what} returned multiple items where a single boolean was expected")
    v = coll[0]
    if isinstance(v, bool):
        return v
    return True


def _singleton(coll: Collection, op: str) -> Any:
    if len(coll) > 1:
        raise FHIRPathError(f"Operator {op!r} requires single-item operands, got {len(coll)} items")
    return coll[0] if coll else None


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _num(v: Any) -> Decimal | int:
    if isinstance(v, float):
        return Decimal(str(v))
    return v  # type: ignore[no-any-return]


def _temporal_parts(s: str) -> tuple[list[str], str | None]:
    """Split an ISO date/time string into precision components and a timezone."""
    tz = None
    m = re.search(r"(Z|[+-]\d{2}:\d{2})$", s)
    if m and "T" in s:
        tz = m.group(1)
        s = s[: m.start()]
    parts = re.split(r"[-T:]", s)
    if parts and "." in parts[-1]:
        sec, frac = parts[-1].split(".", 1)
        parts[-1] = sec
        parts.append(frac)
    return parts, tz


def _looks_temporal(v: Any) -> bool:
    return isinstance(v, (DateStr, DateTimeStr, TimeStr)) or (
        isinstance(v, str) and bool(_DATETIME_RE.match(v)) and len(v) >= 4 and v[:4].isdigit() and "-" in v
    )


def _parse_instant(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _compare_temporal(a: str, b: str) -> int | None:
    """Three-way comparison honouring precision; None when precision makes it undecidable."""
    if "T" in a and "T" in b:
        pa, ta = _temporal_parts(a)
        pb, tb = _temporal_parts(b)
        if len(pa) >= 6 and len(pb) >= 6 and ta and tb:
            da, db = _parse_instant(a), _parse_instant(b)
            if da and db:
                return (da > db) - (da < db)
    pa, _ = _temporal_parts(a)
    pb, _ = _temporal_parts(b)
    for x, y in zip(pa, pb, strict=False):
        if x != y:
            if len(x) != len(y):  # fractional seconds of different length
                x, y = x.ljust(max(len(x), len(y)), "0"), y.ljust(max(len(x), len(y)), "0")
            return (x > y) - (x < y)
    if len(pa) != len(pb):
        return None
    return 0


def _equals(a: Any, b: Any) -> bool | None:
    if _is_number(a) and _is_number(b):
        return bool(_num(a) == _num(b))
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b if isinstance(a, bool) and isinstance(b, bool) else False
    if isinstance(a, str) and isinstance(b, str):
        if _looks_temporal(a) and _looks_temporal(b):
            c = _compare_temporal(a, b)
            return None if c is None else c == 0
        return a == b
    return bool(a == b)


def _equivalent(a: Any, b: Any) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return " ".join(a.lower().split()) == " ".join(b.lower().split())
    if _is_number(a) and _is_number(b):
        return bool(_num(a) == _num(b))
    return bool(a == b)


def _compare(a: Any, b: Any, op: str) -> int | None:
    if _is_number(a) and _is_number(b):
        x, y = _num(a), _num(b)
        return (x > y) - (x < y)
    if isinstance(a, str) and isinstance(b, str):
        if _looks_temporal(a) and _looks_temporal(b):
            return _compare_temporal(a, b)
        return (a > b) - (a < b)
    raise FHIRPathError(f"Cannot compare {type(a).__name__} and {type(b).__name__} with {op!r}")


def _decimal_places(d: Decimal) -> int:
    exp = d.as_tuple().exponent
    return -exp if isinstance(exp, int) and exp < 0 else 0


def _boundary(v: Any, low: bool) -> Any:
    if _is_number(v):
        d = _num(v)
        d = Decimal(d) if isinstance(d, int) else d
        half = Decimal(5).scaleb(-(_decimal_places(d) + 1))
        return d - half if low else d + half
    if isinstance(v, TimeStr) or (isinstance(v, str) and _TIME_RE.match(v) and ":" in v):
        parts = v.split(":")
        while len(parts) < 3:
            parts.append("00" if low else "59")
        if "." not in parts[2]:
            parts[2] += ".000" if low else ".999"
        return TimeStr(":".join(parts))
    if isinstance(v, str) and _DATETIME_RE.match(v):
        is_datetime = isinstance(v, DateTimeStr) or "T" in v
        parts, tz = _temporal_parts(v)
        year = parts[0]
        month = parts[1] if len(parts) > 1 else ("01" if low else "12")
        if len(parts) > 2:
            day = parts[2]
        elif low:
            day = "01"
        else:
            import calendar

            day = f"{calendar.monthrange(int(year), int(month))[1]:02d}"
        if not is_datetime:
            return DateStr(f"{year}-{month}-{day}")
        hh = parts[3] if len(parts) > 3 else ("00" if low else "23")
        mm = parts[4] if len(parts) > 4 else ("00" if low else "59")
        ss = parts[5] if len(parts) > 5 else ("00" if low else "59")
        frac = parts[6] if len(parts) > 6 else ("000" if low else "999")
        if tz is None:
            tz = "+14:00" if low else "-12:00"
        return DateTimeStr(f"{year}-{month}-{day}T{hh}:{mm}:{ss}.{frac}{tz}")
    return None


def _reference_key(ref: Any, type_name: str | None) -> str | None:
    if not isinstance(ref, dict):
        return None
    r = ref.get("reference")
    if not isinstance(r, str) or not r:
        return None
    if r.startswith("urn:uuid:") or r.startswith("urn:oid:"):
        return r.split(":", 2)[2] if type_name is None else None
    if r.startswith("#") or "?" in r:
        return None
    parts = r.split("/_history/")[0].rstrip("/").split("/")
    if len(parts) < 2:
        return None
    rtype, rid = parts[-2], parts[-1]
    if type_name is not None and rtype != type_name:
        return None
    return rid


def _to_string(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


# --------------------------------------------------------------------------------------
# Compiler
# --------------------------------------------------------------------------------------

BUILTIN_EXTERNALS = {"rowIndex", "resource", "rootResource", "context", "ucum", "sct", "loinc"}


class Compiler:
    def __init__(self, constants: set[str] | None = None):
        self.constants = constants

    def compile(self, node: Node) -> Evaluator:
        method = getattr(self, "c_" + type(node).__name__)
        return method(node)  # type: ignore[no-any-return]

    # -- terms ------------------------------------------------------------------------

    def c_Literal(self, node: Literal) -> Evaluator:
        value: Collection = [] if node.value is None else [node.value]
        return lambda focus, env: value

    def c_External(self, node: External) -> Evaluator:
        name = node.name
        if name == "rowIndex":
            return lambda focus, env: [env.row_index]
        if name in ("resource", "rootResource", "context"):
            return lambda focus, env: [env.resource] if env.resource is not None else []
        if name == "ucum":
            return lambda focus, env: ["http://unitsofmeasure.org"]
        if name == "sct":
            return lambda focus, env: ["http://snomed.info/sct"]
        if name == "loinc":
            return lambda focus, env: ["http://loinc.org"]
        if self.constants is not None and name not in self.constants:
            raise FHIRPathError(f"Undefined constant %{name}")

        def ext(focus: Collection, env: Env) -> Collection:
            if name not in env.constants:
                raise FHIRPathError(f"Undefined constant %{name}")
            v = env.constants[name]
            return list(v) if isinstance(v, list) else [v]

        return ext

    def c_Special(self, node: Special) -> Evaluator:
        if node.name == "$this":
            return lambda focus, env: [env.this] if env.this is not None else list(focus)
        if node.name == "$index":
            return lambda focus, env: [env.index] if env.index is not None else []
        raise FHIRPathError(f"{node.name} is not supported")

    def c_Member(self, node: Member) -> Evaluator:
        name = node.name
        return lambda focus, env: _navigate(focus, name)

    def c_Invoke(self, node: Invoke) -> Evaluator:
        target = self.compile(node.target) if node.target is not None else None
        if node.args is None:
            name = node.name

            if target is None:
                return lambda focus, env: _navigate(focus, name)
            return lambda focus, env: _navigate(target(focus, env), name)

        # Special-case ``member.ofType(T)`` to resolve polymorphic ``member[x]`` elements.
        if (
            node.name == "ofType"
            and isinstance(node.target, Invoke)
            and node.target.args is None
            and len(node.args) == 1
        ):
            member = node.target
            type_name = self._type_arg(node.args[0])
            parent = self.compile(member.target) if member.target is not None else None
            mname = member.name
            if parent is None:
                return lambda focus, env: _of_type_member(focus, mname, type_name)
            return lambda focus, env: _of_type_member(parent(focus, env), mname, type_name)

        fn = self.function(node.name, node.args)
        if target is None:
            return fn
        return lambda focus, env: fn(target(focus, env), env)

    def c_Index(self, node: Index) -> Evaluator:
        target = self.compile(node.target)
        index = self.compile(node.index)

        def ev(focus: Collection, env: Env) -> Collection:
            coll = target(focus, env)
            idx = _singleton(index(focus, env), "[]")
            if idx is None:
                return []
            if not isinstance(idx, int) or isinstance(idx, bool):
                raise FHIRPathError("Indexer must be an integer")
            return [coll[idx]] if 0 <= idx < len(coll) else []

        return ev

    def c_Unary(self, node: Unary) -> Evaluator:
        operand = self.compile(node.operand)
        if node.op == "+":
            return operand

        def neg(focus: Collection, env: Env) -> Collection:
            v = _singleton(operand(focus, env), "-")
            if v is None:
                return []
            if not _is_number(v):
                raise FHIRPathError("Unary minus requires a number")
            return [-_num(v)]

        return neg

    def c_TypeOp(self, node: TypeOp) -> Evaluator:
        operand = self.compile(node.operand)
        t = node.type_name
        if node.op == "is":

            def is_(focus: Collection, env: Env) -> Collection:
                v = _singleton(operand(focus, env), "is")
                return [] if v is None else [_matches_type(v, t)]

            return is_

        def as_(focus: Collection, env: Env) -> Collection:
            v = _singleton(operand(focus, env), "as")
            return [v] if v is not None and _matches_type(v, t) else []

        return as_

    def c_Binary(self, node: Binary) -> Evaluator:
        left = self.compile(node.left)
        right = self.compile(node.right)
        op = node.op

        if op in ("and", "or", "xor", "implies"):
            return self._logic(op, left, right)
        if op == "|":

            def union(focus: Collection, env: Env) -> Collection:
                out: Collection = []
                for v in left(focus, env) + right(focus, env):
                    if not any(_equals(v, x) is True for x in out):
                        out.append(v)
                return out

            return union
        if op in ("=", "!="):

            def eq(focus: Collection, env: Env) -> Collection:
                a, b = left(focus, env), right(focus, env)
                if not a or not b:
                    return []
                if len(a) != len(b):
                    res: bool | None = False
                else:
                    res = True
                    for x, y in zip(a, b, strict=True):
                        r = _equals(x, y)
                        if r is None:
                            return []
                        if not r:
                            res = False
                            break
                return [res if op == "=" else not res]

            return eq
        if op in ("~", "!~"):

            def equiv(focus: Collection, env: Env) -> Collection:
                a, b = left(focus, env), right(focus, env)
                if not a and not b:
                    res = True
                elif len(a) != len(b):
                    res = False
                else:
                    res = all(_equivalent(x, y) for x, y in zip(a, b, strict=True))
                return [res if op == "~" else not res]

            return equiv
        if op in ("<", ">", "<=", ">="):

            def cmp(focus: Collection, env: Env) -> Collection:
                a = _singleton(left(focus, env), op)
                b = _singleton(right(focus, env), op)
                if a is None or b is None:
                    return []
                c = _compare(a, b, op)
                if c is None:
                    return []
                return [{"<": c < 0, ">": c > 0, "<=": c <= 0, ">=": c >= 0}[op]]

            return cmp
        if op in ("in", "contains"):

            def member(focus: Collection, env: Env) -> Collection:
                a, b = left(focus, env), right(focus, env)
                item, coll = (a, b) if op == "in" else (b, a)
                if not item:
                    return []
                v = _singleton(item, op)
                return [any(_equals(v, x) is True for x in coll)]

            return member
        if op == "&":

            def concat(focus: Collection, env: Env) -> Collection:
                a = _singleton(left(focus, env), "&")
                b = _singleton(right(focus, env), "&")
                return [(_to_string(a) if a is not None else "") + (_to_string(b) if b is not None else "")]

            return concat

        def arith(focus: Collection, env: Env) -> Collection:
            a = _singleton(left(focus, env), op)
            b = _singleton(right(focus, env), op)
            if a is None or b is None:
                return []
            if op == "+" and isinstance(a, str) and isinstance(b, str):
                return [a + b]
            if not (_is_number(a) and _is_number(b)):
                raise FHIRPathError(f"Operator {op!r} requires numbers")
            x, y = _num(a), _num(b)
            if op == "+":
                return [x + y]
            if op == "-":
                return [x - y]
            if op == "*":
                return [x * y]
            if y == 0:
                return []
            if op == "/":
                return [Decimal(x) / Decimal(y)]
            if op == "div":
                return [int(Decimal(x) / Decimal(y))]
            return [x % y]  # mod

        return arith

    @staticmethod
    def _logic(op: str, left: Evaluator, right: Evaluator) -> Evaluator:
        def ev(focus: Collection, env: Env) -> Collection:
            a = to_bool(left(focus, env), op)
            if op == "and" and a is False:
                return [False]
            if op == "or" and a is True:
                return [True]
            if op == "implies" and a is False:
                return [True]
            b = to_bool(right(focus, env), op)
            if op == "and":
                if b is False:
                    return [False]
                return [True] if a is True and b is True else []
            if op == "or":
                if b is True:
                    return [True]
                return [False] if a is False and b is False else []
            if op == "xor":
                return [] if a is None or b is None else [a != b]
            # implies with a True or empty
            if a is True:
                return [] if b is None else [b]
            return [True] if b is True else []

        return ev

    # -- functions --------------------------------------------------------------------

    @staticmethod
    def _type_arg(node: Node) -> str:
        if isinstance(node, Invoke) and node.args is None:
            name = node.name
            if node.target is not None and isinstance(node.target, Invoke):
                return name  # FHIR.string / System.String
            return name
        raise FHIRPathError("Expected a type name")

    def _arity(self, name: str, args: list[Node], lo: int, hi: int) -> None:
        if not lo <= len(args) <= hi:
            raise FHIRPathError(f"{name}() takes {lo}..{hi} arguments, got {len(args)}")

    def function(self, name: str, args: list[Node]) -> Evaluator:
        fn = getattr(self, "f_" + name, None)
        if fn is None:
            raise FHIRPathError(f"Unsupported FHIRPath function {name}()")
        return fn(args)  # type: ignore[no-any-return]

    def _lambda_arg(self, args: list[Node], name: str) -> Evaluator:
        self._arity(name, args, 1, 1)
        return self.compile(args[0])

    def _value_arg(self, args: list[Node], i: int) -> Evaluator:
        return self.compile(args[i])

    def f_where(self, args: list[Node]) -> Evaluator:
        crit = self._lambda_arg(args, "where")

        def ev(focus: Collection, env: Env) -> Collection:
            out = []
            for i, item in enumerate(focus):
                if to_bool(crit([item], env.child(item, i)), "where()") is True:
                    out.append(item)
            return out

        return ev

    def f_select(self, args: list[Node]) -> Evaluator:
        proj = self._lambda_arg(args, "select")

        def ev(focus: Collection, env: Env) -> Collection:
            out: Collection = []
            for i, item in enumerate(focus):
                out.extend(proj([item], env.child(item, i)))
            return out

        return ev

    def f_repeat(self, args: list[Node]) -> Evaluator:
        proj = self._lambda_arg(args, "repeat")

        def ev(focus: Collection, env: Env) -> Collection:
            out: Collection = []
            queue = list(focus)
            while queue:
                item = queue.pop(0)
                for child in proj([item], env.child(item, 0)):
                    if not any(child is x for x in out):
                        out.append(child)
                        queue.append(child)
            return out

        return ev

    def f_exists(self, args: list[Node]) -> Evaluator:
        self._arity("exists", args, 0, 1)
        if args:
            where = self.f_where(args)
            return lambda focus, env: [bool(where(focus, env))]
        return lambda focus, env: [bool(focus)]

    def f_all(self, args: list[Node]) -> Evaluator:
        crit = self._lambda_arg(args, "all")

        def ev(focus: Collection, env: Env) -> Collection:
            return [all(to_bool(crit([x], env.child(x, i))) is True for i, x in enumerate(focus))]

        return ev

    def f_empty(self, args: list[Node]) -> Evaluator:
        self._arity("empty", args, 0, 0)
        return lambda focus, env: [not focus]

    def f_not(self, args: list[Node]) -> Evaluator:
        self._arity("not", args, 0, 0)

        def ev(focus: Collection, env: Env) -> Collection:
            b = to_bool(focus, "not()")
            return [] if b is None else [not b]

        return ev

    def f_hasValue(self, args: list[Node]) -> Evaluator:
        return lambda focus, env: [len(focus) == 1 and not isinstance(focus[0], dict)]

    def f_first(self, args: list[Node]) -> Evaluator:
        self._arity("first", args, 0, 0)
        return lambda focus, env: focus[:1]

    def f_last(self, args: list[Node]) -> Evaluator:
        self._arity("last", args, 0, 0)
        return lambda focus, env: focus[-1:]

    def f_tail(self, args: list[Node]) -> Evaluator:
        return lambda focus, env: focus[1:]

    def f_single(self, args: list[Node]) -> Evaluator:
        def ev(focus: Collection, env: Env) -> Collection:
            if len(focus) > 1:
                raise FHIRPathError("single() called on a collection with multiple items")
            return focus

        return ev

    def f_skip(self, args: list[Node]) -> Evaluator:
        n = self._value_arg(args, 0)
        return lambda focus, env: focus[int(_singleton(n(focus, env), "skip") or 0) :]

    def f_take(self, args: list[Node]) -> Evaluator:
        n = self._value_arg(args, 0)
        return lambda focus, env: focus[: int(_singleton(n(focus, env), "take") or 0)]

    def f_count(self, args: list[Node]) -> Evaluator:
        return lambda focus, env: [len(focus)]

    def f_distinct(self, args: list[Node]) -> Evaluator:
        def ev(focus: Collection, env: Env) -> Collection:
            out: Collection = []
            for v in focus:
                if not any(_equals(v, x) is True for x in out):
                    out.append(v)
            return out

        return ev

    def f_join(self, args: list[Node]) -> Evaluator:
        self._arity("join", args, 0, 1)
        sep = self._value_arg(args, 0) if args else None

        def ev(focus: Collection, env: Env) -> Collection:
            if not focus:
                return []
            s = _singleton(sep(focus, env), "join") if sep else ""
            return [(s or "").join(_to_string(v) for v in focus)]

        return ev

    def f_ofType(self, args: list[Node]) -> Evaluator:
        self._arity("ofType", args, 1, 1)
        t = self._type_arg(args[0])
        return lambda focus, env: [v for v in focus if _matches_type(v, t)]

    def f_extension(self, args: list[Node]) -> Evaluator:
        url = self._value_arg(args, 0)

        def ev(focus: Collection, env: Env) -> Collection:
            u = _singleton(url(focus, env), "extension")
            out = []
            for item in focus:
                if isinstance(item, dict):
                    for ext in item.get("extension") or []:
                        if isinstance(ext, dict) and ext.get("url") == u:
                            out.append(ext)
            return out

        return ev

    def f_getResourceKey(self, args: list[Node]) -> Evaluator:
        self._arity("getResourceKey", args, 0, 0)
        return lambda focus, env: [
            item["id"] for item in focus if isinstance(item, dict) and item.get("id") is not None
        ]

    def f_getReferenceKey(self, args: list[Node]) -> Evaluator:
        self._arity("getReferenceKey", args, 0, 1)
        t = self._type_arg(args[0]) if args else None

        def ev(focus: Collection, env: Env) -> Collection:
            out = []
            for item in focus:
                k = _reference_key(item, t)
                if k is not None:
                    out.append(k)
            return out

        return ev

    def f_lowBoundary(self, args: list[Node]) -> Evaluator:
        return lambda focus, env: [b for v in focus if (b := _boundary(v, True)) is not None]

    def f_highBoundary(self, args: list[Node]) -> Evaluator:
        return lambda focus, env: [b for v in focus if (b := _boundary(v, False)) is not None]

    def f_iif(self, args: list[Node]) -> Evaluator:
        self._arity("iif", args, 2, 3)
        cond, then = self.compile(args[0]), self.compile(args[1])
        other = self.compile(args[2]) if len(args) == 3 else None

        def ev(focus: Collection, env: Env) -> Collection:
            this = focus[0] if len(focus) == 1 else env.this
            if to_bool(cond(focus, env.child(this, 0)), "iif()") is True:
                return then(focus, env)
            return other(focus, env) if other else []

        return ev

    # string helpers ------------------------------------------------------------------

    def _string_fn(self, args: list[Node], impl: Callable[..., Any]) -> Evaluator:
        compiled = [self.compile(a) for a in args]

        def ev(focus: Collection, env: Env) -> Collection:
            v = _singleton(focus, "string function")
            if v is None:
                return []
            vals = [_singleton(c(focus, env), "argument") for c in compiled]
            if any(x is None for x in vals):
                return []
            r = impl(_to_string(v), *vals)
            return [] if r is None else [r]

        return ev

    def f_toString(self, args: list[Node]) -> Evaluator:
        return self._string_fn(args, lambda s: s)

    def f_startsWith(self, args: list[Node]) -> Evaluator:
        return self._string_fn(args, lambda s, p: s.startswith(p))

    def f_endsWith(self, args: list[Node]) -> Evaluator:
        return self._string_fn(args, lambda s, p: s.endswith(p))

    def f_contains(self, args: list[Node]) -> Evaluator:
        return self._string_fn(args, lambda s, p: p in s)

    def f_matches(self, args: list[Node]) -> Evaluator:
        return self._string_fn(args, lambda s, p: re.search(p, s) is not None)

    def f_replace(self, args: list[Node]) -> Evaluator:
        return self._string_fn(args, lambda s, a, b: s.replace(a, b))

    def f_lower(self, args: list[Node]) -> Evaluator:
        return self._string_fn(args, lambda s: s.lower())

    def f_upper(self, args: list[Node]) -> Evaluator:
        return self._string_fn(args, lambda s: s.upper())

    def f_trim(self, args: list[Node]) -> Evaluator:
        return self._string_fn(args, lambda s: s.strip())

    def f_length(self, args: list[Node]) -> Evaluator:
        return self._string_fn(args, lambda s: len(s))

    def f_substring(self, args: list[Node]) -> Evaluator:
        def impl(s: str, start: int, length: int | None = None) -> str | None:
            if start < 0 or start >= len(s):
                return None
            return s[start:] if length is None else s[start : start + length]

        return self._string_fn(args, impl)

    def f_split(self, args: list[Node]) -> Evaluator:
        sep = self._value_arg(args, 0)

        def ev(focus: Collection, env: Env) -> Collection:
            v = _singleton(focus, "split")
            s = _singleton(sep(focus, env), "split")
            return [] if v is None or s is None else _to_string(v).split(s)

        return ev

    def f_toInteger(self, args: list[Node]) -> Evaluator:
        def ev(focus: Collection, env: Env) -> Collection:
            v = _singleton(focus, "toInteger")
            if isinstance(v, bool):
                return [int(v)]
            if isinstance(v, int):
                return [v]
            if isinstance(v, str) and re.fullmatch(r"[+-]?\d+", v):
                return [int(v)]
            return []

        return ev

    def f_toDecimal(self, args: list[Node]) -> Evaluator:
        def ev(focus: Collection, env: Env) -> Collection:
            v = _singleton(focus, "toDecimal")
            if _is_number(v):
                return [Decimal(_num(v))]
            if isinstance(v, str) and re.fullmatch(r"[+-]?\d+(\.\d+)?", v):
                return [Decimal(v)]
            return []

        return ev


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------


class Expression:
    """A compiled FHIRPath expression."""

    def __init__(self, src: str, constants: set[str] | None = None):
        self.src = src
        self.ast = parse(src)
        self._ev = Compiler(constants).compile(self.ast)

    def __call__(self, focus: Any, env: Env | None = None) -> Collection:
        coll = focus if isinstance(focus, list) else ([] if focus is None else [focus])
        if env is None:
            env = Env(resource=coll[0] if coll else None)
        return self._ev(coll, env)

    def __repr__(self) -> str:
        return f"Expression({self.src!r})"


def evaluate(resource: Any, expression: str, constants: dict[str, Any] | None = None) -> Collection:
    """Evaluate ``expression`` against ``resource``. Convenience for ad-hoc use and tests."""
    expr = Expression(expression, set(constants) if constants is not None else None)
    return expr(resource, Env(resource=resource, constants=constants or {}))
