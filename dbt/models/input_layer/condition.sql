select
    cast(id as varchar) as source_condition_id
  , cast(patient_id as varchar) as person_id
  , cast(patient_id as varchar) as patient_id
  , cast(encounter_id as varchar) as encounter_id
  , coalesce({{ fhir_date('recorded_date') }}, {{ fhir_date('onset_datetime') }}) as recorded_date
  , {{ fhir_date('onset_datetime') }} as onset_date
  , {{ fhir_date('abatement_datetime') }} as resolved_date
  , cast(clinical_status as varchar) as status
  , case category
        when 'problem-list-item' then 'problem'
        else 'discharge diagnosis'
    end as condition_type
  , {{ tuva_code_type('code_system') }} as code_system
  , cast(code_code as varchar) as source_code
  , cast(code_display as varchar) as source_description
  , cast(null as integer) as condition_rank
  , cast(null as varchar) as present_on_admit_code
  , {{ ingest_datetime() }} as ingest_datetime
  , '{{ var("kindling_data_source") }}' as data_source
from {{ source('fhir', 'condition') }}
where verification_status is null or verification_status <> 'entered-in-error'
