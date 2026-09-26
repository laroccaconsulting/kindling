"""Run ViewDefinitions over FHIR NDJSON and write the results to DuckDB or Parquet."""

from __future__ import annotations

import gzip
import json
import time
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from importlib import resources as importlib_resources
from pathlib import Path
from typing import Any

import pyarrow as pa

from .view import View

# FHIR type → Arrow type. Temporal types stay strings: FHIR dates can be partial
# ("2020", "2020-06"), and the warehouse layer (dbt) owns casting.
_ARROW_TYPES: dict[str, pa.DataType] = {
    "boolean": pa.bool_(),
    "integer": pa.int64(),
    "positiveInt": pa.int64(),
    "unsignedInt": pa.int64(),
    "integer64": pa.int64(),
    "decimal": pa.float64(),
}


def arrow_type(fhir_type: str | None, collection: bool = False) -> pa.DataType:
    t = _ARROW_TYPES.get(fhir_type or "", pa.string())
    return pa.list_(t) if collection else t


def _to_arrow_value(v: Any, t: pa.DataType) -> Any:
    if v is None:
        return None
    if isinstance(v, list):
        return [_to_arrow_value(x, t.value_type) for x in v]
    if pa.types.is_string(t):
        if isinstance(v, (dict, list)):
            return json.dumps(v, default=str)
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)
    if pa.types.is_floating(t):
        return float(v) if not isinstance(v, bool) else None
    if pa.types.is_integer(t):
        return int(v) if not isinstance(v, bool) else None
    if pa.types.is_boolean(t):
        return v if isinstance(v, bool) else None
    return v


def bundled_views(name: str = "us_core") -> list[View]:
    """Load a set of ViewDefinitions shipped with kindling-sof (currently ``us_core``)."""
    root = importlib_resources.files("kindling_sof") / "views" / name
    views = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if entry.name.endswith(".json"):
            views.append(View(json.loads(entry.read_text())))
    if not views:
        raise FileNotFoundError(f"No bundled views named {name!r}")
    return views


def load_views(path: str | Path) -> list[View]:
    """Load ViewDefinitions from a JSON file or a directory of JSON files."""
    p = Path(path)
    files = sorted(p.glob("*.json")) if p.is_dir() else [p]
    return [View.from_file(f) for f in files]


def _resource_type_hint(path: Path) -> str | None:
    """``Patient.001.ndjson`` / ``Patient_1.ndjson`` / ``Patient.ndjson.gz`` → ``Patient``."""
    stem = path.name.split(".")[0].split("_")[0].split("-")[0]
    return stem if stem[:1].isupper() and stem.isalpha() else None


def iter_ndjson(paths: Iterable[Path]) -> Iterator[dict[str, Any]]:
    for p in paths:
        opener = gzip.open if p.suffix == ".gz" else open
        with opener(p, "rt", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line, parse_float=Decimal)


def ndjson_files(source: str | Path | Iterable[str | Path]) -> list[Path]:
    if isinstance(source, (str, Path)):
        p = Path(source)
        if p.is_dir():
            return sorted(x for x in p.iterdir() if x.name.endswith((".ndjson", ".ndjson.gz", ".jsonl")))
        return [p]
    return [Path(x) for x in source]


@dataclass
class ViewResult:
    name: str
    rows: int = 0
    seconds: float = 0.0


@dataclass
class RunReport:
    views: list[ViewResult] = field(default_factory=list)
    resources: int = 0
    seconds: float = 0.0

    def summary(self) -> str:
        rows = sum(v.rows for v in self.views)
        return (
            f"{len(self.views)} views, {rows:,} rows from {self.resources:,} resources in {self.seconds:.1f}s"
        )


