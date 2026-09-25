# SQL on FHIR

FHIR resources are nested JSON: a Patient has a list of names, each with a list of given
names, plus extensions for race and ethnicity. Analytics tools want flat tables.
[SQL on FHIR v2](https://sql-on-fhir.org/) is the HL7 standard for bridging the two. A
**ViewDefinition** is a small JSON document that says which resource to read and which
FHIRPath expressions become which columns:

```json
{
  "resourceType": "https://sql-on-fhir.org/ig/StructureDefinition/ViewDefinition",
  "name": "patient",
  "resource": "Patient",
  "select": [{
    "column": [
      {"name": "id", "path": "getResourceKey()", "type": "id"},
      {"name": "family_name", "path": "name.where(use = 'official').family.first()"},
      {"name": "birth_date", "path": "birthDate", "type": "date"}
    ]
  }]
}
```

Because the view is data, not code, the same definition runs on any conforming engine:
Pathling on Spark, Aidbox inside Postgres, or `kindling-sof` in Python.

## kindling-sof

`kindling-sof` is a small, dependency-light implementation for Python and DuckDB:

- A FHIRPath engine that compiles expressions to Python closures.
- Full ViewDefinition semantics: `forEach`, `forEachOrNull`, `repeat`, `unionAll`,
  constants, `%rowIndex`, `getResourceKey()` / `getReferenceKey()`, `lowBoundary()` /
  `highBoundary()`.
- Passes **all 144 cases** of the shared conformance suite (run on every commit).
- Streams NDJSON (e.g. a Bulk Data export) into DuckDB tables or Parquet files.

```bash
pip install kindling-sof
kindling-sof run ./bulk-export --duckdb fhir.duckdb          # bundled US Core views
kindling-sof run ./bulk-export --views ./my-views --parquet out/
```

```python
from kindling_sof import View
from kindling_sof.runner import bundled_views, run_views

run_views(bundled_views("us_core"), "bulk-export/", duckdb="fhir.duckdb")
```

## The bundled US Core views

`kindling_sof/views/us_core/` holds 19 views covering Patient, Encounter, Condition,
Procedure, Observation (and components), DiagnosticReport results, MedicationRequest,
Medication, Immunization, AllergyIntolerance, Practitioner(Role), Organization, Location,
Coverage, and ExplanationOfBenefit (headers, lines and diagnoses). They describe the FHIR
data itself, not any one analytics model. Tuva-specific logic lives downstream in dbt;
see [From Synthea FHIR to Tuva](synthea-to-tuva.md).
