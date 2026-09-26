# 0003: Apache Superset is the dashboard layer

**Status:** Accepted (2026-09-25)

## Context
Tuva produces analytics marts, and users need to see them. The candidates were
Evidence (code-first, static output), Superset and Metabase.

## Decision
Use **Apache Superset**, connected to the Tuva marts through `duckdb-engine` locally and
in the demo, and through the native drivers for other warehouses.

## Consequences
- Superset is a familiar, enterprise-credible BI tool that analytics teams may already
  run, so Kindling dashboards can be imported into their instances.
- Dashboards are stored as code: exported Superset asset bundles (YAML) under
  `superset/`, imported at startup and diffable in PRs.
- Superset is heavier than a static site generator. The demo runs it slim: a single
  container, SQLite metadata DB, no Celery/Redis, 2 gunicorn workers and a read-only
  DuckDB file.
- DuckDB allows only one writer, so the demo treats the DuckDB file as read-only and
  replaces it atomically when a nightly build lands.
