# 0006: FHIR reaches Tuva through SQL on FHIR views and a dbt connector

**Status:** Accepted (2026-09-25)

## Context
Tuva's analytics start from its *input layer*: claims and clinical tables with a fixed
contract. Kindling's data starts as FHIR. We need a repeatable path between the two that
enterprises can reuse with their own FHIR servers.

Options considered:

1. **Tuva's FHIR connector (FHIR Inferno).** Flattens FHIR with custom `.ini` configs.
   It has configurations for a few vendors, none for Synthea/US Core, and the format is
   specific to that tool.
2. **Tuva's `fhir_preprocessing` package.** Goes the other way (Tuva → FHIR-shaped tables).
3. **A Python script that maps FHIR JSON straight to input-layer tables.** Fast to write,
   but it mixes flattening with business logic and can't be reused.
4. **SQL on FHIR v2 ViewDefinitions → DuckDB, then a dbt connector project.**

## Decision
Option 4, in two clearly separated steps:

- **Flatten (`kindling-sof`).** Standard SQL on FHIR v2 ViewDefinitions turn Bulk Data
  NDJSON into generic tables (`fhir.patient`, `fhir.explanation_of_benefit_item`, …).
  The views are plain JSON, portable to any SQL on FHIR engine (Pathling, Aidbox, etc.),
  and describe US Core resources, not Tuva.
- **Map (`dbt/`).** A dbt project in the shape of a Tuva connector turns those tables into
  the Tuva input layer and runs Tuva Core and the Quality Measures package. All the
  Synthea-specific judgment calls live here, in SQL, next to comments explaining them.

`kindling-sof` includes its own FHIRPath engine and passes all 144 cases of the shared SQL
on FHIR conformance suite.

## Consequences
- The flattening layer is standards-based and reusable beyond Kindling; that's why
  it's published as its own package.
- Real FHIR sources (payer APIs, EHR bulk exports) can reuse the same views and swap the
  dbt connector's Synthea assumptions for their own.
- The Synthea → Tuva gaps (SNOMED diagnoses, RxNorm drugs, missing bill types) are
  handled in named, tested dbt models, documented in
  [From Synthea FHIR to Tuva](../concepts/synthea-to-tuva.md).
- The Python engine is fast enough for demo-scale data (about 6,500 resources/s on one
  core). Pushing view evaluation down into DuckDB SQL is a later optimization, and the
  conformance suite makes it safe.
