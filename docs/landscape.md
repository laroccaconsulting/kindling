# Landscape

A first pass at the tools Kindling covers. The plan is to move this into
machine-readable `catalog/*.yaml` entries that generate this page. Statuses and licenses
should be re-verified when each entry is written.

**Role** is where the tool sits in the story: Generate → Store → Use → Analyze → Measure.

## Generate and acquire data

| Tool / dataset | Role | Notes |
|---|---|---|
| **Synthea** | Synthetic patients | Java. Exports FHIR R4 (transaction bundles), C-CDA, CSV, CPCDS claims and bulk NDJSON. Seedable. The Kindling default. |
| CMS DE-SynPUF | Synthetic Medicare claims | Old (2008–2010) but widely used; good for Tuva claims marts. |
| CMS synthetic claims / Blue Button 2.0 sandbox / BCDA sandbox | Synthetic claims via APIs | Real CMS API shapes (CARIN BB-like). |
| MIMIC-IV demo / MIMIC-IV on FHIR demo | De-identified ICU data | The demo subsets are open. The full dataset requires PhysioNet credentialing and a DUA, so it is never hosted by Kindling. |
| Eunomia (OHDSI) | Small OMOP datasets | Useful for the OMOP bridge. |

## Store and exchange (FHIR servers and terminology)

| Tool | Role | Notes |
|---|---|---|
| **HAPI FHIR JPA Server** | FHIR server | Java, the most widely deployed. Includes the `clinical-reasoning` module (successor to cqf-ruler) for `$evaluate-measure`, `$care-gaps` and PlanDefinition `$apply`. Golden-path candidate. |
| **Blaze** | FHIR server | Clojure, fast, with built-in CQL measure evaluation. Great for a `lite` profile and parity testing. |
| **Medplum** | FHIR server + platform | TypeScript. FHIR-native, with a provider app, bots and auth. It's both server and EHR. |
| Microsoft FHIR Server | FHIR server | .NET, open-source counterpart of Azure Health Data Services. |
| Aidbox | FHIR server | Not open source (free dev license). Mention only; don't depend on it. |
| Snowstorm | SNOMED CT terminology server | Needs SNOMED licensing for content. |
| tx.fhir.org / HAPI terminology | Terminology | Public tx server is for dev only. |
| VSAC (NLM) | Value sets for eCQMs | Free, but requires a UMLS license and API key. |
| HL7 FHIR Validator / Inferno | Validation / conformance testing | Inferno is the ONC test kit (US Core, SMART, Bulk). |

## Clinical use (EHRs, apps, auth, CDS)

| Tool | Role | Notes |
|---|---|---|
| **Medplum app** | EHR UI | FHIR-native, runs directly on the Medplum server. |
| OpenEMR | EHR | PHP/MySQL with its own DB and a FHIR API facade (ONC-certified). Data goes in via its own import paths (e.g. C-CDA), not by loading into a FHIR server. |
| OpenMRS (O3) / Bahmni | EHR | Java, own DB, FHIR2 module facade. Strong in global health. |
| GNU Health | HIS | Own DB, limited FHIR. |
| Keycloak (+ SMART extensions) | Auth | SMART App Launch scopes and launch context. |
| SMART App Launcher / sample apps | SMART on FHIR | Growth chart, cardiac risk and similar demo apps. |
| CDS Hooks sandbox | CDS | Test harness for hook services. |

## Analyze

| Tool | Role | Notes |
|---|---|---|
| **Tuva Project** | dbt analytics | Input layer (claims + clinical) → core → marts (CMS-HCC, quality measures, readmissions, chronic conditions, financial PMPM, ED classification, CCSR). Runs on DuckDB, Postgres, Snowflake, BigQuery, Databricks, Redshift and Fabric. |
| Tuva FHIR connectors | FHIR → Tuva input layer | Evaluate before building `kindling-sof` views. |
| **SQL on FHIR v2** | Flattening spec | ViewDefinitions turn FHIR resources into tables. There are several implementations. |
| Pathling | FHIR analytics on Spark | Supports SQL on FHIR, FHIRPath queries and terminology-aware functions. |
| Google FHIR Data Pipes | FHIR → Parquet pipelines | Beam-based, with SQL on FHIR views. |
| Microsoft FHIR-Converter | HL7v2 / C-CDA → FHIR | Liquid templates. |
| OHDSI stack (OMOP CDM, ATLAS, Achilles, DQD, HADES) | Observational research | For the OMOP bridge track. |
| **Apache Superset** | Dashboards | The Kindling dashboard layer (ADR 0003). Connects to DuckDB via `duckdb-engine`. |
| Open Integration Engine | Integration engine | Community fork after NextGen Connect (Mirth) went closed-source. |

## Measure and decide (CQL)

| Tool / content | Role | Notes |
|---|---|---|
| **cqframework `clinical_quality_language`** | Reference translator (CQL→ELM) + Java engine | The canonical implementation. |
| **cqframework `clinical-reasoning`** | Measure/PlanDefinition evaluation | Powers HAPI's operations; also usable embedded. |
| `cql-execution` + `cql-exec-fhir` | JS CQL engine | Used by CDS Connect services. |
| `fqm-execution` (MITRE) | JS FHIR measure calculator | Includes detailed per-patient "highlighting". |
| Firely CQL SDK | .NET CQL → C# compiler | .NET shops. |
| google/cql | Go CQL engine | Newer; worth tracking. |
| VS Code CQL extension / CQL language server | Authoring | Base of the Kindling dev container. |
| cqf-tooling | IG refresh and bundling | Packaging measure content. |
| **CMS eCQMs** (eCQI Resource Center, `ecqm-content-*` repos, MADiE) | Measure content | Annual update cycle; QI-Core-based. |
| AHRQ CDS Connect | CDS content | Openly licensed CQL artifacts. |
| WHO SMART Guidelines | Guideline content | Digital adaptation kits with CQL. |
| CDC opioid prescribing CDS | CDS content | CQL + PlanDefinitions. |
| Bonnie | Measure testing | Test case authoring for eCQMs. |
| NCQA HEDIS digital measures | Measure content | **Licensed**, not openly redistributable. Reference it but don't include it. |

## Specs to explain (not software, but part of the story)

FHIR R4/R5 · US Core · QI-Core · DEQM · Bulk Data Access · SMART App Launch · CDS Hooks ·
SQL on FHIR · CQL/ELM · CARIN Blue Button · Da Vinci (PDex, DTR, CRD, PAS) · USCDI ·
TEFCA · HTI rules.
