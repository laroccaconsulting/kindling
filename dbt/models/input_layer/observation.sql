-- Non-laboratory observations. Panels (e.g. blood pressure) are split into one row per
-- component, with panel_id pointing back at the panel Observation.
with single as (
    select
        cast(id as varchar) as observation_id
      , patient_id
      , encounter_id
      , cast(null as varchar) as panel_id
      , effective_datetime
      , category
      , code_system
      , code_code
      , code_display
      , coalesce(cast(value_quantity as varchar), value_code_display, value_string, cast(value_boolean as varchar)) as result
      , value_unit
      , reference_range_low
      , reference_range_high
    from {{ source('fhir', 'observation') }}
    where category <> 'laboratory'
      and not coalesce(has_components, false)
)

, components as (
    select
        cast(observation_id || '-' || cast(component_index as varchar) as varchar) as observation_id
      , patient_id
      , encounter_id
      , cast(observation_id as varchar) as panel_id
      , effective_datetime
      , category
      , code_system
      , code_code
      , code_display
      , coalesce(cast(value_quantity as varchar), value_code) as result
      , value_unit
      , cast(null as double) as reference_range_low
      , cast(null as double) as reference_range_high
    from {{ source('fhir', 'observation_component') }}
    where category <> 'laboratory'
)

select
    observation_id
  , cast(patient_id as varchar) as person_id
  , cast(patient_id as varchar) as patient_id
  , cast(encounter_id as varchar) as encounter_id
  , panel_id
  , {{ fhir_date('effective_datetime') }} as observation_date
  , case
        when category in ('vital-signs', 'social-history', 'imaging', 'survey', 'exam', 'therapy', 'activity', 'procedure')
            then category
        else 'other'
    end as observation_type
  , {{ tuva_code_type('code_system') }} as source_code_type
  , cast(code_code as varchar) as source_code
  , cast(code_display as varchar) as source_description
  , cast(result as varchar) as result
  , cast(value_unit as varchar) as source_units
  , cast(null as varchar) as normalized_units
  , cast(reference_range_low as varchar) as source_reference_range_low
  , cast(reference_range_high as varchar) as source_reference_range_high
  , cast(null as varchar) as normalized_reference_range_low
  , cast(null as varchar) as normalized_reference_range_high
  , {{ ingest_datetime() }} as ingest_datetime
  , '{{ var("kindling_data_source") }}' as data_source
from (select * from single union all select * from components) as obs
