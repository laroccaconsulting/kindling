# Architecture Decision Records

Short records of decisions that shape Kindling, and why we made them. New ADRs copy
the structure of an existing one (Context / Decision / Consequences) and take the next
number. An accepted ADR is never edited to reverse it; a new ADR supersedes it.

| # | Decision | Status |
|---|---|---|
| [0001](0001-primary-persona.md) | Analytics and quality teams are the primary persona | Accepted |
| [0002](0002-hapi-golden-path.md) | HAPI FHIR is the golden-path FHIR server | Accepted |
| [0003](0003-superset-dashboards.md) | Apache Superset is the dashboard layer | Accepted |
| [0004](0004-low-cost-aws-hosting.md) | Host the reference implementation on AWS for $10–20/month | Accepted |
| [0005](0005-governance.md) | Kindling lives under the LaRocca Consulting organization | Accepted |
| [0006](0006-sql-on-fhir-to-tuva.md) | FHIR reaches Tuva through SQL on FHIR views and a dbt connector | Accepted |
