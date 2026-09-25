# From Synthea FHIR to Tuva

Synthea produces realistic *clinical* histories and, alongside them, claims
(`Claim` and `ExplanationOfBenefit`). Tuva expects *billing-grade* claims: ICD-10-CM
diagnoses, HCPCS/CPT procedures, NDC drugs, bill types, revenue codes and enrollment
spans. The two don't line up out of the box. This page lists every gap Kindling found and
what the dbt connector (`dbt/models`) does about each one.

!!! warning "Synthetic claims are for learning, not benchmarking"
    Several of these fixes infer data that a real payer file would contain. The results are
    good for learning how Tuva works and for exercising pipelines. They aren't
    actuarially meaningful.

## The gaps

| Tuva expects | Synthea gives | Kindling's fix | Where |
|---|---|---|---|
| Claim diagnoses in **ICD-10-CM** | `EOB.diagnosis` → a `Condition` coded in **SNOMED CT** | Resolve the Condition, then map SNOMED → ICD-10-CM with the NLM map in Tuva's terminology (first unconditional target) | `int_snomed_to_icd10`, `int_claim_diagnosis` |
| Pharmacy claims keyed by **NDC** | **RxNorm** on each pharmacy line | Pick one representative NDC per RxNorm concept from Tuva's CodeRx package table (active first, then lowest NDC) | `int_rxnorm_to_ndc` |
| **Days supply** on fills | Not recorded | Assume 30 days (`kindling_default_days_supply`) | `pharmacy_claim` |
| **Place of service** for the visit | A POS code that follows the *billing facility* (most professional lines say "inpatient") | Derive setting from `Encounter.class` and type: IMP→21, EMER→23, urgent care→20, HH→12, VR→02, otherwise 11 | `stg_encounter` |
| **Bill type** and **revenue codes** on institutional claims | None | Derive from the setting: inpatient 111/0120, ED 131/0450, home health 321/0550, else 131/0510 | `stg_encounter`, `medical_claim` |
| **HCPCS/CPT** on service lines | SNOMED, LOINC, CVX or CDT (CPT is licensed; Synthea avoids it) | Keep `hcpcs_code` null unless the line really is CPT/HCPCS | `medical_claim` |
| Claim **service dates** | `billablePeriod` spans a whole coverage year | Use min/max of the line `servicedPeriod`s | `int_claim` |
| **Enrollment** (eligibility spans) | Coverage only exists *inside* each claim (contained `Coverage`) | Enroll a member with a payer for every calendar year in which that payer paid a claim, clipped to birth/death | `int_eligibility_span` |
| Payer **type** | Payer names ("Medicare", "Humana", "NO_INSURANCE") | Medicare / Dual Eligible → medicare, Medicaid → medicaid, others → commercial; drop `NO_INSURANCE` claims | `int_claim` |
| Human-readable **names** | "Eliseo499 Nader710" (digits keep names unique) | Strip digits | `clean_name` macro |
| Lab **orders** (panels) | `DiagnosticReport.result` → Observations | Join results to their panel for `source_order_code` | `lab_result` |
| Vitals as **single values** | Blood pressure is one Observation with components | One `observation` row per component, `panel_id` → the panel | `observation` |
| **Appointments** | Not generated | Empty table with the right columns | `appointment` |

## What works well

- **Clinical data** maps cleanly. Tuva's normalized layer and condition grouper handle
  SNOMED CT natively, and LOINC, CVX and RxNorm pass straight through.
- **Cost and utilization.** Line-level adjudication (`line_prvdr_pmt_amt`,
  `line_alowd_chrg_amt`, …) follows the Blue Button variable names, so paid and allowed
  amounts come through intact.
- **Quality measures** that rely on diagnoses, medications and encounters (for example
  CQM438, statin therapy for cardiovascular disease) produce real denominators and
  numerators.

## What still doesn't work (yet)

- Measures that rely on **G-codes or CPT II** (e.g. CQM130, documentation of current
  medications, and NQF0420, pain assessment) have denominators but zero numerators:
  Synthea never bills those codes. These are good candidates for the CQL cross-check,
  where the same logic reads clinical FHIR data directly.
- **DRGs** aren't assigned, so inpatient DRG-based analytics are empty.
- **Provider attribution** is off (Synthea NPIs are fictional `9999…` numbers that match
  no national provider file).

If you hit another gap, open an issue with the Tuva table and column. Each fix should
be a small, named dbt model with a comment explaining the assumption.
