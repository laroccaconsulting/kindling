# 0001: Analytics and quality teams are the primary persona

**Status:** Accepted (2026-09-25)

## Context
Kindling could serve several audiences: analytics/quality teams, interop engineers,
app developers and educators. Trying to serve all of them at once spreads the work thin.

## Decision
Health system and payer **analytics and quality measurement teams** come first. When
work competes for time, pick whatever gets these users from raw data to trustworthy
analytics and quality measure results fastest.

## Consequences
- Phases 1–2 (zero to dashboard, CQL and quality measures) come before the
  clinical/app profile.
- Guides assume SQL/dbt fluency, not deep FHIR knowledge. FHIR gets explained as
  "the source format" rather than as the destination.
- EHR, SMART and CDS Hooks work (Phase 3) stays in the plan but can slip.
