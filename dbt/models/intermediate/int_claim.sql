-- Claim headers from ExplanationOfBenefit, with the service dates taken from the
-- lines (Synthea's billablePeriod spans a whole coverage year) and the care setting
-- taken from the linked encounter.
with eob as (
    select * from {{ source('fhir', 'explanation_of_benefit') }}
)

, line_dates as (
    select
        eob_id
      , min({{ fhir_date('service_start') }}) as claim_start_date
      , max(coalesce({{ fhir_date('service_end') }}, {{ fhir_date('service_start') }})) as claim_end_date
      , max(encounter_id) as line_encounter_id
    from {{ source('fhir', 'explanation_of_benefit_item') }}
    group by eob_id
)

select
    eob.id as claim_id
  , eob.patient_id as person_id
  , eob.claim_type
  , eob.payer_name as payer
  , case
        when eob.payer_name in ('Medicare', 'Dual Eligible') then 'medicare'
        when eob.payer_name = 'Medicaid' then 'medicaid'
        else 'commercial'
    end as payer_type
  , coalesce(eob.coverage_type, eob.payer_name) as plan
  , coalesce(line_dates.claim_start_date, {{ fhir_date('eob.created') }}) as claim_start_date
  , coalesce(line_dates.claim_end_date, {{ fhir_date('eob.created') }}) as claim_end_date
  , {{ fhir_date('eob.created') }} as paid_date
  , coalesce(eob.encounter_id, line_dates.line_encounter_id) as encounter_id
  , enc.encounter_type
  , enc.class_code
  , enc.place_of_service_code
  , enc.bill_type_code
  , enc.revenue_center_code
  , {{ fhir_date('enc.period_start') }} as encounter_start_date
  , {{ fhir_date('enc.period_end') }} as encounter_end_date
  , enc.discharge_disposition_code
  , eob.provider_id
  , prac.npi as rendering_npi
  , eob.facility_id
  , eob.total_submitted
  , eob.payment_amount
from eob
left join line_dates
    on eob.id = line_dates.eob_id
left join {{ ref('stg_encounter') }} as enc
    on coalesce(eob.encounter_id, line_dates.line_encounter_id) = enc.id
left join {{ source('fhir', 'practitioner') }} as prac
    on eob.provider_id = prac.id
-- Uninsured encounters are billed to "NO_INSURANCE": they're not payer claims.
where eob.payer_name is not null
  and eob.payer_name <> 'NO_INSURANCE'
