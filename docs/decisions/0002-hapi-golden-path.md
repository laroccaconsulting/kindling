# 0002: HAPI FHIR is the golden-path FHIR server

**Status:** Accepted (2026-09-25)

## Context
The golden path needs a single default FHIR server. The candidates were HAPI FHIR JPA
Server, Blaze and Medplum.

## Decision
Use **HAPI FHIR JPA Server** (Postgres backend) with its **clinical-reasoning** module
enabled for `$evaluate-measure`, `$care-gaps` and `Library/$evaluate`.

## Consequences
- It is the most widely deployed open-source FHIR server, so what users learn on it
  transfers to what enterprises already run (including Smile CDR, which is built on HAPI).
- CQL measure evaluation is built in, with no separate engine service needed.
- JVM memory use is significant. The hosted demo tunes the heap down and keeps the
  population small (see ADR 0004).
- Blaze stays in the `quality` profile as a second engine for parity testing, and
  Medplum in the `clinical` profile. Neither is on the golden path.
- Verify arm64 image support for each pinned HAPI version, since the hosted demo targets
  Graviton (ADR 0004).
