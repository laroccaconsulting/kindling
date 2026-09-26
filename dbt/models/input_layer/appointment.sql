-- Synthea doesn't generate Appointment resources. Tuva expects the table when
-- clinical data is enabled, so provide it empty with the contract's columns.
select
    cast(null as varchar) as appointment_id
  , cast(null as varchar) as person_id
  , cast(null as varchar) as patient_id
  , cast(null as varchar) as encounter_id
  , cast(null as timestamp) as start_datetime
  , cast(null as timestamp) as end_datetime
  , cast(null as integer) as duration
  , cast(null as varchar) as location_id
  , cast(null as varchar) as practitioner_id
  , cast(null as varchar) as type
  , cast(null as varchar) as status
  , cast(null as varchar) as reason
  , cast(null as varchar) as cancellation_reason
  , cast(null as timestamp) as ingest_datetime
  , cast(null as varchar) as data_source
where false