class _TableWriter:
    """Accumulates rows for one view and flushes Arrow batches to a sink."""

    def __init__(self, view: View, sink: _Sink, batch_size: int):
        self.view = view
        self.sink = sink
        self.batch_size = batch_size
        self.schema = pa.schema([(c.name, arrow_type(c.type, c.collection)) for c in view.columns])
        self.buffer: dict[str, list[Any]] = {c.name: [] for c in view.columns}
        self.count = 0
        self.pending = 0

    def add(self, row: dict[str, Any]) -> None:
        for f in self.schema:
            self.buffer[f.name].append(_to_arrow_value(row.get(f.name), f.type))
        self.pending += 1
        self.count += 1
        if self.pending >= self.batch_size:
            self.flush()

    def flush(self, final: bool = False) -> None:
        if self.pending or (final and self.count == 0):
            table = pa.table(
                {f.name: pa.array(self.buffer[f.name], type=f.type) for f in self.schema}, schema=self.schema
            )
            self.sink.write(self.view.name or self.view.resource.lower(), table)
            self.buffer = {f.name: [] for f in self.schema}
            self.pending = 0


class _Sink:
    def write(self, name: str, table: pa.Table) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class DuckDBSink(_Sink):
    def __init__(self, database: str | Path | Any, schema: str = "fhir"):
        import duckdb

        self.own = not hasattr(database, "execute")
        con: Any = duckdb.connect(str(database)) if self.own else database
        self.con = con
        self.schema = schema
        con.execute(f'create schema if not exists "{schema}"')
        self.created: set[str] = set()

    def write(self, name: str, table: pa.Table) -> None:
        target = f'"{self.schema}"."{name}"'
        self.con.register("_kindling_batch", table)
        if name not in self.created:
            self.con.execute(f"create or replace table {target} as select * from _kindling_batch")
            self.created.add(name)
        else:
            self.con.execute(f"insert into {target} select * from _kindling_batch")
        self.con.unregister("_kindling_batch")

    def close(self) -> None:
        if self.own:
            self.con.close()


class ParquetSink(_Sink):
    def __init__(self, out_dir: str | Path):
        import pyarrow.parquet as pq

        self.pq = pq
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.writers: dict[str, Any] = {}

    def write(self, name: str, table: pa.Table) -> None:
        w = self.writers.get(name)
        if w is None:
            w = self.writers[name] = self.pq.ParquetWriter(self.out_dir / f"{name}.parquet", table.schema)
        w.write_table(table)

    def close(self) -> None:
        for w in self.writers.values():
            w.close()


def run_views(
    views: list[View],
    source: str | Path | Iterable[str | Path],
    *,
    duckdb: str | Path | Any | None = None,
    schema: str = "fhir",
    parquet_dir: str | Path | None = None,
    batch_size: int = 50_000,
) -> RunReport:
    """Evaluate ``views`` over NDJSON ``source`` (a directory, file, or list of files).

    Each resource file is read once; every view for that resource type is applied to it.
    Results go to DuckDB tables ``{schema}.{view.name}`` and/or ``{view.name}.parquet``.
    """
    if duckdb is None and parquet_dir is None:
        raise ValueError("Provide duckdb= and/or parquet_dir=")
    sinks: list[_Sink] = []
    if duckdb is not None:
        sinks.append(DuckDBSink(duckdb, schema))
    if parquet_dir is not None:
        sinks.append(ParquetSink(parquet_dir))

    class _Tee(_Sink):
        def write(self, name: str, table: pa.Table) -> None:
            for s in sinks:
                s.write(name, table)

    tee = _Tee()
    by_type: dict[str, list[View]] = defaultdict(list)
    for v in views:
        by_type[v.resource].append(v)
    files = ndjson_files(source)
    files_by_type: dict[str | None, list[Path]] = defaultdict(list)
    for f in files:
        files_by_type[_resource_type_hint(f)].append(f)

    report = RunReport()
    start = time.monotonic()
    try:
        for rtype, rviews in by_type.items():
            t0 = time.monotonic()
            writers = [_TableWriter(v, tee, batch_size) for v in rviews]
            inputs = files_by_type.get(rtype, []) + files_by_type.get(None, [])
            for resource in iter_ndjson(inputs):
                if resource.get("resourceType") != rtype:
                    continue
                report.resources += 1
                for w in writers:
                    for row in w.view.rows([resource]):
                        w.add(row)
            elapsed = time.monotonic() - t0
            for w in writers:
                w.flush(final=True)
                report.views.append(ViewResult(w.view.name or rtype, w.count, elapsed))
    finally:
        for s in sinks:
            s.close()
    report.seconds = time.monotonic() - start
    return report
