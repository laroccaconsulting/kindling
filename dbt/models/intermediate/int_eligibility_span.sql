-- Enrollment spans. Synthea only records coverage inside each claim, so enrollment is
-- inferred: a member is enrolled with a payer for every calendar year in which that
-- payer paid one of their claims, clipped to birth and death dates.
with claim_years as (
    select distinct
        person_id
      , payer
      , payer_type
      , plan
      , extract(year from claim_start_date) as enrollment_year
    from {{ ref('int_claim') }}
    where claim_start_date is not null
)

, spans as (
    select
        cy.person_id
      , cy.payer
      , cy.payer_type
      , cy.plan
      , greatest(make_date(cast(cy.enrollment_year as integer), 1, 1), coalesce({{ fhir_date('p.birth_date') }}, date '1900-01-01')) as enrollment_start_date
      , least(make_date(cast(cy.enrollment_year as integer), 12, 31), coalesce({{ fhir_date('p.deceased_datetime') }}, date '2999-12-31')) as enrollment_end_date
    from claim_years as cy
    inner join {{ source('fhir', 'patient') }} as p
        on cy.person_id = p.id
)

select *
from spans
where enrollment_start_date <= enrollment_end_date
