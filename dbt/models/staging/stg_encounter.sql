-- Encounters with a care setting derived from Encounter.class and type.
-- Synthea's claim place-of-service codes describe the billing facility, not the
-- visit, so every downstream claim uses this setting instead.
with enc as (
    select * from {{ source('fhir', 'encounter') }}
)

select
    enc.*
  , case
        when class_code = 'IMP' and lower(type_display) like '%rehabilitation%' then 'inpatient substance use'
        when class_code = 'IMP' then 'acute inpatient'
        when class_code = 'EMER' then 'emergency department'
        when class_code = 'HH' and lower(type_display) like '%hospice%' then 'outpatient hospice'
        when class_code = 'HH' then 'home health'
        when class_code = 'VR' then 'telehealth'
        when type_code = '702927004' then 'urgent care'
        when class_code in ('AMB', 'WELLNESS', 'OUTPATIENT') then 'office visit'
        else 'office visit - other'
    end as encounter_type
  , case
        when class_code = 'IMP' then '21'
        when class_code = 'EMER' then '23'
        when class_code = 'HH' then '12'
        when class_code = 'VR' then '02'
        when type_code = '702927004' then '20'
        else '11'
    end as place_of_service_code
  , case
        when class_code = 'IMP' then '111'
        when class_code = 'EMER' then '131'
        when class_code = 'HH' then '321'
        else '131'
    end as bill_type_code
  , case
        when class_code = 'IMP' then '0120'
        when class_code = 'EMER' then '0450'
        when class_code = 'HH' then '0550'
        else '0510'
    end as revenue_center_code
from enc
