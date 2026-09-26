# Packages

Kindling's glue is published as small, independent Python packages (Python 3.11+,
Apache-2.0). Use them together through the `kindling` CLI, or pick out just the one you
need. None of them requires the rest of Kindling.

!!! note "Not on PyPI yet"
    Until the first release, install from a checkout: `uv sync` in the repository root,
    or `pip install ./packages/kindling-sof`.

## kindling-synthea

Downloads a pinned Synthea release to `~/.cache/kindling` and runs it with reproducible
settings. The `analytics` preset (default) skips clinical notes, provenance, imaging
metadata and supply deliveries, which the analytics pipeline doesn't use.

```python
from kindling_synthea import generate

result = generate(population=100, seed=42, out_dir="data/synthea", reference_date="2026-01-01")
result.bundles  # provider bundles first, then one per patient
```

## kindling-fhir-load

Posts transaction bundles to any FHIR R4 server: shared provider bundles first
(sequentially), then patient bundles in parallel. Retries transient errors and reports
OperationOutcome diagnostics for failures.

```python
from kindling_fhir_load import load_bundles

report = load_bundles(result.bundles, "http://localhost:8080/fhir", concurrency=4)
print(report.summary())  # 117/117 bundles, 170,000 resources in 290.1s (590 resources/s)
```

## kindling-bulk

A client for the [Bulk Data Access IG](https://hl7.org/fhir/uv/bulkdata/) async pattern:
kick-off, poll with `Retry-After`, download, delete.

```python
from kindling_bulk import bulk_export

export = bulk_export("http://localhost:8080/fhir", "data/bulk", types=["Patient", "Condition"])
export.by_type()  # {"Patient": [Path("data/bulk/Patient.001.ndjson")], ...}
```

## kindling-sof

A SQL on FHIR v2 engine with DuckDB and Parquet output. See
[SQL on FHIR](concepts/sql-on-fhir.md).

## kindling-health

The `kindling` command:

```text
kindling up [--profile core|analytics|quality|full]
kindling run [steps...] [--patients N] [--seed S] [--fhir-url URL]
kindling generate | load | export | flatten | tuva-assets | transform
kindling summary
kindling down [--volumes]
```

It also includes `kindling_health.tuva_assets.mirror()`, which mirrors Tuva's versioned
terminology and value sets from the public bucket so dbt can load seeds from local disk
(`tuva_seed_duckdb_storage_root`).
