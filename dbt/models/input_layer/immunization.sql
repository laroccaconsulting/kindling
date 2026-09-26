select
    cast(id as varchar) as immunization_id
  , cast(patient_id as varchar) as person_id
  , cast(patient_id as varchar) as patient_id
  , cast(encounter_id as varchar) as encounter_id
  , {{ tuva_code_type('vaccine_system') }} as source_code_type
  , cast(vaccine_code as varchar) as source_code
  , cast(vaccine_display as varchar) as source_description
  , cast(status as varchar) as status
  , cast(status_reason_code as varchar) as status_reason
  , {{ fhir_date('occurrence_datetime') }} as occurrence_date
  , cast(dose_quantity as varchar) as source_dose
  , cast(lot_number as varchar) as lot_number
  , cast(site_code as varchar) as body_site
  , cast(route_code as varchar) as route
  , cast(location_id as varchar) as location_id
  , cast(practitioner_id as varchar) as practitioner_id
  , {{ ingest_datetime() }} as ingest_datetime
  , '{{ var("kindling_data_source") }}' as data_source
from {{ source('fhir', 'immunization') }}
