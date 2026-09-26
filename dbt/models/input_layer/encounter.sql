with costs as (
    select
        encounter_id
      , sum(payment_amount) as paid_amount
      , sum(total_submitted) as charge_amount
    from {{ ref('int_claim') }}
    where claim_type in ('professional', 'institutional')
    group by encounter_id
)

select
    cast(enc.id as varchar) as encounter_id
  , cast(enc.patient_id as varchar) as person_id
  , cast(enc.patient_id as varchar) as patient_id
  , enc.encounter_type
  , {{ fhir_date('enc.period_start') }} as encounter_start_date
  , {{ fhir_date('enc.period_end') }} as encounter_end_date
  , cast(enc.admit_source_code as varchar) as admit_source_code
  , cast(null as varchar) as admit_type_code
  , cast(enc.discharge_disposition_code as varchar) as discharge_disposition_code
  , cast(enc.practitioner_id as varchar) as attending_provider_id
  , {{ clean_name('enc.practitioner_name') }} as attending_provider_name
  , cast(null as varchar) as facility_npi
  , coalesce(enc.location_name, enc.service_provider_name) as facility_name
  , {{ tuva_code_type('enc.reason_system') }} as primary_diagnosis_code_type
  , cast(enc.reason_code as varchar) as primary_diagnosis_code
  , cast(null as varchar) as drg_code_type
  , cast(null as varchar) as drg_code
  , cast(costs.paid_amount as double) as paid_amount
  , cast(costs.paid_amount as double) as allowed_amount
  , cast(costs.charge_amount as double) as charge_amount
  , {{ ingest_datetime() }} as ingest_datetime
  , '{{ var("kindling_data_source") }}' as data_source
from {{ ref('stg_encounter') }} as enc
left join costs
    on enc.id = costs.encounter_id
