-- Laboratory observations, with the ordering panel (DiagnosticReport) when there is one.
with panel as (
    select
        observation_id
      , any_value(diagnostic_report_id) as diagnostic_report_id
      , any_value(code_system) as order_system
      , any_value(code_code) as order_code
      , any_value(code_display) as order_display
    from {{ source('fhir', 'diagnostic_report_result') }}
    group by observation_id
)

select
    cast(obs.id as varchar) as lab_result_id
  , cast(obs.patient_id as varchar) as person_id
  , cast(obs.patient_id as varchar) as patient_id
  , cast(obs.encounter_id as varchar) as encounter_id
  , cast(panel.diagnostic_report_id as varchar) as accession_number
  , {{ tuva_code_type('panel.order_system') }} as source_order_type
  , cast(panel.order_code as varchar) as source_order_code
  , cast(panel.order_display as varchar) as source_order_description
  , {{ tuva_code_type('obs.code_system') }} as source_component_type
  , cast(obs.code_code as varchar) as source_component_code
  , cast(obs.code_display as varchar) as source_component_description
  , cast(obs.status as varchar) as status
  , cast(coalesce(cast(obs.value_quantity as varchar), obs.value_code_display, obs.value_string) as varchar) as result
  , {{ fhir_timestamp('obs.effective_datetime') }} as result_datetime
  , {{ fhir_timestamp('obs.effective_datetime') }} as collection_datetime
  , cast(obs.value_unit as varchar) as source_units
  , cast(null as varchar) as normalized_units
  , cast(obs.reference_range_low as varchar) as source_reference_range_low
  , cast(obs.reference_range_high as varchar) as source_reference_range_high
  , cast(null as varchar) as normalized_reference_range_low
  , cast(null as varchar) as normalized_reference_range_high
  , cast(obs.interpretation_code as varchar) as source_abnormal_code
  , cast(null as varchar) as normalized_abnormal_code
  , cast(null as varchar) as specimen
  , cast(null as varchar) as ordering_practitioner_id
  , {{ ingest_datetime() }} as ingest_datetime
  , '{{ var("kindling_data_source") }}' as data_source
from {{ source('fhir', 'observation') }} as obs
left join panel
    on obs.id = panel.observation_id
where obs.category = 'laboratory'
