-- Prescriptions (MedicationRequest). medicationReference is resolved to the
-- Medication resource's code; RxNorm codes also get a representative NDC.
with mr as (
    select
        mr.*
      , coalesce(mr.medication_system, med.code_system) as med_system
      , coalesce(mr.medication_code, med.code_code) as med_code
      , coalesce(mr.medication_display, med.code_display) as med_display
    from {{ source('fhir', 'medication_request') }} as mr
    left join {{ source('fhir', 'medication') }} as med
        on mr.medication_id = med.id
)

select
    cast(mr.id as varchar) as medication_id
  , cast(mr.patient_id as varchar) as person_id
  , cast(mr.patient_id as varchar) as patient_id
  , cast(mr.encounter_id as varchar) as encounter_id
  , cast(null as date) as dispensing_date
  , {{ fhir_date('mr.authored_on') }} as prescribing_date
  , {{ tuva_code_type('mr.med_system') }} as source_code_type
  , cast(mr.med_code as varchar) as source_code
  , cast(mr.med_display as varchar) as source_description
  , ndc.ndc_code
  , case when mr.med_system = 'http://www.nlm.nih.gov/research/umls/rxnorm' then cast(mr.med_code as varchar) end as rxnorm_code
  , cast(null as varchar) as atc_code
  , cast(null as varchar) as route
  , cast(null as varchar) as strength
  , cast(mr.dispense_quantity as double) as quantity
  , cast(null as varchar) as quantity_unit
  , cast(mr.days_supply as double) as days_supply
  , cast(mr.requester_id as varchar) as practitioner_id
  , {{ ingest_datetime() }} as ingest_datetime
  , '{{ var("kindling_data_source") }}' as data_source
from mr
left join {{ ref('int_rxnorm_to_ndc') }} as ndc
    on mr.med_system = 'http://www.nlm.nih.gov/research/umls/rxnorm'
   and mr.med_code = ndc.rxnorm_code
