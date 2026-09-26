select
    cast(id as varchar) as source_procedure_id
  , cast(patient_id as varchar) as person_id
  , cast(patient_id as varchar) as patient_id
  , cast(encounter_id as varchar) as encounter_id
  , {{ fhir_date('performed_start') }} as procedure_date
  , {{ tuva_code_type('code_system') }} as code_system
  , cast(code_code as varchar) as source_code
  , cast(code_display as varchar) as source_description
  , cast(null as varchar) as modifier_1
  , cast(null as varchar) as modifier_2
  , cast(null as varchar) as modifier_3
  , cast(null as varchar) as modifier_4
  , cast(null as varchar) as modifier_5
  , cast(practitioner_id as varchar) as practitioner_id
  , {{ ingest_datetime() }} as ingest_datetime
  , '{{ var("kindling_data_source") }}' as data_source
from {{ source('fhir', 'procedure') }}
where status is null or status not in ('entered-in-error', 'not-done')
